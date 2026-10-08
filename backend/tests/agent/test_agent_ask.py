from __future__ import annotations

from scripted_model import ScriptedModel

from dhuaan.agent import agent as ag


def _factory(model):
    return lambda model_id: model


def test_ask_traces_tools_and_grounds(store):
    m = ScriptedModel([
        {"tools": [("get_smoke_forecast", {"place_id": "sch_demo_sunrise", "hours": 72}),
                   ("get_school_day_plan", {"school_id": "sch_demo_sunrise", "date_ist": "2026-10-09"})]},
        {"text": "Smoke reaches the school around 05:30 IST on 9 Oct. Peak near 13:30 IST, about 156 µg/m³ PM2.5 "
                 "(range 117-199). Keep PE indoors."},
    ])
    out = ag.ask("When will smoke reach the school?", place_id="sch_demo_sunrise", lang="en", model_factory=_factory(m))
    assert [t["tool"] for t in out["tool_trace"]] == ["get_smoke_forecast", "get_school_day_plan"]
    assert out["tool_trace"][0]["args"]["place_id"] == "sch_demo_sunrise"
    assert "arrival" in out["tool_trace"][0]["summary"]
    assert out["grounding"]["unverified"] == [], out["grounding"]
    assert out["grounding"]["total"] >= 5, out
    assert out["cached"] is False and out["retried"] is False
    assert out["model_calls"] == 2
    assert "sch_demo_sunrise" in m.requests[0]["system_prompt"]
    # second call hits the store cache and does not touch the model
    again = ag.ask("when will smoke reach the school", place_id="sch_demo_sunrise", lang="en",
                   model_factory=_factory(ScriptedModel([])))
    assert again["cached"] is True and again["answer"] == out["answer"]


def test_unverified_number_triggers_one_retry(store):
    m = ScriptedModel([
        {"tools": [("get_attribution", {"place_id": "town_khanna"})]},
        {"text": "Sangrur contributes 47% of the smoke."},
        {"text": "Sangrur contributes 34% and Barnala 22% of the smoke (Dhuaan forecast)."},
    ])
    out = ag.ask("Where does Khanna's smoke come from?", lang="en", model_factory=_factory(m), use_cache=False)
    assert out["retried"] is True
    assert "34%" in out["answer"]
    assert out["grounding"] == {"verified": 2, "total": 2, "unverified": []}
    assert "47%" in m.requests[2]["messages"][-1]["content"][0]["text"]


def test_retry_keeps_better_answer(store):
    m = ScriptedModel([
        {"tools": [("get_attribution", {"place_id": "town_khanna"})]},
        {"text": "Sangrur 47%."},
        {"text": "Sangrur 47%, Moga 99% and 1234 fires."},
    ])
    out = ag.ask("sources?", lang="en", model_factory=_factory(m), use_cache=False)
    assert out["answer"] == "Sangrur 47%."
    assert out["grounding"]["unverified"] == ["47%"]


def test_validation(store):
    import pytest
    with pytest.raises(ValueError):
        ag.ask("x" * 501, model_factory=_factory(ScriptedModel([])))
    with pytest.raises(ValueError):
        ag.ask("hi", lang="fr", model_factory=_factory(ScriptedModel([])))


def test_cache_key_depends_on_lang_place_and_run(store):
    k1 = ag.cache_key("When?", "a", "en")
    assert k1 == ag.cache_key("  when ", "a", "en")
    assert k1 != ag.cache_key("When?", "a", "hi")
    assert k1 != ag.cache_key("When?", "b", "en")
    assert k1.startswith("cache/answers/") and k1.endswith(".json")


def test_budget_guard(store, monkeypatch):
    import pytest
    monkeypatch.setenv("DHUAAN_MAX_LLM_CALLS", str(ag.BUDGET.calls + 1))
    m = ScriptedModel([{"tools": [("get_data_freshness", {})]}, {"text": "fresh"}])
    with pytest.raises(ag.LLMBudgetExceeded):
        ag.ask("is data fresh?", model_factory=_factory(m), use_cache=False)


def test_falls_back_when_model_retired_or_throttled(store, monkeypatch):
    from dhuaan.agent import models

    class Gone(Exception):
        code = 404
    monkeypatch.setattr(models, "_unavailable", set())
    monkeypatch.setattr(models, "candidates", lambda provider=None: [m for m in ["old-model", "new-model"] if m not in models._unavailable])
    tried = []

    def factory(model_id):
        tried.append(model_id)
        if model_id == "old-model":
            class Broken(ScriptedModel):
                async def stream(self, *a, **k):
                    raise Gone("404 NOT_FOUND. This model is no longer available to new users")
                    yield {}
            return Broken([])
        return ScriptedModel([{"tools": [("get_data_freshness", {})]}, {"text": "Run is fresh."}])
    out = ag.ask("fresh?", model_factory=factory, use_cache=False)
    assert tried == ["old-model", "new-model"] and out["answer"] == "Run is fresh."
    assert out["model"].endswith("new-model")
    assert "old-model" in models._unavailable
