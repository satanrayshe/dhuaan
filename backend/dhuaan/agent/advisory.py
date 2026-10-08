"""School advisories (CONTRACTS item 8): advisories/<school_id>.json for subscribed/demo schools.

The plan always comes from rules.school_day_plan (deterministic). The parent notice is:
  en: written by the LLM from the plan facts, else the fixed template;
  hi, pa: one LLM call translating the English notice (numbers kept identical), else fixed templates.
Every notice is grounding-checked against the facts; a notice that fails the check (or is in the wrong script)
is replaced by its template, so a published notice never carries an unverified number.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import date
from typing import Any, Callable, Iterable

from dhuaan.agent import grounding, models, prompts, rules, tools
from dhuaan.agent.timeutil import iso_utc, ist_str, now_utc
from dhuaan.config import DATA_DIR, settings

log = logging.getLogger(__name__)

CAT = {
    "en": {"good": "Good", "satisfactory": "Satisfactory", "moderate": "Moderate", "poor": "Poor",
           "very_poor": "Very Poor", "severe": "Severe"},
    "hi": {"good": "अच्छी", "satisfactory": "संतोषजनक", "moderate": "मध्यम", "poor": "खराब",
           "very_poor": "बहुत खराब", "severe": "गंभीर"},
    "pa": {"good": "ਚੰਗੀ", "satisfactory": "ਤਸੱਲੀਬਖ਼ਸ਼", "moderate": "ਦਰਮਿਆਨੀ", "poor": "ਮਾੜੀ",
           "very_poor": "ਬਹੁਤ ਮਾੜੀ", "severe": "ਗੰਭੀਰ"},
}
MONTHS = {
    "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
    "hi": ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"],
    "pa": ["ਜਨਵਰੀ", "ਫ਼ਰਵਰੀ", "ਮਾਰਚ", "ਅਪ੍ਰੈਲ", "ਮਈ", "ਜੂਨ", "ਜੁਲਾਈ", "ਅਗਸਤ", "ਸਤੰਬਰ", "ਅਕਤੂਬਰ", "ਨਵੰਬਰ", "ਦਸੰਬਰ"],
}
_TAIL = {
    "en": "This is a forecast estimate (Dhuaan smoke forecast, CPCB NAQI categories), not a measurement.",
    "hi": "यह पूर्वानुमान पर आधारित अनुमान है (Dhuaan धुआँ पूर्वानुमान, CPCB NAQI श्रेणियाँ), मापा हुआ आँकड़ा नहीं।",
    "pa": "ਇਹ ਪੂਰਵ-ਅਨੁਮਾਨ 'ਤੇ ਆਧਾਰਿਤ ਅੰਦਾਜ਼ਾ ਹੈ (Dhuaan ਧੂੰਆਂ ਪੂਰਵ-ਅਨੁਮਾਨ, CPCB NAQI ਸ਼੍ਰੇਣੀਆਂ), ਮਾਪਿਆ ਹੋਇਆ ਅੰਕੜਾ ਨਹੀਂ।",
}
TEMPLATES = {
    "en": {
        "indoors": "Smoke advisory for {name}, {date}: farm-fire smoke is forecast to make the air {cat} during school hours, "
                   "worst around {hour} IST (estimated PM2.5 {worst} µg/m³, range {lo}-{hi}). Assembly, PE and recess will be "
                   "held indoors and windows kept closed. Children with asthma should carry their usual medicines. ",
        "limit": "Smoke advisory for {name}, {date}: farm-fire smoke may make the air {cat} during school hours, worst around "
                 "{hour} IST (estimated PM2.5 {worst} µg/m³, range {lo}-{hi}). There will be no strenuous outdoor PE, assembly "
                 "will be short, and children with asthma or heart or lung conditions will stay indoors. ",
        "ok": "Air update for {name}, {date}: no significant smoke is forecast during school hours (estimated PM2.5 up to "
              "{worst} µg/m³, {cat}). Normal outdoor activities will continue. ",
        "none": "Air update for {name}, {date}: the smoke forecast does not cover this day yet. Please check again tomorrow. ",
    },
    "hi": {
        "indoors": "{name} के लिए धुएँ की सूचना, {date}: पराली के धुएँ के कारण स्कूल के समय हवा '{cat}' श्रेणी में रहने का अनुमान है, "
                   "सबसे ज़्यादा लगभग {hour} बजे (अनुमानित PM2.5 {worst} µg/m³, दायरा {lo}-{hi})। प्रार्थना सभा, पीटी और खेल का समय "
                   "कक्षाओं के अंदर होगा और खिड़कियाँ बंद रखी जाएँगी। दमा (अस्थमा) वाले बच्चे अपनी नियमित दवा साथ रखें। ",
        "limit": "{name} के लिए धुएँ की सूचना, {date}: पराली के धुएँ से स्कूल के समय हवा '{cat}' श्रेणी तक पहुँच सकती है, सबसे ज़्यादा "
                 "लगभग {hour} बजे (अनुमानित PM2.5 {worst} µg/m³, दायरा {lo}-{hi})। बाहर भारी पीटी या खेल नहीं होंगे, प्रार्थना सभा "
                 "छोटी रहेगी, और दमा या दिल/फेफड़ों की बीमारी वाले बच्चे अंदर रहेंगे। ",
        "ok": "{name} के लिए हवा की सूचना, {date}: स्कूल के समय धुएँ का कोई खास असर अपेक्षित नहीं है (अनुमानित PM2.5 अधिकतम "
              "{worst} µg/m³, '{cat}')। बाहर की सामान्य गतिविधियाँ जारी रहेंगी। ",
        "none": "{name} के लिए हवा की सूचना, {date}: इस दिन का धुआँ पूर्वानुमान अभी उपलब्ध नहीं है। कृपया कल फिर देखें। ",
    },
    "pa": {
        "indoors": "{name} ਲਈ ਧੂੰਏਂ ਦੀ ਸੂਚਨਾ, {date}: ਪਰਾਲੀ ਦੇ ਧੂੰਏਂ ਕਾਰਨ ਸਕੂਲ ਦੇ ਸਮੇਂ ਹਵਾ '{cat}' ਸ਼੍ਰੇਣੀ ਵਿੱਚ ਰਹਿਣ ਦਾ ਅਨੁਮਾਨ ਹੈ, "
                   "ਸਭ ਤੋਂ ਵੱਧ ਲਗਭਗ {hour} ਵਜੇ (ਅਨੁਮਾਨਿਤ PM2.5 {worst} µg/m³, ਦਾਇਰਾ {lo}-{hi})। ਸਵੇਰ ਦੀ ਸਭਾ, ਪੀਟੀ ਅਤੇ ਛੁੱਟੀ ਦਾ ਸਮਾਂ "
                   "ਕਮਰਿਆਂ ਦੇ ਅੰਦਰ ਹੋਵੇਗਾ ਅਤੇ ਖਿੜਕੀਆਂ ਬੰਦ ਰੱਖੀਆਂ ਜਾਣਗੀਆਂ। ਦਮੇ ਵਾਲੇ ਬੱਚੇ ਆਪਣੀ ਨਿਯਮਤ ਦਵਾਈ ਨਾਲ ਰੱਖਣ। ",
        "limit": "{name} ਲਈ ਧੂੰਏਂ ਦੀ ਸੂਚਨਾ, {date}: ਪਰਾਲੀ ਦੇ ਧੂੰਏਂ ਨਾਲ ਸਕੂਲ ਦੇ ਸਮੇਂ ਹਵਾ '{cat}' ਸ਼੍ਰੇਣੀ ਤੱਕ ਪਹੁੰਚ ਸਕਦੀ ਹੈ, ਸਭ ਤੋਂ ਵੱਧ "
                 "ਲਗਭਗ {hour} ਵਜੇ (ਅਨੁਮਾਨਿਤ PM2.5 {worst} µg/m³, ਦਾਇਰਾ {lo}-{hi})। ਬਾਹਰ ਕੋਈ ਭਾਰੀ ਪੀਟੀ ਜਾਂ ਖੇਡ ਨਹੀਂ ਹੋਵੇਗੀ, ਸਭਾ ਛੋਟੀ "
                 "ਰੱਖੀ ਜਾਵੇਗੀ, ਅਤੇ ਦਮੇ ਜਾਂ ਦਿਲ/ਫੇਫੜਿਆਂ ਦੀ ਬਿਮਾਰੀ ਵਾਲੇ ਬੱਚੇ ਅੰਦਰ ਰਹਿਣਗੇ। ",
        "ok": "{name} ਲਈ ਹਵਾ ਦੀ ਸੂਚਨਾ, {date}: ਸਕੂਲ ਦੇ ਸਮੇਂ ਧੂੰਏਂ ਦਾ ਕੋਈ ਖ਼ਾਸ ਅਸਰ ਨਹੀਂ ਹੋਣ ਦਾ ਅਨੁਮਾਨ ਹੈ (ਅਨੁਮਾਨਿਤ PM2.5 ਵੱਧ ਤੋਂ ਵੱਧ "
              "{worst} µg/m³, '{cat}')। ਬਾਹਰ ਦੀਆਂ ਆਮ ਗਤੀਵਿਧੀਆਂ ਜਾਰੀ ਰਹਿਣਗੀਆਂ। ",
        "none": "{name} ਲਈ ਹਵਾ ਦੀ ਸੂਚਨਾ, {date}: ਇਸ ਦਿਨ ਦਾ ਧੂੰਆਂ ਪੂਰਵ-ਅਨੁਮਾਨ ਅਜੇ ਉਪਲਬਧ ਨਹੀਂ ਹੈ। ਕਿਰਪਾ ਕਰਕੇ ਕੱਲ੍ਹ ਦੁਬਾਰਾ ਦੇਖੋ। ",
    },
}
_SCRIPT = {"hi": re.compile(r"[ऀ-ॿ]"), "pa": re.compile(r"[਀-੿]")}
LLMCall = Callable[[str, str], str]  # (system_prompt, user_text) -> text
FALLBACK_SCHOOLS = 10  # when no subscriptions/demo file: first N schools in the index
LLM_MAX_SCHOOLS = int(os.environ.get("DHUAAN_ADVISORY_LLM_MAX", "3"))  # LLM notices per run (2 calls each); rest templates


def facts_for(plan: dict) -> dict:
    """The only facts a notice may use (also the grounding reference)."""
    sm = plan.get("summary", {})
    d = date.fromisoformat(plan["date_ist"])
    f = {"school": plan.get("name"), "date_ist": plan["date_ist"], "day": d.day, "month": d.month, "year": d.year,
         "school_hours_ist": plan.get("school_hours_ist"), "level": sm.get("overall_outdoor") or "none"}
    if sm.get("worst_est_pm25") is not None:
        lo, hi = sm.get("worst_est_pm25_band") or [None, None]
        f.update({"worst_hour_ist": sm["worst_hour_ist"], "worst_est_pm25": sm["worst_est_pm25"], "range_low": lo,
                  "range_high": hi, "category": sm["worst_category"], "restricted_hours_ist": sm.get("restricted_hours_ist"),
                  "official_guidance": sm.get("guidance"), "cpcb_health_statement": sm.get("health_statement")})
    return f


def template_notice(lang: str, plan: dict) -> str:
    f = facts_for(plan)
    level = f["level"] if f.get("worst_est_pm25") is not None else "none"
    d = date.fromisoformat(f["date_ist"])
    date_s = f"{d.day} {MONTHS[lang][d.month - 1]} {d.year}"
    text = TEMPLATES[lang][level].format(
        name=f["school"], date=date_s, cat=CAT[lang].get(f.get("category") or "", ""), hour=f.get("worst_hour_ist"),
        worst=f.get("worst_est_pm25"), lo=f.get("range_low"), hi=f.get("range_high"))
    return text + _TAIL[lang]


def _script_ok(lang: str, text: str) -> bool:
    if lang == "en":
        return bool(text) and not _SCRIPT["hi"].search(text) and not _SCRIPT["pa"].search(text)
    # Strict: every letter must be the native script or plain ASCII Latin (for PM2.5, IST, NAQI, school names).
    # Small models sometimes leak Devanagari/Tamil/Kannada/Hebrew letters into Gurmukhi; such a notice is rejected.
    letters = [c for c in text if c.isalpha()]
    native = len(_SCRIPT[lang].findall(text))
    foreign = [c for c in letters if not c.isascii() and not _SCRIPT[lang].match(c) and c not in "µμ"]
    return bool(letters) and not foreign and native / len(letters) >= 0.5


def _strands_llm(model_factory: Callable[[str | None], Any] | None = None) -> LLMCall:
    from strands import Agent

    from dhuaan.agent.agent import TraceRecorder, _call

    def call(system: str, user: str) -> str:
        last: BaseException | None = None
        for mid in models.candidates():
            model = (model_factory or (lambda m: models.build_model(model_id=m, max_tokens=900)))(mid)
            agent = Agent(model=model, tools=[], system_prompt=system, callback_handler=None)
            TraceRecorder().attach(agent)  # counts against the LLM budget
            try:
                text = _call(agent, user)
                call.used = mid  # type: ignore[attr-defined]
                return text
            except Exception as e:
                kind = models.classify_error(e)
                if kind is None:
                    raise
                if kind == "unavailable":
                    models.mark_unavailable(mid)
                last = e
        raise last or RuntimeError("no model available")
    return call


def _parse_json(text: str) -> dict:
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    m = re.search(r"\{.*\}", t, re.S)
    return json.loads(m.group(0)) if m else {}


def build_notices(plan: dict, llm: LLMCall | None) -> tuple[dict, dict, dict]:
    """-> (notice {en,hi,pa}, grounding {verified,total,by_lang}, source {lang: 'llm'|'template'})."""
    facts = facts_for(plan)
    ref = [facts, plan, prompts.STATIC_FACTS]
    notice, source, by_lang = {}, {}, {}

    def accept(lang: str, text: str | None) -> None:
        if text and _script_ok(lang, text):
            g = grounding.check(text, ref)
            if not g["unverified"]:
                notice[lang], source[lang], by_lang[lang] = text.strip(), "llm", g
                return
            log.info("advisory %s %s rejected: unverified %s", plan["school_id"], lang, g["unverified"])
        t = template_notice(lang, plan)
        notice[lang], source[lang], by_lang[lang] = t, "template", grounding.check(t, ref)

    en = None
    if llm and facts.get("worst_est_pm25") is not None:
        try:
            en = llm(prompts.ADVISORY_PROMPT, "Facts (JSON):\n" + json.dumps(facts, ensure_ascii=False))
        except Exception as e:
            log.warning("advisory LLM (en) failed: %s", type(e).__name__)
    accept("en", en)
    tr: dict = {}
    if llm and source["en"] == "llm":
        try:
            tr = _parse_json(llm(prompts.TRANSLATE_PROMPT, notice["en"]))
        except Exception as e:
            log.warning("advisory LLM (translate) failed: %s", type(e).__name__)
    for lang in ("hi", "pa"):
        accept(lang, tr.get(lang) if isinstance(tr, dict) else None)
    g = {"verified": sum(v["verified"] for v in by_lang.values()), "total": sum(v["total"] for v in by_lang.values()),
         "by_lang": {k: {"verified": v["verified"], "total": v["total"]} for k, v in by_lang.items()}}
    return notice, g, source


def _ids_from(obj: Any, schools_only: bool) -> list[str]:
    items = obj.get("places") or obj.get("schools") or obj.get("subscriptions") or [] if isinstance(obj, dict) else obj or []
    out = []
    for it in items:
        if isinstance(it, str):
            out.append(it)
        elif isinstance(it, dict):
            if schools_only and it.get("kind") not in (None, "school"):
                continue
            sid = it.get("school_id") or it.get("place_id") or it.get("id")
            if sid:
                out.append(str(sid))
    return out


def school_ids_default(store: Any) -> list[str]:
    """subscriptions.json + demo schools from demo_places.json; else the first FALLBACK_SCHOOLS schools in the index."""
    ids: list[str] = []
    for fname, schools_only in (("subscriptions.json", False), ("demo_places.json", True)):
        p = DATA_DIR / fname
        if p.exists():
            try:
                ids += _ids_from(json.loads(p.read_text(encoding="utf-8")), schools_only)
            except (ValueError, OSError) as e:
                log.warning("could not read %s: %s", fname, e)
    if not ids:
        idx = store.get_json("latest/receptors_index.json") or {}
        ids = [p["id"] for p in idx.get("places", []) if p.get("kind") == "school"][:FALLBACK_SCHOOLS]
    return list(dict.fromkeys(ids))


def _llm_enabled() -> bool:
    if os.environ.get("DHUAAN_ADVISORY_LLM", "1") == "0":
        return False
    return settings.model_provider == "bedrock" or bool(settings.gemini_api_key)


def generate_all(store: Any, run_id: str, school_ids: Iterable[str] | None = None, *,
                 llm: LLMCall | None | bool = True, date_ist: str | None = None) -> list[str]:
    """Write latest/advisories/<id>.json and runs/<run_id>/advisories/<id>.json; returns the ids written.

    llm: True = use the configured model if enabled (env DHUAAN_ADVISORY_LLM=0 forces templates),
         False/None = templates only, or a callable (system, user) -> text (tests).
    """
    meta = store.get_json("latest/meta.json") or {}
    alpha = float(meta.get("alpha", 1.0))
    if llm is True:
        llm = _strands_llm() if _llm_enabled() else None
    elif llm is False:
        llm = None
    ids = list(school_ids) if school_ids is not None else school_ids_default(store)
    written: list[str] = []
    for sid in ids:
        place = store.get_json(f"latest/places/{sid}.json")
        if not place:
            log.warning("advisory: no places/%s.json, skipped", sid)
            continue
        obs = tools.observed_near(place["lat"], place["lon"])
        plan = rules.school_day_plan(place, alpha, obs, date_ist)
        notice, g, source = build_notices(plan, llm if len(written) < LLM_MAX_SCHOOLS else None)
        used_llm = any(v == "llm" for v in source.values())
        art = {
            "school_id": sid, "name": place.get("name"), "district": place.get("district"), "date_ist": plan["date_ist"],
            "plan": [{k: r[k] for k in ("hour_ist", "est_pm25", "est_pm25_low", "est_pm25_high", "category", "outdoor")}
                     for r in plan["plan"]],
            "summary": plan["summary"], "baseline_basis": plan["baseline_basis"],
            "notice": notice, "notice_source": source, "grounding": g,
            "model": models.model_label(model_id=getattr(llm, "used", None)) if used_llm else "template",
            "run_id": run_id, "generated_utc": iso_utc(now_utc()), "run_t0_ist": ist_str(meta.get("t0_utc")),
            "caveats": plan["caveats"], "sources": plan["sources"],
        }
        store.put_json(f"latest/advisories/{sid}.json", art)
        store.put_json(f"runs/{run_id}/advisories/{sid}.json", art)
        written.append(sid)
    return written


if __name__ == "__main__":
    import argparse

    from dhuaan.store import get_store
    ap = argparse.ArgumentParser(description="Generate school advisories from the latest run")
    ap.add_argument("--school", action="append", help="school id (repeatable); default: subscriptions/demo schools")
    ap.add_argument("--templates-only", action="store_true")
    ap.add_argument("--date", help="YYYY-MM-DD (IST)")
    a = ap.parse_args()
    st = get_store()
    rid = (st.get_json("latest/meta.json") or {}).get("run_id", "none")
    out = generate_all(st, rid, a.school, llm=not a.templates_only, date_ist=a.date)
    for sid in out:
        art = st.get_json(f"latest/advisories/{sid}.json")
        print(json.dumps({k: art[k] for k in ("school_id", "date_ist", "notice", "notice_source", "grounding", "model")},
                         ensure_ascii=False, indent=1))
