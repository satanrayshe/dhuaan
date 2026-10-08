"""Build small, schema-valid fixture artifacts (CONTRACTS items 2, 5, 6, 7) for agent/API tests.

`uv run python tests/agent/make_fixtures.py [root] [t0_iso]` regenerates tests/agent/fixtures/latest/ (default t0 2026-10-08T00:00:00Z).
The live check uses build(root, t0=now) so the agent sees a run that looks fresh.
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_T0 = datetime(2026, 10, 8, 0, 0, tzinfo=timezone.utc)


def _iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _pulse(peak_idx: int, peak: float, width: float, base: float = 0.4) -> list[float]:
    return [round(base + peak * math.exp(-((i - peak_idx) / width) ** 2), 2) for i in range(97)]


PLACES = [
    # id, name, kind, district, state, lat, lon, peak hour offset from t0, peak smoke, width
    ("sch_demo_sunrise", "Sunrise Public School (demo, fictional)", "school", "Ludhiana", "Punjab", 30.8462, 75.9734, 32, 95.4, 6.0),
    ("town_khanna", "Khanna", "town", "Ludhiana", "Punjab", 30.7046, 76.2219, 30, 71.8, 6.0),
    ("city_ludhiana", "Ludhiana", "city", "Ludhiana", "Punjab", 30.9010, 75.8573, 33, 64.2, 7.0),
    ("city_patiala", "Patiala", "city", "Patiala", "Punjab", 30.3398, 76.3869, 40, 22.6, 8.0),
    ("vil_bhadaur", "Bhadaur", "village", "Barnala", "Punjab", 30.4767, 75.3260, 20, 40.1, 5.0),
]
SCALE = 100.0
THRESHOLD = 15.0


def _place(t0: datetime, p: tuple) -> dict:
    pid, name, kind, district, state, lat, lon, peak_off, peak, width = p
    peak_idx = 24 + peak_off
    series = _pulse(peak_idx, peak, width)
    p10 = [round(v * 0.6, 2) for v in series]
    p90 = [round(v * 1.45, 2) for v in series]
    arrival_idx = next((i for i in range(24, 97) if series[i] >= THRESHOLD), None)
    arrival = _iso(t0 + timedelta(hours=arrival_idx - 24)) if arrival_idx is not None else None
    window = None
    if arrival_idx is not None:
        e = next((i for i in range(24, 97) if p90[i] >= THRESHOLD), arrival_idx)
        lt = next((i for i in range(24, 97) if p10[i] >= THRESHOLD), arrival_idx + 3)
        window = [_iso(t0 + timedelta(hours=e - 24)), _iso(t0 + timedelta(hours=lt - 24))]
    peak_i = max(range(24, 97), key=lambda i: series[i])
    return {
        "id": pid, "name": name, "kind": kind, "district": district, "state": state, "lat": lat, "lon": lon,
        "t0_utc": _iso(t0), "series": series, "p10": p10, "p90": p90,
        "arrival_utc": arrival, "arrival_window": window,
        "peak_utc": _iso(t0 + timedelta(hours=peak_i - 24)), "peak_smoke": series[peak_i],
        "attribution": [
            {"district": "Sangrur", "state": "Punjab", "share": 0.34},
            {"district": "Barnala", "state": "Punjab", "share": 0.22},
            {"district": "Ludhiana", "state": "Punjab", "share": 0.18},
            {"district": "Moga", "state": "Punjab", "share": 0.11},
            {"district": "Patiala", "state": "Punjab", "share": 0.07},
            {"district": "Other", "state": "", "share": 0.08},
        ],
        "top_clusters": [{"cluster_id": "c0001", "share": 0.21}, {"cluster_id": "c0002", "share": 0.14}, {"cluster_id": "c0003", "share": 0.09}],
    }


def _clusters(t0: datetime, places: list[dict]) -> dict:
    sch = places[0]
    def dw(p: dict) -> dict:
        return {"place_id": p["id"], "name": p["name"], "kind": p["kind"], "arrival_utc": p["arrival_utc"],
                "peak_utc": p["peak_utc"], "peak_smoke": p["peak_smoke"]}
    rows = [
        ("c0001", 30.2512, 75.8431, 14, 412.6, "Sangrur", "Bhawanigarh", 1824000.0, 0.21),
        ("c0002", 30.3770, 75.5480, 9, 233.1, "Barnala", "Tapa", 1216000.0, 0.14),
        ("c0003", 30.7905, 75.6120, 6, 120.4, "Ludhiana", "Jagraon", 782000.0, 0.09),
        ("c0004", 30.1023, 76.0011, 4, 61.0, "Patiala", "Samana", 401000.0, 0.05),
    ]
    out = []
    for rank, (cid, lat, lon, n, frp, district, near, exp, share) in enumerate(rows, start=1):
        out.append({
            "cluster_id": cid, "lat": lat, "lon": lon, "n_detections": n, "frp_sum_mw": frp,
            "first_seen_utc": _iso(t0 - timedelta(hours=14)), "last_seen_utc": _iso(t0 - timedelta(hours=9)),
            "district": district, "state": "Punjab", "nearest_place": near, "rank": rank,
            "exposure_person_hours": exp, "exposure_share": share,
            "downwind": [dw(sch), dw(places[1]), dw(places[2])] if rank <= 2 else [dw(places[2])],
        })
    return {"t0_utc": _iso(t0), "clusters": out}


def build(root: Path, t0: datetime = DEFAULT_T0) -> None:
    latest = Path(root) / "latest"
    (latest / "places").mkdir(parents=True, exist_ok=True)
    places = [_place(t0, p) for p in PLACES]
    for p in places:
        (latest / "places" / f"{p['id']}.json").write_text(json.dumps(p, ensure_ascii=False), encoding="utf-8")
    index = {"t0_utc": _iso(t0), "places": [
        {k: p[k] for k in ("id", "name", "kind", "district", "state", "lat", "lon", "peak_smoke", "peak_utc", "arrival_utc")}
        for p in places]}
    (latest / "receptors_index.json").write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    (latest / "clusters.json").write_text(json.dumps(_clusters(t0, places), ensure_ascii=False), encoding="utf-8")
    meta = {
        "run_id": t0.strftime("%Y%m%dT%HZ"), "t0_utc": _iso(t0), "generated_utc": _iso(t0 + timedelta(minutes=22)),
        "model_version": "fixture-0.1", "members": 5, "afternoon_mode": "estimated", "alpha": 1.0, "calibrated": False,
        "arrival_threshold": THRESHOLD, "scale": SCALE,
        "domain": {"lon_min": 72.5, "lon_max": 79.0, "lat_min": 28.0, "lat_max": 32.75},
        "sources": [
            {"name": "FIRMS VIIRS/MODIS", "fetched_utc": _iso(t0 + timedelta(minutes=5)), "latest_obs_utc": _iso(t0 - timedelta(hours=9)), "count": 33, "ok": True, "note": ""},
            {"name": "Open-Meteo GFS", "fetched_utc": _iso(t0 + timedelta(minutes=6)), "latest_obs_utc": _iso(t0), "count": 540, "ok": True, "note": ""},
            {"name": "LSA SAF MSG IODC FRP", "fetched_utc": _iso(t0 + timedelta(minutes=7)), "latest_obs_utc": None, "count": 0, "ok": False, "note": "login failed"},
        ],
    }
    (latest / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "fixtures"
    t0 = datetime.fromisoformat(sys.argv[2].replace("Z", "+00:00")) if len(sys.argv) > 2 else DEFAULT_T0
    build(root, t0)
    print(f"fixtures written to {root}")
