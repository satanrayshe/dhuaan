from datetime import timedelta

import numpy as np

from dhuaan.backtest import regional, run


def test_exploratory_fits_per_region_on_fit_period_only():
    axis = [run.WIN_START + timedelta(hours=h) for h in range(int((run.WIN_END - run.WIN_START).total_seconds() // 3600) + 1)]
    fit = np.array([t <= run.FIT_END for t in axis])
    T = len(axis)
    st = np.ones((2, T))
    obs = np.vstack([np.full(T, 10.0), np.full(T, 0.5)])     # Delhi row: alpha 10, Punjab row: alpha 0.5
    obs[0, ~fit] = 999.0                                      # held-out values must not leak into the fit
    stitched = {"A": st, "B": st}
    fcs = {c: {run.FIRST_ISSUE: st} for c in ("A", "B")}
    kept = [{"region": "Delhi"}, {"region": "Punjab"}]
    ex = regional.exploratory(obs, stitched, fcs, axis, fit, kept, run.score, run._rnd)
    assert ex["label"] == "Exploratory - not pre-registered"
    assert ex["alphas"]["B"] == {"delhi_ncr": 10.0, "punjab_haryana": 0.5}
    assert set(ex["metrics"]) == {"A", "B"} and "_per_station" not in ex["metrics"]["B"]
    assert ex["by_region"]["delhi_ncr"]["B"]["share_hours_obs_ge60"] == 1.0
    assert ex["n_stations"] == {"delhi_ncr": 1, "punjab_haryana": 1}


def test_score_accepts_per_station_alpha():
    axis = [run.HELD_START + timedelta(hours=h) for h in range(30)]
    obs = np.zeros((2, 30))
    obs[0, 10:14] = 100
    st = np.zeros((2, 30))
    st[:, 10:14] = 10
    m = run.score(obs, st, {}, axis, np.array([10.0, 1.0]))  # row 1 stays below 60 -> no forecast episode
    assert (m["n_episodes"], m["n_hits"], m["n_forecast_episodes"]) == (1, 1, 1)
