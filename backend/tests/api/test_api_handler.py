from __future__ import annotations

import dataclasses
import json
import shutil
from pathlib import Path

import pytest

from dhuaan.agent import data
from dhuaan.api import handler as h
from dhuaan.api import ratelimit
from dhuaan.store import LocalStore

FIXTURES = Path(__file__).resolve().parents[1] / "agent" / "fixtures"


@pytest.fixture
def api(tmp_path, monkeypatch):
    shutil.copytree(FIXTURES, tmp_path, dirs_exist_ok=True)
    st = LocalStore(tmp_path)
    data.use_store(st)
    ratelimit.set_limiter(ratelimit.MemoryLimiter())
    calls = []

    def fake_ask(question, place_id=None, lang="en"):
        calls.append((question, place_id, lang))
        return {"answer": f"ok {lang}", "lang": lang, "tool_trace": [],
                "grounding": {"verified": 0, "total": 0, "unverified": []}, "model": "fake", "cached": False}
    from dhuaan.agent import agent as ag
    monkeypatch.setattr(ag, "ask", fake_ask)
    yield st, calls
    data.use_store(None)
    ratelimit.set_limiter(None)


def ev(method, path, query=None, body=None, ip="1.2.3.4", origin=None):
    e = {"version": "2.0", "rawPath": path, "queryStringParameters": query, "headers": {},
         "requestContext": {"http": {"method": method, "sourceIp": ip}},
         "body": None if body is None else (body if isinstance(body, str) else json.dumps(body))}
    if origin:
        e["headers"]["Origin"] = origin
    return e


def call(*a, **k):
    r = h.handler(ev(*a, **k))
    return r["statusCode"], (json.loads(r["body"]) if r["body"] else None), r["headers"]


def test_health_and_cors(api):
    s, b, hd = call("GET", "/api/health")
    assert s == 200 and b == {"ok": True, "run_id": "20261008T00Z", "model_provider": h.settings.model_provider}
    assert hd["Access-Control-Allow-Origin"] == "*" and hd["Content-Type"].startswith("application/json")


def test_preflight(api):
    s, b, hd = call("OPTIONS", "/api/ask", origin="http://localhost:3000")
    assert s == 204 and b is None
    assert "POST" in hd["Access-Control-Allow-Methods"] and hd["Access-Control-Allow-Headers"] == "content-type"


def test_cors_specific_origin(api, monkeypatch):
    monkeypatch.setattr(h, "settings", dataclasses.replace(
        h.settings, allowed_origin="https://dhuaan.example,https://x.cloudfront.net"))
    _, _, hd = call("GET", "/api/health", origin="https://x.cloudfront.net")
    assert hd["Access-Control-Allow-Origin"] == "https://x.cloudfront.net" and hd["Vary"] == "Origin"
    _, _, hd = call("GET", "/api/health", origin="https://evil.example")
    assert hd["Access-Control-Allow-Origin"] == "https://dhuaan.example"


def test_routing_errors(api):
    assert call("GET", "/api/nope")[0] == 404
    assert call("DELETE", "/api/ask")[0] == 405
    assert call("GET", "/api/ask")[0] == 405
    assert call("GET", "/api/health/")[0] == 200  # trailing slash tolerated


def test_search(api):
    s, b, _ = call("GET", "/api/search", {"q": "khanna", "limit": "3"})
    assert s == 200 and b["places"][0]["id"] == "town_khanna"
    assert set(b["places"][0]) >= {"id", "name", "kind", "district", "state", "lat", "lon", "peak_smoke", "peak_utc", "arrival_utc"}
    assert call("GET", "/api/search", {})[0] == 400
    assert call("GET", "/api/search", {"q": "a", "limit": "x"})[0] == 400
    assert call("GET", "/api/search", {"q": "a", "limit": "500"})[0] == 400


