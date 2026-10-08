"""Pipeline steps shared by run_local and the Lambda handlers.

ingest()   -> fires, met, sources        (each source failure is recorded, never raised, except met:
                                          without winds there is nothing to model, so that raises)
publish()  -> model.run + write artifacts to runs/<run_id>/ then latest/, meta.json last
Raw inputs can be round-tripped through the store (raw/<run_id>/fires.json, met.npz, sources.json) so the
ingest and model Lambdas stay separate steps in Step Functions.
"""
from __future__ import annotations

import io
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import numpy as np

from dhuaan.config import DOMAIN
from dhuaan.ingest.common import iso_z, now_utc, source_status
from dhuaan.model.types import Fire, MetField

log = logging.getLogger("dhuaan.pipeline")


def floor_hour(t: datetime) -> datetime:
    return t.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


def make_run_id(t0: datetime) -> str:
    return f"{t0:%Y%m%dT%H%MZ}"


def parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


# ---------- serialisation of raw inputs ----------

def fires_to_json(fires: list[Fire]) -> list[dict[str, Any]]:
    return [{"id": f.id, "lat": f.lat, "lon": f.lon, "time_utc": iso_z(f.time_utc), "frp_mw": f.frp_mw,
             "sensor": f.sensor, "confidence": f.confidence} for f in fires]


def fires_from_json(rows: list[dict[str, Any]]) -> list[Fire]:
    return [Fire(id=r["id"], lat=float(r["lat"]), lon=float(r["lon"]), time_utc=parse_iso(r["time_utc"]),
                 frp_mw=None if r.get("frp_mw") is None else float(r["frp_mw"]), sensor=r["sensor"],
                 confidence=r["confidence"]) for r in rows]


MET_FIELDS = ("u10", "v10", "u925", "v925", "u850", "v850", "blh")


def met_to_npz(met: MetField) -> bytes:
    buf = io.BytesIO()
    times = np.array([int(t.timestamp()) for t in met.times], dtype=np.int64)
    np.savez_compressed(buf, lons=met.lons, lats=met.lats, times=times,
                        **{k: np.asarray(getattr(met, k), dtype=np.float32) for k in MET_FIELDS})
    return buf.getvalue()


def met_from_npz(data: bytes) -> MetField:
    z = np.load(io.BytesIO(data))
    times = [datetime.fromtimestamp(int(t), tz=timezone.utc) for t in z["times"]]
    return MetField(lons=z["lons"], lats=z["lats"], times=times, **{k: z[k] for k in MET_FIELDS})


# ---------- ingest ----------

def ingest(t0: datetime, *, use_lsasaf: bool = True, firms_days: int = 2, with_openaq: bool = True,
           use_cache: bool | None = None) -> tuple[list[Fire], MetField, list[dict[str, Any]]]:
    from dhuaan.ingest import firms, openmeteo

    sources: list[dict[str, Any]] = []
    fires, st = firms.fetch_recent(firms_days, use_cache=use_cache)
    sources += st
    if use_lsasaf:
        try:
            from dhuaan.ingest import lsasaf
            lf, s = lsasaf.fetch_recent(t0 + timedelta(hours=1), use_cache=use_cache)
            fires += lf
            sources.append(s)
        except Exception as e:
            log.warning("LSA SAF failed: %s", e)
            sources.append(source_status("LSA SAF MSG-IODC FRP-PIXEL", ok=False, note=str(e)[:200]))
    else:
        sources.append(source_status("LSA SAF MSG-IODC FRP-PIXEL", ok=False, note="skipped (--no-lsasaf)"))
    if with_openaq:
        try:
            from dhuaan.ingest import openaq
            sources.append(openaq.status_for_stations(openaq.fetch_stations(use_cache=use_cache)))
        except Exception as e:
            sources.append(source_status("OpenAQ PM2.5 stations", ok=False, note=str(e)[:200]))
    try:
        met, s = openmeteo.fetch_forecast(t0, use_cache=use_cache)
        sources.append(s)
    except Exception as e:
        sources.append(source_status("Open-Meteo forecast", ok=False, note=str(e)[:200]))
        raise RuntimeError(f"met ingest failed, cannot model: {e}") from e
    fires = sorted({f.id: f for f in fires}.values(), key=lambda f: (f.time_utc, f.id))
    return fires, met, sources


def save_raw(store: Any, run_id: str, t0: datetime, fires: list[Fire], met: MetField,
             sources: list[dict[str, Any]]) -> None:
    store.put_json(f"raw/{run_id}/fires.json", {"t0_utc": iso_z(t0), "fires": fires_to_json(fires)})
    store.put_bytes(f"raw/{run_id}/met.npz", met_to_npz(met))
    store.put_json(f"raw/{run_id}/sources.json", sources)


def load_raw(store: Any, run_id: str) -> tuple[datetime, list[Fire], MetField, list[dict[str, Any]]]:
    doc = store.get_json(f"raw/{run_id}/fires.json")
    met_b = store.get_bytes(f"raw/{run_id}/met.npz")
    if doc is None or met_b is None:
        raise FileNotFoundError(f"raw inputs for run {run_id} not found")
    return parse_iso(doc["t0_utc"]), fires_from_json(doc["fires"]), met_from_npz(met_b), \
        store.get_json(f"raw/{run_id}/sources.json") or []


# ---------- model + publish ----------

