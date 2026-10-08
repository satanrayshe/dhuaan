"""Offline tests for the backtest definitions, GK2A parsing, hotspot finder and afternoon ratio."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from dhuaan.backtest import gk2a, hotspots, inputs, metrics as M, ratio, run
from dhuaan.model.types import Fire

UTC = timezone.utc
NAN = np.nan


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network call in an offline test")
    monkeypatch.setattr("requests.request", boom)


# ---------- metrics (pre-registered definitions) ----------

def test_excess_trailing_p10():
    pm = np.full(200, 50.0)
    pm[180:] = 150.0
    ex = M.excess(pm)
    assert np.isnan(ex[:71]).all() and ex[71] == 0.0          # needs 72 valid hours
    assert ex[190] == pytest.approx(100.0)                     # p10 of the trailing 168 h is still 50
    pm2 = pm.copy()
    pm2[100] = NAN
    assert np.isnan(M.excess(pm2)[100])


def test_episodes_need_three_consecutive_hours():
    x = np.array([0, 60, 61, 70, 0, 80, 90, NAN, 99, 99, 99, 59, 60, 60, 60])
    assert M.episodes(x) == [(1, 3), (8, 10), (12, 14)]


def test_hit_window_and_false_alarms():
    pred = np.zeros(40)
    pred[22] = 70                     # 6 h after the end of an episode at 10..16
    assert M.is_hit(pred, (10, 16))
    pred[22] = 0
    pred[23] = 70                     # 7 h after: miss
    assert not M.is_hit(pred, (10, 16))
    assert M.false_alarms([(20, 24), (30, 33)], [(10, 16)]) == 1   # 20..24 is within +-6 h of the episode


def test_lead_time_earliest_issue_at_least_12h_ahead():
    n = 100
    ep = (60, 64)
    fc_early = np.full(n, NAN)
    fc_early[0:73] = 0
    fc_early[58] = 80                 # issued at 0: lead 60 h, crossing inside the window
    fc_late = np.full(n, NAN)
    fc_late[50:] = 0
    fc_late[61] = 80                  # issued at 50: only 10 h ahead -> ignored
    fc_miss = np.full(n, NAN)
    fc_miss[24:97] = 0                # issued at 24: no crossing
    assert M.lead_time(ep, [(0, fc_early), (24, fc_miss), (50, fc_late)]) == 60
    assert M.lead_time(ep, [(24, fc_miss), (50, fc_late)]) is None


def test_alpha_pearson_r2():
    c = np.array([1.0, 2.0, 3.0, NAN, 4.0])
    obs = np.array([2.0, 4.0, 6.0, 5.0, 8.0])
    assert M.fit_alpha(obs, c) == pytest.approx(2.0)
    assert M.pearson(obs, c) == pytest.approx(1.0)
    assert M.r2(obs, 2 * c) == pytest.approx(1.0)
    assert M.pearson(obs, np.zeros(5)) is None


def test_stitch_uses_lead_12_to_35():
    axis = [datetime(2025, 11, 1, tzinfo=UTC) + timedelta(hours=h) for h in range(48)]
    assert run.issue_for(axis[11]) == datetime(2025, 10, 31, tzinfo=UTC)   # 11Z -> previous day's 00Z, lead 35
    assert run.issue_for(axis[12]) == datetime(2025, 11, 1, tzinfo=UTC)    # 12Z -> same day's 00Z, lead 12
    fc = {datetime(2025, 10, 31, tzinfo=UTC): np.full((1, 48), 1.0),
          datetime(2025, 11, 1, tzinfo=UTC): np.full((1, 48), 2.0)}
    s = run.stitch(fc, axis)
    assert s[0, 11] == 1.0 and s[0, 12] == 2.0 and s[0, 35] == 2.0
    assert np.isnan(s[0, 36])                                              # needs the 2 Nov issue (absent)


def test_score_counts():
    axis = [run.HELD_START + timedelta(hours=h) for h in range(60)]
    obs = np.zeros((1, 60))
    obs[0, 20:25] = 100
    st = np.zeros((1, 60))
    st[0, 18:22] = 50                 # x alpha 2 = 100 -> hit
    st[0, 45:49] = 50                 # forecast episode with nothing observed -> false alarm
    fc = {run.HELD_START - timedelta(hours=12): st.copy()}
    m = run.score(obs, st, fc, axis, alpha=2.0)
    assert (m["n_episodes"], m["n_hits"], m["hit_rate"]) == (1, 1, 1.0)
    assert (m["n_forecast_episodes"], m["n_false_alarms"], m["false_alarm_ratio"]) == (2, 1, 0.5)
    assert m["median_lead_h"] == 32.0


# ---------- inputs ----------

def test_hourly_pm_period_ending_and_validity():
    axis = [datetime(2025, 11, 11, 0, tzinfo=UTC), datetime(2025, 11, 11, 1, tzinfo=UTC)]
    recs = [{"t": "2025-11-11T00:15:00Z", "value": 100.0}, {"t": "2025-11-11T01:00:00Z", "value": 200.0},
            {"t": "2025-11-11T01:15:00Z", "value": 0.0}, {"t": "2025-11-11T01:30:00Z", "value": 5000.0}]
    out = inputs.hourly_pm(recs, axis)
    assert out[0] == 150.0 and np.isnan(out[1])


# ---------- GK2A ----------

GK_TXT = """FILE_NAME = GK2-AMI_FireHotspotsData_2025_10-11_Punjab_India_v1.txt
FORMAT:  1=Year 2=Month ...
2025 11 10 13 00  75.0000  30.5000   7.1 304.6 294.3  1
2025 11 10 16 00  75.1000  30.6000   7.1 304.6 294.3  2
2025 11 10 17 00  75.2000  30.7000   7.1 304.6 294.3  3
2025 11 10 18 00  75.3000  30.8000   7.1 304.6 294.3  2
"""


def test_gk2a_parse_ist_and_share():
    rows = gk2a.parse(GK_TXT, "Punjab")
    assert len(rows) == 4 and rows[0]["t_ist"].utcoffset() == timedelta(hours=5, minutes=30)
    share, late, n = gk2a.afternoon_share(rows)
    assert (late, n) == (3, 4) and share == 0.75
    fires = gk2a.to_fires(rows)                       # flag 1 dropped
    assert len(fires) == 3 and all(f.sensor == "GK2A" and f.frp_mw is None for f in fires)
    assert fires[0].time_utc == datetime(2025, 11, 10, 10, 30, tzinfo=UTC)   # 16:00 IST
    assert fires[1].confidence == "high"


# ---------- hotspots ----------

def _f(lat: float, lon: float, day: int, sensor: str = "VIIRS_SNPP") -> Fire:
    t = datetime(2025, 3, 1, 8, tzinfo=UTC) + timedelta(days=day)
    return Fire(id=f"{sensor}_{day}_{lat}_{lon}", lat=lat, lon=lon, time_utc=t, frp_mw=3.0, sensor=sensor,
                confidence="nominal")


def test_find_hotspots_distinct_days():
    fires = [_f(29.4551, 76.8652, d) for d in range(8)]            # 8 distinct days -> hotspot
    fires += [_f(29.4553, 76.8655, 0, "VIIRS_NOAA20")] * 3          # same day again: no extra credit
    fires += [_f(30.1001, 75.1001, d % 7) for d in range(20)]       # many detections but only 7 days
    hs = hotspots.find_hotspots(fires)
    assert len(hs) == 1 and hs[0]["days"] == 8 and hs[0]["lat"] == 29.455 and hs[0]["lon"] == 76.865


# ---------- afternoon ratio ----------

def test_compute_ratio_shrinks_and_caps():
    def district_of(lat: float, lon: float) -> tuple[str, str]:
        if lon < 74.5:
            return "Fazilka", "Punjab"
        return ("Ludhiana", "Punjab") if lon < 76 else ("Delhi", "Delhi")
    t_late = datetime(2025, 11, 1, 11, 0, tzinfo=UTC)    # 16:30 IST
    t_early = datetime(2025, 11, 1, 7, 0, tzinfo=UTC)    # 12:30 IST
    gk = [Fire(f"g{i}", 30.0, 74.0, t_late, None, "GK2A", "nominal") for i in range(100)]
    gk += [Fire(f"e{i}", 30.0, 74.0, t_early, None, "GK2A", "nominal") for i in range(50)]   # before 16 IST
    pol = [Fire(f"p{i}", 30.0, 74.0, t_early, 5.0, "VIIRS_SNPP", "nominal") for i in range(10)]
    pol += [Fire(f"q{i}", 30.9, 75.8, t_early, 5.0, "MODIS", "nominal") for i in range(90)]
    pol += [Fire(f"d{i}", 28.6, 77.2, t_early, 5.0, "MODIS", "nominal") for i in range(500)]  # not Punjab/Haryana
    r, rows = ratio.compute_ratio(gk, pol, district_of)
    assert r["_default"] == 1.0                                         # pooled 100 / 100
    assert r["Fazilka"] == pytest.approx((100 + 30) / (10 + 30), abs=1e-3)   # raw 10 -> shrunk to 3.25
    assert r["Ludhiana"] == ratio.CAP_LO                                # (0 + 30) / 120 = 0.25
    assert "Delhi" not in r and len(rows) == 2
