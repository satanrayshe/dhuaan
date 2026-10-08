"""Offline tests for the ingest clients (no network: fixtures + monkeypatching)."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from dhuaan.ingest import common, firms, lsasaf, openaq, openmeteo

FX = Path(__file__).parent / "fixtures"
UTC = timezone.utc


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network call in an offline test")
    monkeypatch.setattr("requests.request", boom)
    monkeypatch.setattr("requests.get", boom)
    monkeypatch.setattr("requests.post", boom)


# ---------- FIRMS ----------

def test_firms_parse_viirs():
    fires = firms.parse_csv((FX / "firms_viirs.csv").read_text(), "VIIRS_SNPP_NRT")
    assert len(fires) == 4  # one row outside DOMAIN dropped
    f = fires[0]
    assert f.sensor == "VIIRS_SNPP" and f.confidence == "nominal" and f.frp_mw == pytest.approx(2.69)
    assert f.time_utc == datetime(2026, 10, 7, 8, 20, tzinfo=UTC)  # "820" -> 08:20Z
    assert fires[1].confidence == "high"
    assert fires[3].frp_mw is None and fires[3].confidence == "low"
    assert len(firms.dedupe(fires)) == 3  # exact repeat removed


def test_firms_parse_modis_confidence():
    fires = firms.parse_csv((FX / "firms_modis.csv").read_text(), "MODIS_NRT")
    assert [f.confidence for f in fires] == ["nominal", "high", "low"]
    assert all(f.sensor == "MODIS" for f in fires)


def test_firms_empty_and_error_bodies():
    assert firms.parse_csv("", "MODIS_NRT") == []
    with pytest.raises(RuntimeError):
        firms.parse_csv("Invalid MAP_KEY.", "MODIS_NRT")


@pytest.mark.parametrize("raw,exp", [("l", "low"), ("n", "nominal"), ("h", "high"), ("29", "low"), ("30", "nominal"),
                                     ("80", "high"), ("", "nominal"), ("x", "nominal")])
def test_confidence(raw, exp):
    assert firms.normalise_confidence(raw) == exp


def test_firms_recent_records_failures(monkeypatch):
    good = firms.parse_csv((FX / "firms_viirs.csv").read_text(), "VIIRS_SNPP_NRT")

    def fake(src, days=2, day=None, use_cache=None):
        if src == "MODIS_NRT":
            raise RuntimeError("HTTP 500")
        return good if src == "VIIRS_SNPP_NRT" else []
    monkeypatch.setattr(firms, "fetch_source", fake)
    fires, st = firms.fetch_recent(2)
    assert len(fires) == 3
    by = {s["name"]: s for s in st}
    assert by["FIRMS MODIS_NRT"]["ok"] is False and by["FIRMS VIIRS_SNPP_NRT"]["count"] == 4
    assert by["FIRMS VIIRS_SNPP_NRT"]["latest_obs_utc"].endswith("Z")


def test_firms_archive_source_choice_and_chunks(monkeypatch):
    avail = {"VIIRS_SNPP_SP": (date(2012, 1, 20), date(2026, 6, 30)), "VIIRS_SNPP_NRT": (date(2026, 7, 1), date(2026, 10, 7)),
             "VIIRS_NOAA21_NRT": (date(2024, 1, 17), date(2026, 10, 7))}
    assert firms.archive_source_for("VIIRS_SNPP", date(2025, 10, 25), date(2025, 11, 20), avail) == "VIIRS_SNPP_SP"
    assert firms.archive_source_for("VIIRS_NOAA21", date(2025, 10, 25), date(2025, 11, 20), avail) == "VIIRS_NOAA21_NRT"
    assert firms.archive_source_for("VIIRS_SNPP", date(2026, 8, 1), date(2026, 8, 3), avail) == "VIIRS_SNPP_NRT"
    assert firms.archive_source_for("MODIS", date(2025, 10, 25), date(2025, 11, 20), avail) is None
    calls = []
    monkeypatch.setattr(firms, "availability", lambda use_cache=None: avail)
    monkeypatch.setattr(firms, "fetch_source", lambda s, days, d, use_cache=None: calls.append((s, days, d)) or [])
    firms.fetch_archive(date(2025, 10, 25), date(2025, 11, 5), sensors=("VIIRS_SNPP",))
    assert calls == [("VIIRS_SNPP_SP", 5, date(2025, 10, 25)), ("VIIRS_SNPP_SP", 5, date(2025, 10, 30)),
                     ("VIIRS_SNPP_SP", 2, date(2025, 11, 4))]


def test_redact_hides_map_key():
    assert "SECRET" not in common.redact("https://firms.modaps.eosdis.nasa.gov/api/area/csv/SECRET/MODIS_NRT/1,2,3,4/2")


def test_fetch_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(common.settings.__class__, "cache_dir", property(lambda self: tmp_path), raising=False)
    p = common.cache_path("t", "k")
    p.write_bytes(b"cached")
    assert common.fetch("https://example.invalid/x", namespace="t", cache_key="k", use_cache=True) == b"cached"


# ---------- Open-Meteo ----------

def _resp(times, val):
    h = {"time": [t.strftime("%Y-%m-%dT%H:%M") for t in times]}
    for v in openmeteo.UV_VARS:
        h[v] = [val] * len(times)
    h["boundary_layer_height"][0] = None  # a gap to fill
    return {"hourly": h}


def test_openmeteo_grid_and_weight():
    lons, lats = openmeteo.grid()
    assert lons.shape == (27,) and lats.shape == (20,)
    assert lons[0] == 72.5 and lons[-1] == 79.0 and lats[0] == 28.0 and lats[-1] == 32.75
    assert openmeteo.call_weight(540, 7, 5) == 540
    assert openmeteo.call_weight(10, 20, 28) == 40


def test_openmeteo_assemble_slices_and_fills():
    t0 = datetime(2026, 10, 8, 10, tzinfo=UTC)
    times = openmeteo.run_times(t0)
    assert len(times) == 97 and times[0] == t0 - timedelta(hours=24) and times[-1] == t0 + timedelta(hours=72)
    api_times = [datetime(2026, 10, 7, tzinfo=UTC) + timedelta(hours=h) for h in range(120)]
    lons, lats = np.array([75.0, 75.25]), np.array([30.0, 30.25, 30.5])
    resp = [_resp(api_times, float(k)) for k in range(6)]
    met = openmeteo.assemble(resp, lons, lats, times)
    assert met.u10.shape == (97, 3, 2)
    assert met.u10[0, 1, 0] == 2.0 and met.v850[5, 2, 1] == 5.0  # row-major: k = j*nx + i
    assert not np.isnan(met.blh).any() and met.blh.min() >= 10.0
    assert met.times == times


def test_openmeteo_speed_direction_fallback():
    t = [datetime(2026, 10, 8, h, tzinfo=UTC) for h in range(3)]
    h = {"time": [x.strftime("%Y-%m-%dT%H:%M") for x in t], "boundary_layer_height": [500] * 3}
    for lv in openmeteo.LEVELS:
        h[f"wind_speed_{lv}"] = [10.0] * 3
        h[f"wind_direction_{lv}"] = [270.0] * 3  # from the west -> blowing east
    met = openmeteo.assemble([{"hourly": h}], np.array([75.0]), np.array([30.0]), t, speed_direction=True)
    assert met.u10[0, 0, 0] == pytest.approx(10.0, abs=1e-4) and met.v10[0, 0, 0] == pytest.approx(0.0, abs=1e-4)


def test_openmeteo_wrong_count_raises():
    with pytest.raises(RuntimeError):
        openmeteo.assemble([], np.array([75.0]), np.array([30.0]), [datetime(2026, 1, 1, tzinfo=UTC)])


# ---------- LSA SAF ----------

def test_lsasaf_listing_and_hourly_pick():
    slots = lsasaf.parse_listing((FX / "lsasaf_listing.html").read_text())
    assert len(slots) == 5  # QualityProduct ignored
    picks = lsasaf.hourly_pick(slots, datetime(2026, 10, 8, 9, tzinfo=UTC), datetime(2026, 10, 8, 11, tzinfo=UTC))
    assert [t.strftime("%H%M") for t, _ in picks] == ["0900", "1015"]


def _make_h5(path: Path, rows):
    import h5py
    lat, lon, frp, conf, ps, acq = (np.array(c) for c in zip(*rows))
    with h5py.File(path, "w") as f:
        for name, arr, scale, dt, miss in [("LATITUDE", lat * 100, 100.0, "i2", 19000), ("LONGITUDE", lon * 100, 100.0, "i2", 19000),
                                           ("FRP", frp * 10, 10.0, "i4", -999), ("FIRE_CONFIDENCE", conf * 100, 100.0, "i2", -999),
                                           ("PIXEL_SIZE", ps * 100, 100.0, "i2", -999), ("ACQTIME", acq, 1.0, "i2", -999)]:
            d = f.create_dataset(name, data=np.round(arr).astype(dt))
            d.attrs["SCALING_FACTOR"] = scale
            d.attrs["MISSING_VALUE"] = miss


def test_lsasaf_parse_h5(tmp_path):
    p = tmp_path / "x.h5"
    _make_h5(p, [(30.27, 76.04, 55.3, 0.9, 4.6, 1107), (10.0, 76.0, 20.0, 0.5, 3.0, 1107),
                 (29.5, 75.0, 30.0, 0.2, 4.4, 1108)])
    fires, ps = lsasaf.parse_h5(p.read_bytes(), datetime(2026, 10, 8, 11, 0, tzinfo=UTC))
    assert len(fires) == 2
    f = fires[0]
    assert f.sensor == "MSG_IODC" and f.frp_mw == pytest.approx(55.3) and f.confidence == "high"
    assert f.time_utc == datetime(2026, 10, 8, 11, 7, tzinfo=UTC) and f.lat == pytest.approx(30.27)
    assert fires[1].confidence == "low" and ps == pytest.approx(4.5)


def test_lsasaf_needs_credentials(monkeypatch):
    monkeypatch.setattr(lsasaf, "settings", type("S", (), {"lsasaf_username": "", "lsasaf_password": ""})())
    with pytest.raises(RuntimeError):
        lsasaf.fetch_recent()


# ---------- OpenAQ ----------

def _stations():
    return openaq.parse_locations(json.loads((FX / "openaq_locations.json").read_text())["results"])


def test_openaq_parse_locations():
    st = _stations()
    assert [s["id"] for s in st] == [5544, 10831]  # out-of-domain and no-pm25 dropped
    assert st[1]["pm25_sensor_ids"] == [99, 12235092] and st[1]["is_monitor"]


def test_openaq_latest_near(monkeypatch):
    st = _stations()
    now = datetime(2026, 10, 8, 10, tzinfo=UTC)
    monkeypatch.setattr(openaq, "latest_pm25", lambda s: (90.04, "2026-10-07T14:30:00Z"))
    r = openaq.latest_near(28.73, 77.11, stations=st, now=now)
    assert set(r) == {"station_id", "name", "lat", "lon", "pm25", "unit", "measured_utc", "distance_km"}
    assert r["station_id"] == 10831 and r["pm25"] == 90.0 and r["distance_km"] == pytest.approx(1.0, abs=0.2)
    assert openaq.latest_near(32.5, 73.0, stations=st, now=now) is None  # nothing within 50 km
    monkeypatch.setattr(openaq, "latest_pm25", lambda s: (90.0, "2026-10-05T00:00:00Z"))  # too old
    assert openaq.latest_near(28.73, 77.11, stations=st, now=now) is None


def test_openaq_archive_parse_utc():
    rows = openaq.parse_archive_csv((FX / "openaq_archive.csv").read_text(encoding="utf-8"))
    assert [r["t"] for r in rows] == ["2025-11-04T19:15:00Z", "2025-11-04T19:30:00Z"]
    assert rows[1]["value"] == 180.5


def test_openaq_archive_missing_day(monkeypatch):
    def nf(*a, **k):
        raise RuntimeError("x failed: HTTP 404: nope")
    monkeypatch.setattr(openaq, "fetch", nf)
    assert openaq.fetch_archive(235, date(2025, 11, 5)) == []


def test_openaq_stations_file_shape():
    st = openaq.load_stations()
    assert len(st) > 50
    assert {"id", "name", "lat", "lon", "provider"} <= set(st[0])