def calibration(store: Any, afternoon_mode: str) -> tuple[float, bool]:
    """alpha from env DHUAAN_ALPHA, else the backtest's calibration (B when afternoon fires are used), else 1.0."""
    if os.environ.get("DHUAAN_ALPHA"):
        return float(os.environ["DHUAAN_ALPHA"]), True
    try:
        bt = store.get_json("latest/backtest.json") or {}
        cal = bt.get("calibration") or {}
        a = cal.get("alpha_B" if afternoon_mode != "none" else "alpha_A")
        if a:
            return float(a), True
    except Exception as e:
        log.warning("could not read backtest calibration: %s", e)
    return 1.0, False


def regional_calibration(store: Any, afternoon_mode: str, pooled: float, calibrated: bool) -> tuple[dict, str]:
    """(alpha_by_region {delhi_ncr, punjab_haryana, _default}, calibration_basis text).

    Uses backtest.json "exploratory_regional" alphas (B when afternoon fires are used, else A) where present;
    _default (and any missing region) is the pooled, pre-registered alpha."""
    from dhuaan.geo.regions import DEFAULT, REGIONS
    cfg = "B" if afternoon_mode != "none" else "A"
    by = {r: pooled for r in REGIONS}
    by[DEFAULT] = pooled
    if os.environ.get("DHUAAN_ALPHA") or not calibrated:
        why = "DHUAAN_ALPHA override" if os.environ.get("DHUAAN_ALPHA") else "uncalibrated default"
        return by, f"single alpha {pooled:g} everywhere ({why}); provisional"
    try:
        ex = ((store.get_json("latest/backtest.json") or {}).get("exploratory_regional") or {})
        al = (ex.get("alphas") or {}).get(cfg) or {}
    except Exception as e:
        log.warning("could not read exploratory regional calibration: %s", e)
        al = {}
    got = {r: float(al[r]) for r in REGIONS if al.get(r)}
    by.update(got)
    if not got:
        return by, (f"pooled pre-registered backtest alpha_{cfg}={pooled:g} everywhere "
                    "(25 Oct-5 Nov 2025 fit, 9 CPCB stations); provisional")
    parts = ", ".join(f"{r} {by[r]:g}" for r in REGIONS)
    return by, (f"provisional: exploratory regional alphas (not pre-registered; config {cfg}, fitted 25 Oct-5 Nov "
                f"2025 on DPCC Delhi and PPCB Punjab stations): {parts}; elsewhere the pooled pre-registered "
                f"alpha_{cfg}={pooled:g}")


def _write_all(store: Any, items: list[tuple[str, Any]], workers: int = 16) -> None:
    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(lambda kv: store.put_json(kv[0], kv[1]), items))


def publish(store: Any, run_id: str, t0: datetime, fires: list[Fire], met: MetField,
            sources: list[dict[str, Any]], *, members: int = 5, afternoon_mode: str = "estimated",
            seed: int = 0, run_model: Callable[..., dict[str, Any]] | None = None,
            receptors: list | None = None, population: np.ndarray | None = None) -> dict[str, Any]:
    """Run the model, write every artifact to runs/<run_id>/ and latest/, then meta.json. Returns meta."""
    from dhuaan.geo.districts import district_of
    if receptors is None:
        from dhuaan.geo.receptors import load_receptors
        receptors = load_receptors()
    if population is None:
        from dhuaan.geo.population import load_population
        population = load_population()
    if run_model is None:
        from dhuaan.model import run as run_model
    try:
        from dhuaan.model import MODEL_VERSION
    except ImportError:
        MODEL_VERSION = "unknown"

    if afternoon_mode == "observed" and not any(f.sensor == "MSG_IODC" for f in fires):
        lsa = next((s for s in sources if s["name"].startswith("LSA SAF")), None)
        if lsa is None or not lsa["ok"]:
            log.warning("afternoon_mode=observed but LSA SAF unavailable; using estimated")
            afternoon_mode = "estimated"

    arts = run_model(fires, met, receptors, population, t0, members=members, seed=seed,
                     afternoon_mode=afternoon_mode, district_of=district_of)
    summary = arts.pop("_summary", {}) or {}
    arts.pop("meta.json", None)
    alpha, calibrated = calibration(store, afternoon_mode)
    alpha_by_region, basis = regional_calibration(store, afternoon_mode, alpha, calibrated)
    meta = {
        "run_id": run_id, "t0_utc": iso_z(t0), "generated_utc": iso_z(now_utc()), "model_version": MODEL_VERSION,
        "members": summary.get("members", members), "afternoon_mode": summary.get("afternoon_mode", afternoon_mode),
        "alpha": alpha, "alpha_by_region": alpha_by_region, "calibration_basis": basis,
        "calibrated": calibrated, "arrival_threshold": summary.get("arrival_threshold"),
        "scale": summary.get("scale"), "domain": dict(DOMAIN), "sources": sources,
        "model_summary": summary,
    }
    items = list(arts.items())
    # Archive only the run-level files under runs/; the ~3k per-place files go to latest/ only (keeps S3 PUTs low on the Free plan).
    archived = [(f"runs/{run_id}/{k}", v) for k, v in items if not k.startswith("places/")]
    _write_all(store, archived + [(f"runs/{run_id}/meta.json", meta)])
    _write_all(store, [(f"latest/{k}", v) for k, v in items])
    store.put_json("latest/meta.json", meta)  # last: its presence means latest/ is complete
    meta["_n_artifacts"] = len(items) + 1
    return meta
