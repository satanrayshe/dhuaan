"""Pre-registered backtest definitions (prep/01-project-spec.md, "Backtest"), as pure functions on hourly arrays.

All series are float arrays on one common hourly UTC axis; NaN = missing.
- excess(pm):          PM2.5 - trailing 7-day (168 h, current hour included) 10th percentile at the same station.
- episodes(x):         runs of >= 3 consecutive hours with x >= 60 (a missing hour breaks a run).
- hit:                 an observed episode is hit when the forecast is >= 60 at any hour in [start-6 h, end+6 h].
- false alarm:         a forecast episode (same 60 / 3 h rule on the forecast) that overlaps no observed episode
                       widened by +-6 h. FAR = false alarms / forecast episodes.
- lead time:           per hit episode, start - earliest issue time I (I <= start - 12 h) whose forecast crosses
                       60 inside the hit window at a forecast hour after I; median over episodes.
- calibration:         least squares through the origin, excess ~ alpha * C (alpha = sum xy / sum x^2).
- pearson_r, r2:       on all held-out station-hours with both values; r2 = 1 - SSE/SST using alpha * C.
"""
from __future__ import annotations

from typing import Iterable

import numpy as np

THRESH = 60.0
MIN_RUN_H = 3
TOL_H = 6
BASELINE_H = 168
BASELINE_PCT = 10.0
BASELINE_MIN_VALID = 72
MIN_LEAD_H = 12


def excess(pm: np.ndarray, window_h: int = BASELINE_H, pct: float = BASELINE_PCT,
           min_valid: int = BASELINE_MIN_VALID) -> np.ndarray:
    pm = np.asarray(pm, dtype=np.float64)
    out = np.full_like(pm, np.nan)
    for i in range(pm.size):
        if np.isnan(pm[i]):
            continue
        w = pm[max(0, i - window_h + 1): i + 1]
        w = w[~np.isnan(w)]
        if w.size >= min_valid:
            out[i] = pm[i] - np.percentile(w, pct)
    return out


def episodes(x: np.ndarray, thresh: float = THRESH, min_run: int = MIN_RUN_H) -> list[tuple[int, int]]:
    """[(start, end)] inclusive hour indices of runs with x >= thresh lasting >= min_run hours."""
    x = np.asarray(x, dtype=np.float64)
    above = np.where(np.isnan(x), False, x >= thresh)
    out, i, n = [], 0, x.size
    while i < n:
        if above[i]:
            j = i
            while j + 1 < n and above[j + 1]:
                j += 1
            if j - i + 1 >= min_run:
                out.append((i, j))
            i = j + 1
        else:
            i += 1
    return out


def is_hit(pred: np.ndarray, ep: tuple[int, int], thresh: float = THRESH, tol: int = TOL_H) -> bool:
    a, b = max(0, ep[0] - tol), min(len(pred) - 1, ep[1] + tol)
    w = np.asarray(pred[a: b + 1], dtype=np.float64)
    return bool(np.any(np.where(np.isnan(w), False, w >= thresh)))


def false_alarms(pred_eps: list[tuple[int, int]], obs_eps: list[tuple[int, int]], tol: int = TOL_H) -> int:
    n = 0
    for ps, pe in pred_eps:
        if not any(ps <= oe + tol and pe >= os_ - tol for os_, oe in obs_eps):
            n += 1
    return n


def lead_time(ep: tuple[int, int], issues: Iterable[tuple[int, np.ndarray]], thresh: float = THRESH,
              tol: int = TOL_H, min_lead: int = MIN_LEAD_H) -> int | None:
    """issues: (issue_index, forecast on the common axis, NaN outside the forecast range).
    Returns start - earliest qualifying issue index (hours), or None."""
    best = None
    for ii, fc in issues:
        if ii > ep[0] - min_lead:
            continue
        a, b = max(ii + 1, ep[0] - tol), min(len(fc) - 1, ep[1] + tol)
        if a > b:
            continue
        w = np.asarray(fc[a: b + 1], dtype=np.float64)
        if np.any(np.where(np.isnan(w), False, w >= thresh)):
            lead = ep[0] - ii
            best = lead if best is None else max(best, lead)
    return best


def fit_alpha(obs: np.ndarray, c: np.ndarray) -> float:
    o, m = np.asarray(obs, dtype=np.float64), np.asarray(c, dtype=np.float64)
    ok = ~np.isnan(o) & ~np.isnan(m)
    den = float(np.sum(m[ok] ** 2))
    return float(np.sum(o[ok] * m[ok]) / den) if den > 0 else float("nan")


def pearson(a: np.ndarray, b: np.ndarray) -> float | None:
    a, b = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    ok = ~np.isnan(a) & ~np.isnan(b)
    if ok.sum() < 3 or np.std(a[ok]) == 0 or np.std(b[ok]) == 0:
        return None
    return float(np.corrcoef(a[ok], b[ok])[0, 1])


def r2(obs: np.ndarray, pred: np.ndarray) -> float | None:
    o, p = np.asarray(obs, dtype=np.float64), np.asarray(pred, dtype=np.float64)
    ok = ~np.isnan(o) & ~np.isnan(p)
    if ok.sum() < 3:
        return None
    sst = float(np.sum((o[ok] - o[ok].mean()) ** 2))
    return None if sst == 0 else 1.0 - float(np.sum((o[ok] - p[ok]) ** 2)) / sst
