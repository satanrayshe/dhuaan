"""Backtest A vs B on the 11 Nov 2025 episode -> out/latest/backtest.json (CONTRACTS item 9).

    uv run python -m dhuaan.backtest.run [--members 3] [--reuse]

Protocol (definitions pre-registered in prep/01-project-spec.md, "Backtest"; implemented in metrics.py):
- Forecasts are issued daily at 00:00Z (05:30 IST), 24 Oct .. 20 Nov 2025. Each uses only fires detected in
  [issue - 48 h, issue] and runs the smoke model (dhuaan.model.core.simulate, `--members` ensemble members, median)
  with archived-forecast winds for issue - 48 h .. issue + 72 h, sampled at the station locations.
- Stitched evaluation series: hour t is taken from the forecast issued at 00Z on the day of t - 12 h, so every
  scored hour has a lead of 12-35 h (a "tomorrow" forecast with no knowledge of fires after issue time).
- Calibration alpha (least squares through the origin) on 25 Oct 00Z - 5 Nov 23Z; everything is scored on
  6 Nov 00Z - 20 Nov 23Z only. Episodes are attributed to the period of their start hour.
- Lead time uses every forecast issued >= 12 h before the episode start (leads up to 72 h).
- A = FIRMS VIIRS/MODIS only (afternoon_mode "none"); B = A + GK2A hourly afternoon detections (flags >= 2,
  sensor "GK2A", frp None, afternoon_mode "observed"). Static hotspots are masked from FIRMS in both.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np

from dhuaan.config import settings
from dhuaan.ingest.common import iso_z, now_utc
from dhuaan.model.types import Fire, Receptor

from . import gk2a, inputs, metrics as M, ratio

log = logging.getLogger("dhuaan.backtest")
UTC = timezone.utc
WIN_START = datetime(2025, 10, 25, tzinfo=UTC)
WIN_END = datetime(2025, 11, 20, 23, tzinfo=UTC)
FIT_END = datetime(2025, 11, 5, 23, tzinfo=UTC)
HELD_START = datetime(2025, 11, 6, tzinfo=UTC)
FIRST_ISSUE = datetime(2025, 10, 24, tzinfo=UTC)
LAST_ISSUE = datetime(2025, 11, 20, tzinfo=UTC)
BASELINE_FROM = WIN_START - timedelta(days=7)
MIN_COMPLETENESS = 0.80
LEAD_MIN, LEAD_MAX = 12, 35
MET_SOURCE = ("Open-Meteo Historical Forecast API: archived operational forecasts (best-match model, 0.25 deg), "
              "NOT reanalysis. The archive stitches the first hours of successive forecast runs, so beyond about "
              "1 day of lead the winds are better than what a forecaster had at issue time; treat the skill here "
              "as an upper bound on operational skill.")


def issues() -> list[datetime]:
    out, t = [], FIRST_ISSUE
    while t <= LAST_ISSUE:
        out.append(t)
        t += timedelta(days=1)
    return out


def issue_for(t: datetime) -> datetime:
    """Stitching rule: the 00Z issue of the day of t - 12 h (lead 12..35 h)."""
    u = t - timedelta(hours=LEAD_MIN)
    return datetime(u.year, u.month, u.day, tzinfo=UTC)


def same_day_issue(t: datetime) -> datetime:
    return datetime(t.year, t.month, t.day, tzinfo=UTC)


def run_forecasts(fires: list[Fire], mode: str, met: Any, receptors: list[Receptor], axis: list[datetime],
                  members: int) -> dict[datetime, np.ndarray]:
    """{issue: (Nr, len(axis)) smoke, NaN where the forecast does not cover (before issue / after issue+72h)}."""
    from dhuaan.geo.districts import district_of
    from dhuaan.geo.population import load_population
    from dhuaan.model.core import simulate
    pop = load_population()
    pos = {t: i for i, t in enumerate(axis)}
    out = {}
    for I in issues():
        f = [x for x in fires if I - timedelta(hours=48) <= x.time_utc <= I]
        m = inputs.slice_met(met, I - timedelta(hours=48), I + timedelta(hours=72))
        t = time.perf_counter()
        res = simulate(f, m, receptors, pop, I, members=members, afternoon_mode=mode, district_of=district_of)
        med = np.median(res.rec_members, axis=0)          # (97, Nr), index 0 = I - 24 h
        arr = np.full((len(receptors), len(axis)), np.nan)
        for h in range(0, 73):
            j = pos.get(I + timedelta(hours=h))
            if j is not None:
                arr[:, j] = med[24 + h]
        out[I] = arr
        print(f"    {mode:<8} issue {iso_z(I)}  fires={len(f):<5} particles={res.sources.particles.n:<6} "
              f"{time.perf_counter() - t:.1f}s", flush=True)
    return out


def stitch(fc: dict[datetime, np.ndarray], axis: list[datetime],
           rule: Callable[[datetime], datetime] = issue_for) -> np.ndarray:
    nr = next(iter(fc.values())).shape[0]
    out = np.full((nr, len(axis)), np.nan)
    for j, t in enumerate(axis):
        I = rule(t)
        if I in fc:
            out[:, j] = fc[I][:, j]
    return out


def _rnd(x: Any, k: int = 3) -> float | None:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    return round(float(x), k)


def score(obs: np.ndarray, stitched: np.ndarray, fc: dict[datetime, np.ndarray], axis: list[datetime],
          alpha: float) -> dict[str, Any]:
    """Held-out metrics, pooled over stations. obs, stitched: (Nr, T) on the window axis."""
    held = np.array([t >= HELD_START for t in axis])
    pred = alpha * stitched
    n_ep = n_hit = n_pep = n_fa = 0
    leads: list[int] = []
    per_station = []
    for s in range(obs.shape[0]):
        oe = M.episodes(obs[s])
        pe = M.episodes(pred[s])
        oe_h = [e for e in oe if held[e[0]]]
        pe_h = [e for e in pe if held[e[0]]]
        hits = [e for e in oe_h if M.is_hit(pred[s], e)]
        fa = M.false_alarms(pe_h, oe)
        iss = [(int((I - axis[0]).total_seconds() // 3600), alpha * arr[s]) for I, arr in fc.items()]
        st_leads = [lt for e in oe_h if (lt := M.lead_time(e, iss)) is not None]
        leads += st_leads
        n_ep += len(oe_h)
        n_hit += len(hits)
        n_pep += len(pe_h)
        n_fa += fa
        per_station.append({"n_episodes": len(oe_h), "n_hits": len(hits), "n_forecast_episodes": len(pe_h),
                            "n_false_alarms": fa, "pearson_r": _rnd(M.pearson(obs[s][held], stitched[s][held])),
                            "median_lead_h": _rnd(float(np.median(st_leads)) if st_leads else None, 1)})
    return {
        "hit_rate": _rnd(n_hit / n_ep if n_ep else None),
        "false_alarm_ratio": _rnd(n_fa / n_pep if n_pep else None),
        "median_lead_h": _rnd(float(np.median(leads)) if leads else None, 1),
        "pearson_r": _rnd(M.pearson(obs[:, held].ravel(), stitched[:, held].ravel())),
        "r2": _rnd(M.r2(obs[:, held].ravel(), pred[:, held].ravel())),
        "n_episodes": n_ep, "n_hits": n_hit, "episodes": n_ep, "hits": n_hit,
        "n_forecast_episodes": n_pep, "n_false_alarms": n_fa, "n_lead_episodes": len(leads),
        "_per_station": per_station,
    }


def _fmt(v: Any, pct: bool = False) -> str:
    if v is None:
        return "n/a"
    return f"{v:.0%}" if pct else f"{v}"


def build_notes(res: dict, nowcast: dict, kept: list[dict], excluded: list[dict], members: int,
                n_masked: int, n_hotspots: int, facts: dict) -> list[str]:
    ra, rb = res["A"], res["B"]
    excl = ", ".join(f"{s['name']} ({s['completeness']:.1%})" for s in excluded)
    return [
        f"Headline fact: {_fmt(facts.get('afternoon_share_2025'), True)} of {facts.get('n_detections', 'n/a')} GK2A "
        "detections over Punjab between 12:00 and 18:59 IST in Oct-Nov 2025 fall at or after 16:00 IST, i.e. after the "
        "last VIIRS/MODIS overpass (~13:30 IST). Source: " + gk2a.CITATION + ".",
        "Met data are archived forecasts (Open-Meteo Historical Forecast API), not reanalysis. The archive is stitched "
        "from successive short-range runs, so it is somewhat better than the winds available at issue time.",
        f"Protocol: one forecast per day issued at 00:00Z (05:30 IST), {iso_z(FIRST_ISSUE)[:10]} to "
        f"{iso_z(LAST_ISSUE)[:10]}, using only fires detected in the 48 h before issue. Scored series = lead 12-35 h. "
        f"Ensemble: {members} members, median. Calibration alpha fitted on 25 Oct-5 Nov; every metric is on "
        "6-20 Nov (held out). No parameter was tuned on the held-out period.",
        f"Stations kept (>=80% hourly PM2.5 in the window): {', '.join(s['name'] for s in kept)}. "
        + (f"Excluded for completeness below 80%: {excl}." if excluded else "None excluded."),
        f"A vs B (held out): hit rate {_fmt(ra['hit_rate'])} vs {_fmt(rb['hit_rate'])} ({ra['n_hits']}/{ra['n_episodes']} "
        f"vs {rb['n_hits']}/{rb['n_episodes']} episodes); false-alarm ratio {_fmt(ra['false_alarm_ratio'])} vs "
        f"{_fmt(rb['false_alarm_ratio'])} ({ra['n_false_alarms']}/{ra['n_forecast_episodes']} vs "
        f"{rb['n_false_alarms']}/{rb['n_forecast_episodes']} forecast episodes); median lead "
        f"{_fmt(ra['median_lead_h'])} h vs {_fmt(rb['median_lead_h'])} h; Pearson r {_fmt(ra['pearson_r'])} vs "
        f"{_fmt(rb['pearson_r'])}; R2 {_fmt(ra['r2'])} vs {_fmt(rb['r2'])}.",
        f"Secondary check (not pre-registered): same-day lead 0-23 h gives hit rate {_fmt(nowcast['A']['hit_rate'])} (A) / "
        f"{_fmt(nowcast['B']['hit_rate'])} (B), Pearson r {_fmt(nowcast['A']['pearson_r'])} / "
        f"{_fmt(nowcast['B']['pearson_r'])}.",
        "B adds GK2A detections only for Punjab and Haryana (the dataset's coverage), confidence flags 2-3 as its "
        "README recommends. GK2A has no FRP, so each detection gets the median VIIRS/MODIS FRP. GK2A is a research "
        "dataset published after the season, so B shows what the forecast would have been with hourly afternoon fires.",
        f"FIRMS detections within 1 km of the {n_hotspots} static hotspots (industrial, kiln or landfill cells seen on "
        f">= 8 days in Jan-Aug 2025) are masked in both configurations ({n_masked} masked in Oct-Nov 2025).",
        "PM2.5 excess = PM2.5 minus the trailing 7-day 10th percentile at the same station. In Delhi the excess also "
        "holds local and regional non-fire pollution, which a fire-only model cannot represent.",
    ]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="dhuaan.backtest.run")
    ap.add_argument("--members", type=int, default=3)
    ap.add_argument("--reuse", action="store_true", help="reuse saved model forecasts from cache_dir/backtest")
    ap.add_argument("--out", default=None, help="output path (default: LOCAL_OUT/latest/backtest.json)")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    t_all = time.perf_counter()

    # observations
    full_axis = inputs.hour_axis(BASELINE_FROM, WIN_END)
    axis = [t for t in full_axis if t >= WIN_START]
    off = len(full_axis) - len(axis)
    meta = inputs.station_meta([s["id"] for s in inputs.STATIONS])
    kept, excluded, obs_rows = [], [], []
    for s in inputs.STATIONS:
        pm = inputs.load_pm(s["id"], full_axis)
        comp = float(np.mean(~np.isnan(pm[off:])))
        st = {**s, "lat": meta[s["id"]]["lat"], "lon": meta[s["id"]]["lon"], "completeness": round(comp, 3)}
        ok = comp >= MIN_COMPLETENESS
        (kept if ok else excluded).append(st)
        if ok:
            obs_rows.append(M.excess(pm)[off:])
        print(f"  {s['name']:<38} completeness {comp:.1%} {'kept' if ok else 'EXCLUDED (<80%)'}")
    obs = np.array(obs_rows)
    receptors = [Receptor(str(s["id"]), s["name"], "city", "", s["region"], s["lat"], s["lon"], None) for s in kept]

    # model inputs
    polar, n_masked, _ = ratio.season_polar()
    t_lo, t_hi = FIRST_ISSUE - timedelta(hours=48), LAST_ISSUE
    gk = [f for f in gk2a.to_fires(gk2a.load_rows(2025)) if t_lo <= f.time_utc <= t_hi]
    polar = [f for f in polar if t_lo <= f.time_utc <= t_hi]
    met, _ = inputs.load_met((FIRST_ISSUE - timedelta(days=2)).date(), (LAST_ISSUE + timedelta(days=3)).date())
    print(f"  fires: polar {len(polar)} (season static-hotspot masked: {n_masked}), GK2A flags>=2 {len(gk)}; "
          f"met {len(met.times)} h")

    cache = Path(settings.cache_dir) / "backtest"
    cache.mkdir(parents=True, exist_ok=True)
    fcs: dict[str, dict[datetime, np.ndarray]] = {}
    configs = (("A", polar, "none"), ("B", sorted(polar + gk, key=lambda f: (f.time_utc, f.id)), "observed"))
    for cfg, fires, mode in configs:
        p = cache / f"forecasts_{cfg}_m{a.members}_{len(kept)}st.npz"
        if a.reuse and p.exists():
            z = np.load(p)
            fcs[cfg] = {datetime.fromtimestamp(int(k), tz=UTC): z[k] for k in z.files}
            print(f"  {cfg}: reused {len(fcs[cfg])} forecasts from {p.name}")
        else:
            print(f"  {cfg}: running {len(issues())} forecasts, members={a.members}")
            fcs[cfg] = run_forecasts(fires, mode, met, receptors, axis, a.members)
            np.savez_compressed(p, **{str(int(I.timestamp())): v for I, v in fcs[cfg].items()})

    fit = np.array([t <= FIT_END for t in axis])
    res: dict[str, dict[str, Any]] = {}
    nowcast: dict[str, dict[str, Any]] = {}
    stitched: dict[str, np.ndarray] = {}
    alphas: dict[str, float] = {}
    for cfg in ("A", "B"):
        stitched[cfg] = stitch(fcs[cfg], axis)
        alphas[cfg] = M.fit_alpha(obs[:, fit].ravel(), stitched[cfg][:, fit].ravel())
        res[cfg] = score(obs, stitched[cfg], fcs[cfg], axis, alphas[cfg])
        # secondary, not pre-registered: same-day lead 0-23 h (00Z issue of the same day), same alpha
        nowcast[cfg] = score(obs, stitch(fcs[cfg], axis, same_day_issue), fcs[cfg], axis, alphas[cfg])

    stations_out = []
    for k, st in enumerate(kept):
        series = []
        for j, t in enumerate(axis):
            ov, pa, pb = obs[k, j], alphas["A"] * stitched["A"][k, j], alphas["B"] * stitched["B"][k, j]
            series.append({"t": iso_z(t), "obs_excess": _rnd(ov, 1), "pred_A": _rnd(pa, 1), "pred_B": _rnd(pb, 1)})
        stations_out.append({"id": str(st["id"]), "name": st["name"], "lat": st["lat"], "lon": st["lon"],
                             "region": st["region"], "completeness": st["completeness"],
                             "metrics": {"A": res["A"]["_per_station"][k], "B": res["B"]["_per_station"][k]},
                             "series": series})
    for d in (res, nowcast):
        for cfg in ("A", "B"):
            d[cfg].pop("_per_station")

    from dhuaan.ingest import firms
    facts = json.loads(ratio.FACTS_FILE.read_text(encoding="utf-8")) if ratio.FACTS_FILE.exists() else {}
    notes = build_notes(res, nowcast, kept, excluded, a.members, n_masked, len(firms.load_static_hotspots()), facts)
    # diagnostic only (fit period, nothing is re-fitted or scored with it): why one pooled alpha is small
    diag = []
    for region in ("Punjab", "Delhi"):
        rows = [k for k, s in enumerate(kept) if s["region"] == region]
        if rows:
            al = {c: M.fit_alpha(obs[rows][:, fit].ravel(), stitched[c][rows][:, fit].ravel()) for c in ("A", "B")}
            diag.append(f"{region}: mean observed excess {np.nanmean(obs[rows]):.0f} ug/m3, mean raw model smoke "
                        f"{np.nanmean(stitched['A'][rows]):.1f} (A) / {np.nanmean(stitched['B'][rows]):.1f} (B), "
                        f"fit-period alpha if fitted alone {al['A']:.2f} (A) / {al['B']:.2f} (B)")
    notes.append("Diagnostic (fit period, not used for scoring): " + "; ".join(diag) + ". The single pooled alpha is "
                 "pulled down by Punjab stations where the model is noisy near the fires, so calibrated forecasts "
                 "rarely reach 60 ug/m3 and the episode hit rate is near zero. Correlation, not the 60 ug/m3 "
                 "threshold, is where the model shows some (weak) skill, and B correlates better than A in Delhi.")
    doc = {
        "window": {"start_utc": iso_z(WIN_START), "end_utc": iso_z(WIN_END), "episode_date": "2025-11-11",
                   "fit": [iso_z(WIN_START), iso_z(FIT_END)], "held_out": [iso_z(HELD_START), iso_z(WIN_END)],
                   "issue_times": f"daily 00:00Z, {iso_z(FIRST_ISSUE)} to {iso_z(LAST_ISSUE)}",
                   "scored_lead_h": [LEAD_MIN, LEAD_MAX]},
        "met_source": MET_SOURCE,
        "stations": stations_out,
        "metrics": {"A": res["A"], "B": res["B"]},
        "calibration": {"alpha_A": _rnd(alphas["A"], 4), "alpha_B": _rnd(alphas["B"], 4),
                        "method": "least squares through the origin, excess ~ alpha * C, 25 Oct 00Z to 5 Nov 23Z, "
                                  "all kept stations pooled, lead 12-35 h"},
        "secondary_lead_0_23h": nowcast,
        "excluded_stations": [{"id": str(s["id"]), "name": s["name"], "completeness": s["completeness"]} for s in excluded],
        "members": a.members, "generated_utc": iso_z(now_utc()),
        "facts": {k: facts.get(k) for k in ("afternoon_share_2025", "n_detections", "source")},
        "notes": notes,
    }
    if a.out:
        Path(a.out).write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        where = a.out
    else:
        from dhuaan.store import LocalStore
        LocalStore().put_json("latest/backtest.json", doc)
        where = str(Path(settings.local_out) / "latest" / "backtest.json")
    print(f"  alpha_A={doc['calibration']['alpha_A']} alpha_B={doc['calibration']['alpha_B']}")
    for cfg in ("A", "B"):
        print(f"  {cfg}: " + ", ".join(f"{k}={v}" for k, v in res[cfg].items()))
        print(f"  {cfg} (lead 0-23 h, secondary): " + ", ".join(f"{k}={v}" for k, v in nowcast[cfg].items()))
    for st in stations_out:
        print(f"    {st['name']:<38} A {st['metrics']['A']}\n    {'':<38} B {st['metrics']['B']}")
    print(f"  wrote {where}  ({time.perf_counter() - t_all:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
