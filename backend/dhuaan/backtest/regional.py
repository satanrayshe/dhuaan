"""EXPLORATORY regional calibration (not pre-registered). The pooled alpha in backtest.json "calibration" stays
the reported result; this block only asks how much a per-region alpha would change the held-out picture.

Same protocol as the pooled fit: least squares through the origin on the fit period (25 Oct-5 Nov), stitched
lead 12-35 h, then the identical score() on the held-out period (6-20 Nov). Regions follow dhuaan.geo.regions:
"delhi_ncr" = DPCC Delhi stations, "punjab_haryana" = PPCB Punjab stations. Uses the saved forecasts (--reuse).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

import numpy as np

from dhuaan.geo.regions import REGIONS, station_region

from . import metrics as M

LABEL = "Exploratory - not pre-registered"


def _pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.0%}"


_KEYS = ("hit_rate", "false_alarm_ratio", "median_lead_h", "pearson_r", "r2", "n_episodes", "n_hits",
         "n_forecast_episodes", "n_false_alarms")


def exploratory(obs: np.ndarray, stitched: dict[str, np.ndarray], fcs: dict[str, dict[datetime, np.ndarray]],
                axis: list[datetime], fit: np.ndarray, kept: list[dict], score: Callable[..., dict[str, Any]],
                rnd: Callable[..., float | None]) -> dict[str, Any]:
    reg = np.array([station_region(s["region"]) for s in kept])
    held = ~fit
    rows_of = {r: np.where(reg == r)[0] for r in REGIONS}
    alphas: dict[str, dict[str, float | None]] = {"A": {}, "B": {}}
    metrics: dict[str, dict[str, Any]] = {}
    by_region: dict[str, dict[str, Any]] = {r: {} for r in REGIONS}
    for cfg in ("A", "B"):
        a_st = np.zeros(len(kept))
        for r, rows in rows_of.items():
            if rows.size == 0:
                alphas[cfg][r] = None
                continue
            a = M.fit_alpha(obs[rows][:, fit].ravel(), stitched[cfg][rows][:, fit].ravel())
            alphas[cfg][r] = rnd(a, 4)
            a_st[rows] = a
        m = score(obs, stitched[cfg], fcs[cfg], axis, a_st)
        m.pop("_per_station")
        metrics[cfg] = m
        for r, rows in rows_of.items():
            if rows.size == 0:
                continue
            sub = score(obs[rows], stitched[cfg][rows], {I: v[rows] for I, v in fcs[cfg].items()}, axis, a_st[rows])
            by_region[r][cfg] = {k: sub[k] for k in _KEYS}
            # base rates on held-out hours: a hit rate means little if the forecast is above 60 nearly all the time
            o, pr = obs[rows][:, held], (a_st[rows][:, None] * stitched[cfg][rows])[:, held]
            ok = ~np.isnan(o) & ~np.isnan(pr)
            by_region[r][cfg]["share_hours_obs_ge60"] = rnd(float(np.mean(o[ok] >= M.THRESH)) if ok.any() else None)
            by_region[r][cfg]["share_hours_pred_ge60"] = rnd(float(np.mean(pr[ok] >= M.THRESH)) if ok.any() else None)
    n = {r: int(rows.size) for r, rows in rows_of.items()}
    d = by_region["delhi_ncr"].get("B") or {}
    notes = [
        "EXPLORATORY, NOT PRE-REGISTERED. The pre-registered result is the pooled calibration (\"calibration\" and "
        "\"metrics\"); this block was added after seeing that one pooled alpha is dominated by noisy Punjab "
        "stations near the fires.",
        f"One alpha per region, fitted only on the fit period (25 Oct-5 Nov) with the same least-squares-through-"
        f"origin rule: delhi_ncr = {n['delhi_ncr']} DPCC Delhi stations, punjab_haryana = {n['punjab_haryana']} "
        "PPCB Punjab stations. Scored on 6-20 Nov with the same metric code and the same saved forecasts.",
        "Pearson r is computed on the raw model smoke, so it does not depend on alpha; only the threshold metrics "
        "(hit rate, false alarms, lead) and R2 can move. The Delhi alpha rests on 3 stations, so treat it as provisional.",
        f"Read the Delhi/NCR hit rate with care: on held-out hours the observed excess was >= 60 ug/m3 "
        f"{_pct(d.get('share_hours_obs_ge60'))} of the time and the regionally calibrated forecast (B) "
        f"{_pct(d.get('share_hours_pred_ge60'))} of the time, so a forecast that is high most of the time scores "
        "well on episodes without tracking them; the strongly negative R2 shows the magnitudes are off. Delhi's "
        "excess also contains local non-fire pollution that the larger alpha absorbs.",
        "The live pipeline uses these regional alphas for est. smoke PM2.5 (provisional calibration) in Delhi/NCR "
        "and Punjab/Haryana, and the pooled alpha everywhere else.",
    ]
    return {"label": LABEL, "regions": {"delhi_ncr": "Delhi + NCR districts", "punjab_haryana": "Punjab + Haryana"},
            "alphas": alphas, "metrics": metrics, "by_region": by_region, "n_stations": n, "notes": notes}
