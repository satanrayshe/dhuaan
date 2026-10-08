from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from dhuaan.agent import rules

T0 = datetime(2026, 10, 8, 0, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("pm,cat", [(0, "good"), (30, "good"), (30.4, "good"), (30.6, "satisfactory"), (60, "satisfactory"),
                                    (61, "moderate"), (90, "moderate"), (91, "poor"), (120, "poor"), (121, "very_poor"),
                                    (250, "very_poor"), (251, "severe"), (900, "severe")])
def test_naqi_category(pm, cat):
    assert rules.naqi_category(pm) == cat


@pytest.mark.parametrize("pm,lvl", [(10, "ok"), (60, "ok"), (61, "limit"), (120, "limit"), (121, "indoors"), (400, "indoors")])
def test_outdoor_level(pm, lvl):
    assert rules.outdoor_level(pm) == lvl


def test_baseline_fresh_stale_missing():
    now = datetime(2026, 10, 8, 6, 0, tzinfo=timezone.utc)
    fresh = {"pm25": 82.0, "measured_utc": "2026-10-08T04:00:00Z", "name": "Punjab Agricultural University"}
    assert rules.baseline_pm25(fresh, now)[0] == 82.0
    assert "observed" in rules.baseline_pm25(fresh, now)[1]
    stale = {**fresh, "measured_utc": "2026-10-07T23:00:00Z"}
    assert rules.baseline_pm25(stale, now)[0] == 60.0
    assert rules.baseline_pm25(None, now)[0] == 60.0
    assert rules.baseline_pm25({"pm25": None, "measured_utc": "2026-10-08T05:00:00Z"}, now)[0] == 60.0


def test_est_total():
    assert rules.est_total(60, 1.0, 95.4) == 155
    assert rules.est_total(60, 2.0, 10) == 80
    assert rules.est_total(60, 1.0, -3) == 60
    assert rules.est_total(60, 1.0, None) is None


def test_value_at_interpolates_half_hours():
    arr = [float(i) for i in range(97)]
    t = datetime(2026, 10, 8, 7, 0, tzinfo=rules.IST)  # 01:30 UTC -> index 25.5
    assert rules.value_at(arr, T0, t) == pytest.approx(25.5)
    assert rules.series_index(T0, t) == 25
    assert rules.value_at(arr, T0, datetime(2026, 10, 12, tzinfo=timezone.utc)) is None


def test_default_school_date():
    assert rules.default_school_date(datetime(2026, 10, 8, 3, 0, tzinfo=timezone.utc)) == date(2026, 10, 8)   # 08:30 IST
    assert rules.default_school_date(datetime(2026, 10, 8, 9, 0, tzinfo=timezone.utc)) == date(2026, 10, 9)   # 14:30 IST


def _place(series):
    return {"id": "s1", "name": "S", "district": "D", "t0_utc": "2026-10-08T00:00:00Z", "series": series,
            "p10": [v * 0.5 for v in series], "p90": [v * 2 for v in series]}


def test_school_day_plan_levels_and_summary():
    s = [0.0] * 97
    # 9 Oct 07:00-13:00 IST = 01:30-07:30 UTC = index 49.5..55.5
    for i in range(49, 57):
        s[i] = 80.0
    s[50] = s[51] = 30.0
    p = rules.school_day_plan(_place(s), 1.0, None, "2026-10-09", now=T0)
    assert [r["hour_ist"] for r in p["plan"]] == ["07:00", "08:00", "09:00", "10:00", "11:00", "12:00", "13:00"]
    est = [r["est_pm25"] for r in p["plan"]]
    assert est == [115, 90, 115, 140, 140, 140, 140]
    assert [r["outdoor"] for r in p["plan"]] == ["limit", "limit", "limit", "indoors", "indoors", "indoors", "indoors"]
    assert p["summary"]["overall_outdoor"] == "indoors"
    assert p["summary"]["worst_est_pm25"] == 140 and p["summary"]["worst_category"] == "very_poor"
    assert p["summary"]["guidance"] == rules.OUTDOOR_GUIDANCE["indoors"]
    assert p["plan"][3]["est_pm25_low"] == 100 and p["plan"][3]["est_pm25_high"] == 220
    assert p["sources"] == rules.SOURCES and p["baseline_pm25"] == 60.0


def test_school_day_plan_outside_run():
    p = rules.school_day_plan(_place([1.0] * 97), 1.0, None, "2026-10-20", now=T0)
    assert all(r["est_pm25"] is None for r in p["plan"])
    assert "note" in p["summary"]


def test_school_day_plan_uses_fresh_observation():
    obs = {"pm25": 100.0, "measured_utc": "2026-10-08T00:00:00Z", "name": "X"}
    p = rules.school_day_plan(_place([0.0] * 97), 1.0, obs, "2026-10-08", now=datetime(2026, 10, 8, 2, tzinfo=timezone.utc))
    assert {r["outdoor"] for r in p["plan"]} == {"limit"}
