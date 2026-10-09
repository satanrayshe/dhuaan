"""Deterministic school-day rules. No LLM here: the plan is pure arithmetic on the forecast.

est total PM2.5 (hour h) = baseline + alpha * max(0, smoke(h) - smoke(t_obs))  [t_obs = baseline measurement time]
  baseline = the nearest station's latest PM2.5 if it is <= 36 h old (CPCB data reach OpenAQ ~20 h late, so a
             6 h rule never fired), stated with its age and distance; else 60 ug/m3 (top of "satisfactory")
  alpha    = the region-appropriate calibration (meta.alpha_by_region via dhuaan.geo.regions; provisional)
NAQI category (CONTRACTS): good <=30, satisfactory 31-60, moderate 61-90, poor 91-120, very_poor 121-250, severe >250
Outdoor guidance: <=60 "ok", 61-120 "limit", >120 "indoors". School day: 07:00-14:00 IST (hours 07..13).

Caveats (stated in every plan): NAQI breakpoints are 24-hour averages and we apply them to hourly estimates as a
proxy; the observed baseline already contains whatever smoke is present now, so during an episode the total can be
an overestimate; alpha is a provisional calibration (pooled pre-registered, or exploratory regional).
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta

from dhuaan.agent import timeutil
from dhuaan.agent.timeutil import IST, hours_between, iso_utc, parse_utc

DEFAULT_BASELINE = 60.0
OBS_MAX_AGE_H = 36.0
EST_LABEL = "est. PM2.5, background + smoke (provisional calibration)"  # school-plan totals; smoke-only values use geo.regions.EST_LABEL
SCHOOL_START_H, SCHOOL_END_H = 7, 14  # [07:00, 14:00) IST
OK_MAX, LIMIT_MAX = 60, 120

CATEGORIES = ("good", "satisfactory", "moderate", "poor", "very_poor", "severe")
CATEGORY_RANGES = {
    "good": "0-30", "satisfactory": "31-60", "moderate": "61-90",
    "poor": "91-120", "very_poor": "121-250", "severe": ">250",
}
# CPCB National AQI (2014) "possible health impacts" statements, verbatim.
HEALTH_STATEMENTS = {
    "good": "Minimal impact",
    "satisfactory": "Minor breathing discomfort to sensitive people",
    "moderate": "Breathing discomfort to the people with lung disease such as asthma and discomfort to people with heart disease, children and older adults",
    "poor": "Breathing discomfort to most people on prolonged exposure",
    "very_poor": "Respiratory illness on prolonged exposure",
    "severe": "Affects healthy people and seriously impacts those with existing diseases",
}
OUTDOOR_GUIDANCE = {
    "ok": "Normal outdoor activity. Children with asthma or heart/lung conditions should keep their usual medicines and avoid long hard exercise if they feel discomfort.",
    "limit": "No strenuous outdoor PE or sports; keep morning assembly short or hold it indoors; children with asthma or other heart/lung conditions stay indoors.",
    "indoors": "Hold assembly, PE and recess indoors; keep windows and doors closed during these hours; no outdoor sports.",
}
SOURCES = [
    {"name": "CPCB National Air Quality Index (2014): PM2.5 breakpoints and health statements",
     "url": "https://cpcb.nic.in/National-Air-Quality-Index/"},
    {"name": "CAQM Graded Response Action Plan (GRAP) for NCR, revised schedule (school and outdoor-activity measures by AQI stage)",
     "url": "https://caqm.nic.in/"},
    {"name": "MoHFW / NPCCHH health advisory on air pollution (protecting children and vulnerable groups)",
     "url": "https://ncdc.mohfw.gov.in/"},
]
CAVEATS = [
    "Estimate, not a measurement: est. PM2.5 (provisional calibration) = background baseline + alpha x (forecast smoke minus the smoke already present when the baseline was measured).",
    "The baseline is the nearest station's latest reading if it is at most 36 h old (CPCB data arrive about 20 h late), otherwise a fixed 60 ug/m3.",
    "NAQI breakpoints are 24-hour averages; applied here to hourly estimates as a guide.",
    "If the baseline is a recent observation it already includes current smoke, so totals may be overstated during an episode.",
]


def naqi_category(pm25: float) -> str:
    v = round(pm25)
    if v <= 30:
        return "good"
    if v <= 60:
        return "satisfactory"
    if v <= 90:
        return "moderate"
    if v <= 120:
        return "poor"
    if v <= 250:
        return "very_poor"
    return "severe"


def outdoor_level(pm25: float) -> str:
    v = round(pm25)
    if v <= OK_MAX:
        return "ok"
    if v <= LIMIT_MAX:
        return "limit"
    return "indoors"


_LEVEL_ORDER = {"ok": 0, "limit": 1, "indoors": 2}


NO_RECENT = "no recent nearby reading"


def baseline_info(obs: dict | None, now: datetime | None = None) -> dict:
    """{pm25, source: "measured"|"default", basis (human text), age_h, station, distance_km, measured_utc}.
    obs is an openaq.latest_near() dict or None. A reading counts if it is at most OBS_MAX_AGE_H old."""
    now = now or timeutil.now_utc()
    if obs and obs.get("pm25") is not None and obs.get("measured_utc"):
        t = parse_utc(obs["measured_utc"])
        if t is not None:
            age = hours_between(t, now)
            if -1.0 <= age <= OBS_MAX_AGE_H and float(obs["pm25"]) >= 0:
                age_h = max(0, round(age))
                name = obs.get("name") or "nearest station"
                dist = obs.get("distance_km")
                where = f"{name}, {round(float(dist))} km" if dist is not None else name
                return {"pm25": float(obs["pm25"]), "source": "measured", "age_h": age_h, "station": name,
                        "distance_km": None if dist is None else round(float(dist), 1), "measured_utc": obs["measured_utc"],
                        "basis": f"measured {age_h} h ago at {where}"}
    return {"pm25": DEFAULT_BASELINE, "source": "default", "age_h": None, "station": None, "distance_km": None,
            "measured_utc": None, "basis": f"{NO_RECENT}; default {DEFAULT_BASELINE:.0f} ug/m3"}


def baseline_pm25(obs: dict | None, now: datetime | None = None) -> tuple[float, str]:
    """(baseline ug/m3, basis text). See baseline_info."""
    b = baseline_info(obs, now)
    return b["pm25"], b["basis"]


def est_total(baseline: float, alpha: float, smoke: float | None, smoke_ref: float = 0.0) -> int | None:
    """baseline + alpha x (smoke - smoke already in the baseline), never below the baseline."""
    if smoke is None:
        return None
    return int(round(baseline + alpha * max(0.0, float(smoke) - float(smoke_ref))))


def series_index(t0: datetime, t: datetime) -> int:
    """Index of the hour containing t in the 97-hour arrays (index 0 = t0 - 24 h)."""
    return 24 + math.floor(hours_between(t0, t) + 1e-9)


def value_at(arr: list[float] | None, t0: datetime, t: datetime) -> float | None:
    """Array value at time t, linearly interpolated between hourly (UTC) steps; IST hours fall on :30 UTC."""
    if not arr:
        return None
    x = 24 + hours_between(t0, t)
    i = math.floor(x + 1e-9)
    if i < 0 or i >= len(arr):
        return None
    frac = x - i
    if frac < 1e-6 or i + 1 >= len(arr):
        return float(arr[i])
    return float(arr[i]) * (1 - frac) + float(arr[i + 1]) * frac


def default_school_date(now: datetime | None = None) -> date:
    """Today (IST) if the school day hasn't ended yet, else tomorrow."""
    n = (now or timeutil.now_utc()).astimezone(IST)
    return n.date() if n.hour < SCHOOL_END_H else n.date() + timedelta(days=1)


