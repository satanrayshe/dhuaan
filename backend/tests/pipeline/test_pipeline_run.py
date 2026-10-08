"""Offline pipeline tests: serialisation, publish(), run_local CLI and Lambda handlers with stubs."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from dhuaan.ingest.common import source_status
from dhuaan.model.types import Fire, MetField, Receptor
from dhuaan.pipeline import core, handlers, run_local
from dhuaan.store import LocalStore

UTC = timezone.utc
T0 = datetime(2026, 10, 8, 6, tzinfo=UTC)
META_KEYS = {"run_id", "t0_utc", "generated_utc", "model_version", "members", "afternoon_mode", "alpha", "calibrated",
             "arrival_threshold", "scale", "domain", "sources"}


def _met() -> MetField:
    lons, lats = np.arange(72.5, 79.01, 0.25), np.arange(28.0, 32.76, 0.25)
    shape = (97, len(lats), len(lons))
    z = np.zeros(shape, dtype=np.float32)
    return MetField(lons=lons, lats=lats, times=[T0 + timedelta(hours=h) for h in range(-24, 73)],
                    u10=z + 1, v10=z, u925=z + 2, v925=z, u850=z + 3, v850=z, blh=z + 500)


FIRES = [Fire("VIIRS_SNPP_202610070812_30.2670_76.0410", 30.267, 76.041, datetime(2026, 10, 7, 8, 12, tzinfo=UTC), 12.5,
              "VIIRS_SNPP", "high"),
         Fire("MSG_IODC_202610071107_30.27_76.04", 30.27, 76.04, datetime(2026, 10, 7, 11, 7, tzinfo=UTC), None, "MSG_IODC", "low")]
SOURCES = [source_status("FIRMS VIIRS_SNPP_NRT", ok=True, count=1), source_status("LSA SAF MSG-IODC FRP-PIXEL", ok=True, count=1)]


def stub_model(fires, met, receptors, pop, t0, *, members=5, seed=0, afternoon_mode="none", district_of=None):
    stub_model.calls.append({"afternoon_mode": afternoon_mode, "n_fires": len(fires), "members": members,
                             "pop_shape": pop.shape, "district": district_of(30.266, 76.04)})
    return {"fires.geojson": {"type": "FeatureCollection", "features": []}, "clusters.json": {"t0_utc": "x", "clusters": []},
            "places/osm-w1.json": {"id": "osm-w1"},
            "_summary": {"members": members, "afternoon_mode": afternoon_mode, "scale": 2.5, "arrival_threshold": 0.375,
                         "n_clusters": 1, "n_fires": len(fires)}}


stub_model.calls = []
RECS = [Receptor("osm-w1", "School", "school", "Sangrur", "Punjab", 30.266, 76.04, None)]


@pytest.fixture
def store(tmp_path):
    return LocalStore(tmp_path)


def test_fires_and_met_roundtrip():
    back = core.fires_from_json(core.fires_to_json(FIRES))
    assert back == FIRES
    met = _met()
    m2 = core.met_from_npz(core.met_to_npz(met))
    assert m2.times == met.times and m2.u850.shape == (97, 20, 27) and float(m2.u850[0, 0, 0]) == 3.0
    np.testing.assert_array_equal(m2.lons, met.lons)


def test_raw_store_roundtrip(store):
    core.save_raw(store, "R1", T0, FIRES, _met(), SOURCES)
    t0, fires, met, src = core.load_raw(store, "R1")
    assert t0 == T0 and fires == FIRES and met.blh.shape == (97, 20, 27) and src == SOURCES
    with pytest.raises(FileNotFoundError):
        core.load_raw(store, "nope")


def test_publish_writes_artifacts_and_meta(store):
    stub_model.calls.clear()
    meta = core.publish(store, "20261008T0600Z", T0, FIRES, _met(), SOURCES, members=3, afternoon_mode="observed",
                        run_model=stub_model, receptors=RECS, population=np.ones((48, 66)))
    assert META_KEYS <= set(meta)
    assert meta["scale"] == 2.5 and meta["arrival_threshold"] == 0.375 and meta["members"] == 3
    assert meta["afternoon_mode"] == "observed" and meta["alpha"] == 1.0 and meta["calibrated"] is False
    assert meta["t0_utc"] == "2026-10-08T06:00:00Z" and meta["sources"] == SOURCES
    for prefix in ("latest", "runs/20261008T0600Z"):
        for k in ("fires.geojson", "clusters.json", "places/osm-w1.json", "meta.json"):
            assert store.exists(f"{prefix}/{k}"), f"{prefix}/{k}"
    assert not store.exists("latest/_summary")
    assert stub_model.calls[-1]["district"] == ("Sangrur", "Punjab") and stub_model.calls[-1]["pop_shape"] == (48, 66)


def test_publish_observed_falls_back_without_lsasaf(store):
    stub_model.calls.clear()
    src = [source_status("LSA SAF MSG-IODC FRP-PIXEL", ok=False, note="down")]
    core.publish(store, "R", T0, FIRES[:1], _met(), src, afternoon_mode="observed", run_model=stub_model,
                 receptors=RECS, population=np.ones((48, 66)))
    assert stub_model.calls[-1]["afternoon_mode"] == "estimated"


def test_calibration_from_backtest(store, monkeypatch):
    monkeypatch.delenv("DHUAAN_ALPHA", raising=False)
    assert core.calibration(store, "estimated") == (1.0, False)
    store.put_json("latest/backtest.json", {"calibration": {"alpha_A": 0.8, "alpha_B": 0.6}})
    assert core.calibration(store, "estimated") == (0.6, True)
    assert core.calibration(store, "none") == (0.8, True)


def test_ingest_records_failures(monkeypatch):
    from dhuaan.ingest import firms, lsasaf, openaq, openmeteo
    monkeypatch.setattr(firms, "fetch_recent", lambda days, use_cache=None: (FIRES[:1], SOURCES[:1]))
    monkeypatch.setattr(lsasaf, "fetch_recent", lambda now, use_cache=None: (_ for _ in ()).throw(RuntimeError("401")))
    monkeypatch.setattr(openaq, "fetch_stations", lambda use_cache=None: (_ for _ in ()).throw(RuntimeError("429")))
    monkeypatch.setattr(openmeteo, "fetch_forecast", lambda t0, use_cache=None: (_met(), source_status("Open-Meteo forecast", ok=True)))
    fires, met, sources = core.ingest(T0)
    by = {s["name"]: s for s in sources}
    assert len(fires) == 1 and met.u10.shape[0] == 97
    assert by["LSA SAF MSG-IODC FRP-PIXEL"]["ok"] is False and by["OpenAQ PM2.5 stations"]["ok"] is False
    monkeypatch.setattr(openmeteo, "fetch_forecast", lambda t0, use_cache=None: (_ for _ in ()).throw(RuntimeError("x")))
    with pytest.raises(RuntimeError, match="met ingest failed"):
        core.ingest(T0, use_lsasaf=False, with_openaq=False)


def _patch_pipeline(monkeypatch, store):
    monkeypatch.setattr(core, "ingest", lambda t0, **k: (FIRES, _met(), SOURCES))
    orig = core.publish
    monkeypatch.setattr(run_local, "ingest", core.ingest)
    monkeypatch.setattr(handlers, "ingest", core.ingest)
    pub = lambda *a, **k: orig(*a, run_model=stub_model, receptors=RECS, population=np.ones((48, 66)), **k)
    monkeypatch.setattr(run_local, "publish", pub)
    monkeypatch.setattr(handlers, "publish", pub)
    monkeypatch.setattr(run_local, "get_store", lambda: store)
    monkeypatch.setattr(handlers, "get_store", lambda: store)


def test_run_local_cli(store, monkeypatch, capsys):
    _patch_pipeline(monkeypatch, store)
    assert run_local.main(["--members", "2", "--afternoon-mode", "none", "--t0", "2026-10-08T06:30:00Z"]) == 0
    out = capsys.readouterr().out
    assert "run 20261008T0600Z" in out and "wrote" in out
    meta = store.get_json("latest/meta.json")
    assert meta["run_id"] == "20261008T0600Z" and meta["afternoon_mode"] == "none" and meta["members"] == 2
    assert store.exists("raw/20261008T0600Z/met.npz")


def test_handlers_ingest_then_model(store, monkeypatch):
    _patch_pipeline(monkeypatch, store)
    r = handlers.ingest_handler({"t0_utc": "2026-10-08T06:10:00Z"})
    assert r["run_id"] == "20261008T0600Z" and r["n_fires"] == 2 and r["sources_ok"] == 2
    m = handlers.model_handler({"run_id": r["run_id"], "members": 3})
    assert m["n_clusters"] == 1 and m["scale"] == 2.5 and store.exists("latest/meta.json")


def test_advise_handler_calls_agent(store, monkeypatch):
    import dhuaan.agent.advisory as adv
    monkeypatch.setattr(handlers, "get_store", lambda: store)
    monkeypatch.setattr(adv, "generate_all", lambda st, run_id, ids=None: ["osm-w1"])
    assert handlers.advise_handler({"run_id": "R"}) == {"run_id": "R", "advisories": ["osm-w1"]}


ADV = {"school_id": "osm-w1", "date_ist": "2026-10-09",
       "plan": [{"hour_ist": "08:00", "est_pm25": 40, "category": "satisfactory", "outdoor": "ok"},
                {"hour_ist": "09:00", "est_pm25": 130, "category": "very_poor", "outdoor": "indoors"}],
       "notice": {"en": "Keep assembly indoors.", "hi": "हिंदी", "pa": "ਪੰਜਾਬੀ"}, "grounding": {"verified": 5, "total": 5}}


def test_format_message():
    t = handlers.format_message(ADV, "Govt School", ["en", "pa"])
    assert "Govt School" in t and "09:00" in t and "very_poor" in t and "Keep assembly indoors." in t and "ਪੰਜਾਬੀ" in t
    assert "हिंदी" not in t and "5/5" in t


def test_notify_handler(store, monkeypatch):
    monkeypatch.setattr(handlers, "get_store", lambda: store)
    sent = {}

    class R:
        status_code = 200
        text = ""

        def json(self):
            return {"ok": True}

    def post(url, json=None, timeout=None):
        sent["url"], sent["body"] = url, json
        return R()
    monkeypatch.setattr("requests.post", post)
    from dhuaan.config import settings
    monkeypatch.setattr(type(settings), "telegram_bot_token", property(lambda s: "TOKEN"), raising=False)
    monkeypatch.setattr(type(settings), "telegram_chat_id", property(lambda s: "42"), raising=False)
    assert handlers.notify_handler({"school_id": "osm-w1"})["note"] == "no advisory"
    store.put_json("latest/advisories/osm-w1.json", ADV)
    r = handlers.notify_handler({"school_id": "osm-w1", "lang": "en"})
    assert r["sent"] is True and sent["body"]["chat_id"] == "42" and "Keep assembly indoors." in sent["body"]["text"]
    assert sent["url"].endswith("/sendMessage")
