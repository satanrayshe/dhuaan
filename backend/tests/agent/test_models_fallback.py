import pytest

from dhuaan.agent import models


class Err(Exception):
    def __init__(self, code, msg=""):
        super().__init__(msg or str(code))
        self.code = code


def _chain(monkeypatch, ids):
    monkeypatch.setattr(models, "_unavailable", set())
    monkeypatch.setattr(models, "candidates", lambda provider=None: [m for m in ids if m not in models._unavailable])


def test_chain_has_no_retired_ids():
    assert models.GEMINI_CHAIN[0] == "gemini-flash-lite-latest"
    assert not any(m.startswith("gemini-2.5") for m in models.GEMINI_CHAIN)


def test_overload_backs_off_then_falls_through(monkeypatch):
    _chain(monkeypatch, ["a", "b"])
    calls, sleeps = [], []

    def fn(mid):
        calls.append(mid)
        if mid == "a":
            raise Err(503, "503 UNAVAILABLE. The model is experiencing high demand")
        return "ok"
    out, mid = models.call_with_fallback(fn, sleep=sleeps.append)
    assert (out, mid) == ("ok", "b")
    assert calls == ["a"] * (models.OVERLOAD_RETRIES + 1) + ["b"]
    assert len(sleeps) == models.OVERLOAD_RETRIES and all(0 < s <= 3 for s in sleeps)


def test_overload_recovers_on_same_model(monkeypatch):
    _chain(monkeypatch, ["a", "b"])
    n = {"a": 0}

    def fn(mid):
        n["a"] += 1
        if n["a"] == 1:
            raise Err(503)
        return mid
    assert models.call_with_fallback(fn, sleep=lambda s: None) == ("a", "a")


def test_quota_and_retired_skip_without_sleep(monkeypatch):
    _chain(monkeypatch, ["a", "b", "c"])
    sleeps = []

    def fn(mid):
        if mid == "a":
            raise Err(404, "This model is no longer available to new users")
        if mid == "b":
            raise Err(429, "RESOURCE_EXHAUSTED")
        return mid
    assert models.call_with_fallback(fn, sleep=sleeps.append) == ("c", "c")
    assert sleeps == [] and "a" in models._unavailable and "b" not in models._unavailable


def test_other_errors_raise(monkeypatch):
    _chain(monkeypatch, ["a", "b"])
    with pytest.raises(ValueError):
        models.call_with_fallback(lambda mid: (_ for _ in ()).throw(ValueError("bad")))