def test_ask_validation(api):
    _, calls = api
    assert call("POST", "/api/ask", body="not json")[0] == 400
    assert call("POST", "/api/ask", body=[1])[0] == 400
    assert call("POST", "/api/ask", body={"lang": "en"})[0] == 400
    assert call("POST", "/api/ask", body={"question": "x" * 501})[0] == 400
    assert call("POST", "/api/ask", body={"question": "ok", "lang": "fr"})[0] == 400
    assert call("POST", "/api/ask", body={"question": "ok", "place_id": "../etc"})[0] == 400
    assert call("POST", "/api/ask", body={"question": "ok", "place_id": "nowhere"})[0] == 404
    assert call("POST", "/api/ask", body="x" * 9000)[0] == 413
    assert calls == []
    s, b, _ = call("POST", "/api/ask", body={"question": "x" * 500, "lang": "pa", "place_id": "town_khanna"})
    assert s == 200 and b["lang"] == "pa" and calls == [("x" * 500, "town_khanna", "pa")]
    s, b, _ = call("POST", "/api/ask", body={"question": "When?", "place_id": ""})
    assert s == 200 and calls[-1] == ("When?", None, "en")


def test_ask_base64_body(api):
    import base64
    e = ev("POST", "/api/ask", body=None)
    e["body"] = base64.b64encode(json.dumps({"question": "hi", "lang": "hi"}).encode()).decode()
    e["isBase64Encoded"] = True
    r = h.handler(e)
    assert r["statusCode"] == 200 and json.loads(r["body"])["lang"] == "hi"


def test_ask_rate_limit_per_ip_and_cache_bypass(api):
    st, calls = api
    for i in range(20):
        assert call("POST", "/api/ask", body={"question": f"q{i}"}, ip="9.9.9.9")[0] == 200
    s, b, hd = call("POST", "/api/ask", body={"question": "q21"}, ip="9.9.9.9")
    assert s == 429 and int(hd["Retry-After"]) > 0 and "per hour" in b["error"]
    assert call("POST", "/api/ask", body={"question": "q21"}, ip="8.8.8.8")[0] == 200
    # a cached answer is served even when rate-limited
    from dhuaan.agent import agent as ag
    st.put_json(ag.cache_key("cached one", None, "en"), {
        "answer": "from cache", "lang": "en", "tool_trace": [],
        "grounding": {"verified": 0, "total": 0, "unverified": []}, "model": "m"})
    s, b, _ = call("POST", "/api/ask", body={"question": "Cached one?"}, ip="9.9.9.9")
    assert s == 200 and b["cached"] is True and b["answer"] == "from cache"


def test_ask_global_daily_limit(api):
    ratelimit.set_limiter(ratelimit.MemoryLimiter(global_day=3))
    for i in range(3):
        assert call("POST", "/api/ask", body={"question": f"g{i}"}, ip=f"10.0.0.{i}")[0] == 200
    s, b, _ = call("POST", "/api/ask", body={"question": "g9"}, ip="10.0.0.99")
    assert s == 429 and "daily" in b["error"]


def test_ask_model_failure_is_503(api, monkeypatch):
    from dhuaan.agent import agent as ag

    def boom(*a, **k):
        raise RuntimeError("down")
    monkeypatch.setattr(ag, "ask", boom)
    s, b, hd = call("POST", "/api/ask", body={"question": "hi"})
    assert s == 503 and "error" in b and hd["Access-Control-Allow-Origin"] == "*"


def test_advisory(api):
    st, _ = api
    assert call("GET", "/api/advisory", {"school_id": "sch_demo_sunrise"})[0] == 404
    from dhuaan.agent import advisory
    advisory.generate_all(st, "20261008T00Z", ["sch_demo_sunrise"], llm=False, date_ist="2026-10-09")
    data.clear_cache()
    s, b, _ = call("GET", "/api/advisory", {"school_id": "sch_demo_sunrise", "lang": "hi"})
    assert s == 200 and b["school_id"] == "sch_demo_sunrise" and b["notice_text"] == b["notice"]["hi"]
    assert set(b) >= {"school_id", "date_ist", "plan", "notice", "grounding", "model"}
    assert call("GET", "/api/advisory", {"school_id": "sch_demo_sunrise", "lang": "xx"})[0] == 400
    assert call("GET", "/api/advisory", {})[0] == 400


def test_local_server_event_shape():
    from dhuaan.api.local import to_event
    e = to_event("GET", "/api/search?q=khanna&limit=2", {"Origin": "x"}, b"", "127.0.0.1")
    assert e["rawPath"] == "/api/search" and e["queryStringParameters"] == {"q": "khanna", "limit": "2"}
    assert e["requestContext"]["http"] == {"method": "GET", "path": "/api/search", "sourceIp": "127.0.0.1"}
