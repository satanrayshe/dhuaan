"""Deterministic school-day rules. No LLM here: the plan is pure arithmetic on the forecast.

est total PM2.5 (hour h) = baseline + alpha * smoke(h)
  baseline = latest nearby observed PM2.5 if the reading is < 6 h old, else 60 ug/m3 (top of "satisfactory")
NAQI category (CONTRACTS): good <=30, satisfactory 31-60, moderate 61-90, poor 91-120, very_poor 121-250, severe >250
Outdoor guidance: <=60 "ok", 61-120 "limit", >120 "indoors". School day: 07:00-14:00 IST (hours 07..13).

Caveats (stated in every plan): NAQI breakpoints are 24-hour averages and we apply them to hourly estimates as a
proxy; the observed baseline already contains whatever smoke is present now, so during an episode the total can be
an overestimate; alpha is uncalibrated until the backtest runs (meta.calibrated = false).
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta

from dhuaan.agent import timeutil
from dhuaan.agent.timeutil import IST, hours_between, iso_utc, parse_utc

DEFAULT_BASELINE = 60.0
OBS_MAX_AGE_H = 6.0
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
    "Estimate, not a measurement: total = baseline + alpha x smoke forecast.",
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


def baseline_pm25(obs: dict | None, now: datetime | None = None) -> tuple[float, str]:
    """(baseline ug/m3, basis). obs is an openaq.latest_near() dict or None."""
    now = now or timeutil.now_utc()
    if obs and obs.get("pm25") is not None and obs.get("measured_utc"):
        t = parse_utc(obs["measured_utc"])
        if t is not None:
            age = hours_between(t, now)
            if -1.0 <= age < OBS_MAX_AGE_H and float(obs["pm25"]) >= 0:
                return float(obs["pm25"]), f"observed at {obs.get('name', 'nearest station')} ({age:.1f} h old)"
    return DEFAULT_BASELINE, "default 60 ug/m3 (no nearby observation under 6 h old)"


def est_total(baseline: float, alpha: float, smoke: float | None) -> int | None:
    if smoke is None:
        return None
    return int(round(baseline + alpha * max(0.0, float(smoke))))


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
    base, basis = baseline_pm25(obs, now)
    plan = []
    for h in range(SCHOOL_START_H, SCHOOL_END_H):
        t = datetime(d.year, d.month, d.day, h, tzinfo=IST)
        smoke = value_at(place.get("series"), t0, t)
        lo = value_at(place.get("p10"), t0, t)
        hi = value_at(place.get("p90"), t0, t)
        est = est_total(base, alpha, smoke)
        row = {"hour_ist": f"{h:02d}:00", "utc": iso_utc(t), "smoke_index": None if smoke is None else round(smoke, 2),
               "est_pm25": est, "est_pm25_low": est_total(base, alpha, lo), "est_pm25_high": est_total(base, alpha, hi),
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
        "baseline_pm25": round(base, 1), "baseline_basis": basis, "alpha": alpha,
        "rule": f"est_pm25 = baseline + alpha x smoke; outdoor ok <= {OK_MAX}, limit {OK_MAX + 1}-{LIMIT_MAX}, indoors > {LIMIT_MAX}",
        "plan": plan, "summary": summary, "caveats": CAVEATS, "sources": SOURCES,
    }
