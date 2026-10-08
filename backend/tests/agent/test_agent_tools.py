from __future__ import annotations

import sys
import types

from dhuaan.agent import data, tools


def test_data_access_and_cache(store):
    assert data.run_id() == "20261008T00Z"
    assert data.alpha() == 1.0
    assert len(data.index()) == 5
    assert data.place("town_khanna")["name"] == "Khanna"
    assert data.place("../meta") is None and data.place("") is None
    assert data.cluster("c0002")["district"] == "Barnala"
    # cached: removing the file does not change the answer until the cache is cleared
    (store.root / "latest" / "places" / "town_khanna.json").unlink()
    assert data.place("town_khanna") is not None
    data.clear_cache()
    assert data.place("town_khanna") is None


def test_search_ranking(store):
    assert data.search("khanna")[0]["id"] == "town_khanna"
    assert data.search("Sunrise")[0]["id"] == "sch_demo_sunrise"
    lud = [p["id"] for p in data.search("ludhiana")]
    assert lud[0] == "city_ludhiana" and set(lud) >= {"town_khanna", "sch_demo_sunrise"}
    assert data.search("zzz") == [] and data.search("") == []
    assert len(data.search("punjab", limit=2)) == 2


def test_forecast_tool(store):
    r = tools.get_smoke_forecast("sch_demo_sunrise", 72)
    assert r["arrival_ist"] == "2026-10-09 05:30 IST"
    assert r["peak"]["time_ist"] == "2026-10-09 13:30 IST"
    assert r["peak"]["est_pm25"] == 156 and r["peak"]["est_pm25_band"] == [117, 199]
    assert r["peak"]["category"] == "very_poor"
    assert r["run"]["stale"] is False and r["run"]["run_age_hours"] == 3.0
    assert r["from_ist"] == "08 Oct 08:30" and len(r["series_3h"]) == 24  # run ends at t0+72 h
    assert "NOT yet calibrated" in r["uncertainty"]
    assert tools.get_smoke_forecast("nope")["error"].startswith("unknown place_id")


def test_attribution_and_clusters(store):
    a = tools.get_attribution("town_khanna")
    assert a["districts"][0] == {"district": "Sangrur", "state": "Punjab", "share_pct": 34}
    assert a["top_clusters"][0]["near"] == "Bhawanigarh"
    c = tools.get_fire_clusters()
    assert [x["cluster_id"] for x in c["clusters"]] == ["c0001", "c0002", "c0003", "c0004"]
    assert tools.get_fire_clusters(district="barnala")["count"] == 1
    assert tools.get_fire_clusters(limit=2)["count"] == 2


def test_school_plan_tool(store):
    r = tools.get_school_day_plan("sch_demo_sunrise", "2026-10-09")
    assert r["summary"]["overall_outdoor"] == "indoors"
    assert r["plan"][0]["hour_ist"] == "07:00"
    assert tools.get_school_day_plan("sch_demo_sunrise", "9 Oct")["error"]


def test_freshness(store):
    r = tools.get_data_freshness()
    assert r["run_id"] == "20261008T00Z" and r["stale"] is False
    assert any(s["ok"] is False for s in r["sources"])


def test_air_quality_now_handles_missing_module(store, monkeypatch):
    assert tools.get_air_quality_now("town_khanna")["available"] is False


_ORIG_OBSERVED = tools.observed_near  # captured before the store fixture stubs it out


def test_air_quality_now_with_openaq(store, monkeypatch):
    fake = types.ModuleType("dhuaan.ingest.openaq")
    fake.latest_near = lambda lat, lon, radius_km=50: {
        "station_id": "s1", "name": "Ludhiana PAU", "lat": 30.9, "lon": 75.8, "pm25": 97.6, "unit": "µg/m³",
        "measured_utc": "2026-10-08T02:00:00Z", "distance_km": 12.34}
    import dhuaan.ingest as ing
    monkeypatch.setitem(sys.modules, "dhuaan.ingest.openaq", fake)
    monkeypatch.setattr(ing, "openaq", fake, raising=False)
    monkeypatch.setattr(tools, "observed_near", _ORIG_OBSERVED)
    tools._obs_cache.clear()
    r = tools.get_air_quality_now("town_khanna")
    assert r["available"] and r["pm25"] == 98 and r["category"] == "poor" and r["age_hours"] == 1.0
    assert r["measured_ist"] == "2026-10-08 07:30 IST" and r["stale"] is False
    # the fresh observation becomes the plan baseline
    plan = tools.get_school_day_plan("town_khanna", "2026-10-08")
    assert plan["baseline_pm25"] == 97.6 and "observed" in plan["baseline_basis"]
    tools._obs_cache.clear()


def test_tool_summaries(store):
    for name, args in [("search_place", ("khanna",)), ("get_smoke_forecast", ("town_khanna",)),
                       ("get_attribution", ("town_khanna",)), ("get_fire_clusters", ()),
                       ("get_school_day_plan", ("sch_demo_sunrise", "2026-10-09")), ("get_data_freshness", ())]:
        fn = getattr(tools, name)
        s = tools.summarize(name, fn(*args))
        assert s and s != name, name
