"""Offline tests for the FIRMS static-hotspot mask."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from dhuaan.ingest import firms
from dhuaan.model.types import Fire

T = datetime(2025, 11, 10, 8, 0, tzinfo=timezone.utc)


def fire(lat: float, lon: float, sensor: str = "VIIRS_NOAA20") -> Fire:
    return Fire(id=firms.fire_id(sensor, T, lat, lon), lat=lat, lon=lon, time_utc=T, frp_mw=5.0, sensor=sensor,
                confidence="nominal")


def test_mask_drops_within_radius_only():
    hs = [(29.455, 76.865)]                      # Panipat refinery cell centre
    near = fire(29.459, 76.868)                  # ~0.5 km
    edge = fire(29.455 + 0.0085, 76.865)         # ~0.94 km north
    far = fire(29.455 + 0.012, 76.865)           # ~1.3 km north
    east = fire(29.455, 76.865 + 0.012)          # ~1.16 km east (cos(lat) shrinks lon degrees)
    kept, masked = firms.mask_static([near, edge, far, east], hs, radius_km=1.0)
    assert {f.id for f in masked} == {near.id, edge.id}
    assert {f.id for f in kept} == {far.id, east.id}


def test_mask_crosses_cell_boundaries_and_keeps_geo_sensors():
    hs = [(30.0049, 75.0049)]                    # near a 0.01-degree cell corner
    a = fire(30.0105, 75.0105)                   # different cell, ~0.8 km away
    g = fire(30.005, 75.005, sensor="GK2A")      # coarse geostationary pixel: never masked
    kept, masked = firms.mask_static([a, g], hs)
    assert masked == [a] and kept == [g]


def test_mask_empty_hotspots_is_identity():
    fs = [fire(30.0, 75.0)]
    assert firms.mask_static(fs, []) == (fs, [])


def test_load_static_hotspots(tmp_path):
    p = tmp_path / "hs.json"
    p.write_text(json.dumps({"hotspots": [{"lat": 29.455, "lon": 76.865, "days": 65}]}))
    assert firms.load_static_hotspots(p) == [(29.455, 76.865)]
    assert firms.load_static_hotspots(tmp_path / "missing.json") == []


def test_fetch_recent_reports_masked(monkeypatch):
    fs = [fire(29.459, 76.868), fire(31.0, 75.0)]
    monkeypatch.setattr(firms, "fetch_source",
                        lambda src, days=2, day=None, use_cache=None: fs if src == "VIIRS_NOAA20_NRT" else [])
    monkeypatch.setattr(firms, "load_static_hotspots", lambda path=None: [(29.455, 76.865)])
    fires, st = firms.fetch_recent(2)
    assert [f.lat for f in fires] == [31.0]
    s = {x["name"]: x for x in st}["FIRMS VIIRS_NOAA20_NRT"]
    assert s["count"] == 1 and "1 masked as static hotspots" in s["note"]
    fires2, _ = firms.fetch_recent(2, mask=False)
    assert len(fires2) == 2


def test_shipped_hotspots_cover_known_refineries():
    hs = firms.load_static_hotspots()
    if not hs:
        return
    _, masked = firms.mask_static([fire(29.456, 76.866), fire(29.906, 74.956)], hs)
    assert len(masked) == 2   # Panipat refinery, HMEL Bathinda refinery