def school_day_plan(place: dict, alpha: float, obs: dict | None = None,
                    date_ist: str | date | None = None, now: datetime | None = None) -> dict:
    """Hourly plan for 07:00-14:00 IST on date_ist from a places/<id>.json artifact."""
    now = now or timeutil.now_utc()
    if isinstance(date_ist, str) and date_ist:
        d = date.fromisoformat(date_ist)
    elif isinstance(date_ist, date):
        d = date_ist
    else:
        d = default_school_date(now)
    t0 = parse_utc(place["t0_utc"])
    bi = baseline_info(obs, now)
    base, basis = bi["pm25"], bi["basis"]
    # A measured baseline already contains the smoke present at measurement time; add only the change since then
    # (otherwise a large regional alpha double-counts today's smoke).
    smoke_ref = 0.0
    if bi["source"] == "measured" and bi.get("measured_utc"):
        ref = value_at(place.get("series"), t0, parse_utc(bi["measured_utc"]))
        smoke_ref = float(ref) if ref is not None else 0.0
    plan = []
    for h in range(SCHOOL_START_H, SCHOOL_END_H):
        t = datetime(d.year, d.month, d.day, h, tzinfo=IST)
        smoke = value_at(place.get("series"), t0, t)
        lo = value_at(place.get("p10"), t0, t)
        hi = value_at(place.get("p90"), t0, t)
        est = est_total(base, alpha, smoke, smoke_ref)
        e_lo, e_hi = est_total(base, alpha, lo, smoke_ref), est_total(base, alpha, hi, smoke_ref)
        row = {"hour_ist": f"{h:02d}:00", "utc": iso_utc(t), "smoke_index": None if smoke is None else round(smoke, 2),
               "est_pm25": est, "est_pm25_low": est if e_lo is None else min(e_lo, est or e_lo),
               "est_pm25_high": est if e_hi is None else max(e_hi, est or e_hi),
               "category": naqi_category(est) if est is not None else None,
               "outdoor": outdoor_level(est) if est is not None else None}
        plan.append(row)
    known = [r for r in plan if r["est_pm25"] is not None]
    summary: dict = {"hours_forecast": len(known)}
    if known:
        worst = max(known, key=lambda r: r["est_pm25"])
        overall = max((r["outdoor"] for r in known), key=_LEVEL_ORDER.__getitem__)
        affected = [r["hour_ist"] for r in known if r["outdoor"] != "ok"]
        summary.update({
            "worst_hour_ist": worst["hour_ist"], "worst_est_pm25": worst["est_pm25"],
            "worst_est_pm25_band": [worst["est_pm25_low"], worst["est_pm25_high"]],
            "worst_category": worst["category"], "overall_outdoor": overall,
            "restricted_hours_ist": affected,
            "guidance": OUTDOOR_GUIDANCE[overall],
            "health_statement": HEALTH_STATEMENTS[worst["category"]],
        })
    else:
        summary["note"] = "The forecast run does not cover this date."
    return {
        "school_id": place["id"], "name": place.get("name"), "district": place.get("district"),
        "date_ist": d.isoformat(), "school_hours_ist": f"{SCHOOL_START_H:02d}:00-{SCHOOL_END_H:02d}:00",
        "baseline_pm25": round(base, 1), "baseline_basis": basis, "baseline_source": bi["source"],
        "baseline_age_h": bi["age_h"], "baseline_station": bi["station"], "baseline_distance_km": bi["distance_km"],
        "alpha": alpha, "est_label": EST_LABEL,
        "rule": f"est_pm25 = baseline + alpha x max(0, smoke - smoke at baseline time); outdoor ok <= {OK_MAX}, limit {OK_MAX + 1}-{LIMIT_MAX}, indoors > {LIMIT_MAX}",
        "plan": plan, "summary": summary, "caveats": CAVEATS, "sources": SOURCES,
    }
