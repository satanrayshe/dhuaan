from __future__ import annotations

import json
import re

from dhuaan.agent import advisory, rules
from dhuaan.agent.grounding import check

DEV = re.compile(r"[ऀ-ॿ]")
GUR = re.compile(r"[਀-੿]")


def _plan(store, date_ist="2026-10-09", sid="sch_demo_sunrise"):
    return rules.school_day_plan(store.get_json(f"latest/places/{sid}.json"), 1.0, None, date_ist)


def test_templates_all_levels_grounded_and_in_script(store):
    for sid, d, level in [("sch_demo_sunrise", "2026-10-09", "indoors"), ("city_patiala", "2026-10-09", "limit"),
                          ("city_patiala", "2026-10-08", "ok"), ("city_patiala", "2026-11-20", "none")]:
        plan = _plan(store, d, sid)
        assert (plan["summary"].get("overall_outdoor") or "none") == level, (sid, d)
        f = advisory.facts_for(plan)
        for lang in ("en", "hi", "pa"):
            t = advisory.template_notice(lang, plan)
            g = check(t, [f, plan])
            assert g["unverified"] == [] and g["total"] >= 2, (lang, level, t, g)
            assert "{" not in t and "None" not in t, t
        assert DEV.search(advisory.template_notice("hi", plan)) and GUR.search(advisory.template_notice("pa", plan))
        assert not DEV.search(advisory.template_notice("en", plan))


def test_build_notices_uses_llm_when_grounded(store):
    plan = _plan(store)
    worst = plan["summary"]["worst_est_pm25"]
    calls = []

    def llm(system, user):
        calls.append(system)
        if "JSON only" in system:
            return "```json\n" + json.dumps({"hi": f"धुएँ की चेतावनी: 13:00 बजे PM2.5 लगभग {worst} µg/m³।",
                                             "pa": f"ਧੂੰਏਂ ਦੀ ਚੇਤਾਵਨੀ: 99 ਵਜੇ"}, ensure_ascii=False) + "\n```"
        return f"Smoke is forecast at Sunrise Public School on 9 October, worst at 13:00 IST (about {worst} µg/m³). PE indoors."

    notice, g, src = advisory.build_notices(plan, llm)
    assert len(calls) == 2
    assert src == {"en": "llm", "hi": "llm", "pa": "template"}  # pa had an invented number -> template
    assert notice["pa"] == advisory.template_notice("pa", plan)
    assert set(g["by_lang"]) == {"en", "hi", "pa"} and g["verified"] == g["total"]


def test_build_notices_rejects_ungrounded_or_wrong_script(store):
    plan = _plan(store)

    def llm(system, user):
        if "JSON only" in system:
            return json.dumps({"hi": "Smoke aayega", "pa": "ਧੂੰਆਂ"})
        return "Air will hit 400 tomorrow."

    notice, g, src = advisory.build_notices(plan, llm)
    assert src == {"en": "template", "hi": "template", "pa": "template"}  # en failed -> no translation attempted


def test_generate_all_writes_artifacts(store, monkeypatch):
    monkeypatch.setattr(advisory, "DATA_DIR", store.root / "nodata")
    ids = advisory.generate_all(store, "20261008T00Z", llm=False, date_ist="2026-10-09")
    assert ids == ["sch_demo_sunrise"]  # default: schools in the index
    art = store.get_json("latest/advisories/sch_demo_sunrise.json")
    assert store.get_json("runs/20261008T00Z/advisories/sch_demo_sunrise.json") == art
    assert art["school_id"] == "sch_demo_sunrise" and art["date_ist"] == "2026-10-09"
    assert set(art["notice"]) == {"en", "hi", "pa"} and art["model"] == "template"
    assert art["grounding"]["verified"] == art["grounding"]["total"] > 0
    row = art["plan"][0]
    assert set(row) >= {"hour_ist", "est_pm25", "category", "outdoor"} and row["outdoor"] in ("ok", "limit", "indoors")


def test_school_ids_from_data_files(store, monkeypatch, tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    (d / "demo_places.json").write_text(json.dumps({"places": [
        {"id": "sch_demo_sunrise", "kind": "school"}, {"id": "town_khanna", "kind": "town"}]}), encoding="utf-8")
    (d / "subscriptions.json").write_text(json.dumps([{"school_id": "city_patiala"}, "sch_demo_sunrise"]), encoding="utf-8")
    monkeypatch.setattr(advisory, "DATA_DIR", d)
    assert advisory.school_ids_default(store) == ["city_patiala", "sch_demo_sunrise"]
    assert advisory.generate_all(store, "r1", ["missing", "town_khanna"], llm=False) == ["town_khanna"]
