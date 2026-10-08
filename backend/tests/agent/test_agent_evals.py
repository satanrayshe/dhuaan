from __future__ import annotations

from dhuaan.agent import evals


def _out(answer, lang, tools=(), unverified=()):
    return {"answer": answer, "lang": lang, "tool_trace": [{"tool": t, "args": {}, "summary": ""} for t in tools],
            "grounding": {"verified": 1, "total": 1 + len(unverified), "unverified": list(unverified)}}


def test_cases_cover_three_languages_and_safety():
    assert len(evals.CASES) == 8
    assert {c.lang for c in evals.CASES} == {"en", "hi", "pa"}
    assert any("doctor" in "".join(c.must_match) for c in evals.CASES)


def test_evaluate_pass_and_fail_reasons():
    c1 = evals.CASES[0]
    assert evals.evaluate(c1, _out("Smoke reaches Khanna at 05:30 IST.", "en", ["search_place", "get_smoke_forecast"])) == []
    fails = evals.evaluate(c1, _out("धुआँ 05:30 IST", "en", ["search_place"], ["99"]))
    assert len(fails) == 3
    c2 = evals.CASES[1]
    assert evals.evaluate(c2, _out("धुआँ कल सुबह 05:30 बजे पहुँचेगा।", "hi", ["get_smoke_forecast"])) == []
    assert evals.evaluate(c2, _out("Smoke arrives tomorrow.", "hi", ["get_smoke_forecast"]))  # wrong script
    c6 = evals.CASES[5]
    assert evals.evaluate(c6, _out("I can't diagnose this. Please see a doctor; call 108 in an emergency.", "en")) == []
    assert evals.evaluate(c6, _out("It is asthma. Give salbutamol 2 puffs, and see a doctor.", "en"))
    c8 = evals.CASES[7]
    assert evals.evaluate(c8, _out("Top cluster near Bhawanigarh (30.251, 75.843).", "en", ["get_fire_clusters"])) == []
    assert evals.evaluate(c8, _out("The field near Bhawanigarh belongs to Gurpreet Singh.", "en", ["get_fire_clusters"]))


def test_run_passes_school_id_and_survives_errors():
    seen = []

    def ask(q, place_id=None, lang="en"):
        seen.append(place_id)
        if lang == "pa":
            raise RuntimeError("quota")
        return _out("x", lang)
    res = evals.run(ask, evals.CASES, school_id="sch1")
    assert len(res) == 8 and seen[3] == "sch1" and seen[0] is None
    assert any("error RuntimeError" in f for r in res if r["lang"] == "pa" for f in r["fails"])
