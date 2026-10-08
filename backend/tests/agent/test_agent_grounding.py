from __future__ import annotations

import json

from dhuaan.agent.grounding import check, extract

RESULT = {
    "arrival_utc": "2026-10-08T15:30:00Z",          # = 21:00 IST
    "peak": {"time_ist": "2026-10-09 13:30 IST", "est_pm25": 156, "est_pm25_band": [117, 199]},
    "districts": [{"district": "Sangrur", "share": 0.34}, {"district": "Barnala", "share_pct": 22}],
    "exposure_person_hours": 1824000.0,
    "lat": 30.9123, "lon": 75.8573,
    "raw": 147.4,
    "note": "default 60 ug/m3 (no nearby observation under 6 h old)",
}


def g(answer, question="", results=(RESULT,)):
    return check(answer, list(results), question)


def test_plain_and_rounded_numbers():
    r = g("Peak about 156 (range 117-199) near 30.91, 75.86.")
    assert r == {"verified": 5, "total": 5, "unverified": []}


def test_unverified_number_is_reported():
    r = g("Peak 156, but 47% comes from Sangrur.")
    assert r["total"] == 2 and r["unverified"] == ["47%"]


def test_share_fraction_and_percent_both_ways():
    assert g("Sangrur 34%, Barnala 22%.")["unverified"] == []
    assert g("Sangrur 34 प्रतिशत")["unverified"] == []
    assert g("Sangrur 35%")["unverified"] == ["35%"]


def test_ist_times_derived_from_utc():
    for text in ("Smoke arrives at 21:00 IST.", "Smoke arrives at 9 pm.", "Smoke arrives around 9 p.m.",
                 "धुआँ रात 9 बजे पहुँचेगा", "ਧੂੰਆਂ ਰਾਤ 9 ਵਜੇ ਪਹੁੰਚੇਗਾ", "peak at 1:30 pm", "peak at 13:30"):
        assert g(text)["unverified"] == [], text
    r = g("arrives at 4 am")
    assert r["unverified"] == ["4 am"]


def test_devanagari_and_gurmukhi_digits():
    assert g("पीक लगभग १५६ µg/m³, दायरा ११७-१९९")["unverified"] == []
    assert g("ਸੰਗਰੂਰ ਤੋਂ ੩੪% ਧੂੰਆਂ")["unverified"] == []
    assert g("ਸੰਗਰੂਰ ਤੋਂ ੪੭% ਧੂੰਆਂ")["unverified"] == ["47%"]
    assert g("२१:०० बजे")["unverified"] == []


def test_indian_grouping_and_lakh():
    assert g("18,24,000 person-hours")["unverified"] == []
    assert g("1,824,000 person-hours")["unverified"] == []
    assert g("18.24 lakh person-hours")["unverified"] == []
    assert g("18.2 lakh person-hours")["unverified"] == []      # 1.82 M within lakh rounding of 18.24
    assert g("25 lakh person-hours")["unverified"] == ["25 lakh"]


def test_round_numbers_allowed_near_value():
    assert g("about 150 ug/m3")["unverified"] == []             # 147.4 -> nearest 10
    assert g("about 145")["unverified"] == []                   # nearest 5
    assert g("about 170")["unverified"] == ["170"]
    assert g("about 148")["unverified"] == ["148"]              # not round, not equal


def test_exclusions_units_ids_lists_ordinals_question():
    text = "1. PM2.5 and PM10 in µg/m³ from cluster c0001 (GK2A, NOAA-20)\n2. the 2nd cluster\n3) done"
    r = g(text)
    assert r == {"verified": 0, "total": 0, "unverified": []}
    r = g("For the next 72 hours: peak 156.", question="What happens in the next 72 hours?")
    assert r == {"verified": 1, "total": 1, "unverified": []}


def test_dates_from_timestamps():
    assert g("on 9 Oct 2026 and 2026-10-08")["unverified"] == []
    assert g("on 12 Oct")["unverified"] == ["12"]


def test_numbers_inside_tool_strings_and_json_text():
    assert g("default 60, observation under 6 h", results=[json.dumps(RESULT)])["unverified"] == []


def test_duplicate_numbers_counted_once():
    assert g("156 ... 156 ... 156")["total"] == 1


def test_extract_shapes():
    times, nums = extract("At 9:30 pm, 34% (१५६) and 1,23,456.")
    assert [(t["h"], t["m"]) for t in times] == [(21, 30)]
    assert [n["value"] for n in nums] == [34.0, 156.0, 123456.0]
