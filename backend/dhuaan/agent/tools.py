"""Read-only Strands tools. Docstrings are the tool descriptions the model sees; keep them precise.

Every tool returns a JSON-serialisable dict. Times are given in IST ("2026-10-08 21:00 IST") with the UTC original
alongside, so both the model and the grounding check can use them.
"""
from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any

from strands import tool

from dhuaan.agent import data, rules, timeutil
from dhuaan.agent.timeutil import IST, hours_between, ist_str, parse_utc
from dhuaan.geo import regions

log = logging.getLogger(__name__)
RUN_STALE_H = 6.0
_OBS_TTL_S = 900.0
_obs_cache: dict[str, tuple[float, dict | None]] = {}
SMOKE_SOURCE = "Dhuaan smoke model (satellite fire detections + GFS winds, Lagrangian particles)"


def _not_found(place_id: str) -> dict:
    return {"error": f"unknown place_id '{place_id}'. Call search_place first to get a valid id."}


def _run_info() -> dict:
    m = data.meta() or {}
    t0 = parse_utc(m.get("t0_utc"))
    age = round(hours_between(t0, timeutil.now_utc()), 1) if t0 else None
    return {"run_id": m.get("run_id"), "run_t0_ist": ist_str(t0), "run_age_hours": age,
            "stale": bool(age is None or age > RUN_STALE_H), "alpha": data.alpha(), "calibrated": bool(m.get("calibrated", False)),
            "alpha_by_region": m.get("alpha_by_region"), "calibration_basis": m.get("calibration_basis")}


def observed_near(lat: float, lon: float) -> dict | None:
    """Nearest station PM2.5 via dhuaan.ingest.openaq (lazy import; cached 15 min; None if unavailable)."""
    key = f"{lat:.2f},{lon:.2f}"
    hit = _obs_cache.get(key)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    obs: dict | None = None
    try:
        from dhuaan.ingest import openaq  # written by INGEST; may be absent
        obs = openaq.latest_near(lat, lon, radius_km=50)
    except Exception as e:  # ImportError, network, missing key
        log.warning("openaq unavailable: %s", type(e).__name__)
        obs = None
    _obs_cache[key] = (time.monotonic() + _OBS_TTL_S, obs)
    return obs


def _published_baseline(place_id: str) -> dict | None:
    """The measured baseline the advisory step published in latest/baselines.json, so the chat answer and the
    Schools page use the same reading. None if absent or not a measurement."""
    try:
        from dhuaan.store import get_store
        doc = get_store().get_json("latest/baselines.json") or {}
    except Exception:
        return None
    b = (doc.get("places") or {}).get(place_id)
    if not b or b.get("source") != "measured" or b.get("pm25") is None:
        return None
    return {"pm25": b["pm25"], "measured_utc": b.get("measured_utc"), "name": b.get("station"),
            "distance_km": b.get("distance_km")}


def _short(t) -> str:
    return t.astimezone(IST).strftime("%d %b %H:%M")


@tool
def search_place(query: str) -> dict:
    """Find places (villages, towns, cities, schools, wards) in the forecast domain by name or district.

    Use this first whenever the user names a place, to get its place_id.

    Args:
        query: Place name or district in English letters, e.g. "Khanna", "Ludhiana", "Sunrise school".
            Transliterate Hindi/Punjabi names to English first.
    """
    hits = data.search(query, limit=5)
    return {"query": query, "places": [
        {k: p.get(k) for k in ("id", "name", "kind", "district", "state", "lat", "lon")} for p in hits],
        "note": "" if hits else "No match. Try a nearby town or the district name."}


@tool
def get_smoke_forecast(place_id: str, hours: int = 72) -> dict:
    """Stubble-smoke forecast for one place: arrival time, peak, and a 3-hourly series with an uncertainty band.

    Returns smoke index (model units), smoke-attributable PM2.5 (alpha x smoke) and estimated total PM2.5
    (baseline + smoke) with the NAQI category, all times in IST.

    Args:
        place_id: Place id from search_place.
        hours: How many hours ahead to summarise from now (1-72).
    """
    p = data.place(place_id)
    if not p:
        return _not_found(place_id)
    hours = max(1, min(int(hours), 72))
    alpha = data.alpha_for(p)
    t0 = parse_utc(p["t0_utc"])
    now = timeutil.now_utc()
    start = max(24, min(96, rules.series_index(t0, now.replace(minute=0, second=0, microsecond=0))))
    end = min(96, start + hours)
    s, lo, hi = p["series"], p.get("p10") or p["series"], p.get("p90") or p["series"]
    obs = observed_near(p["lat"], p["lon"])
    base, basis = rules.baseline_pm25(obs, now)

    def row(i: int) -> dict:
        t = t0 + timedelta(hours=i - 24)
        est = rules.est_total(base, alpha, s[i])
        return {"time_ist": _short(t), "smoke_index": s[i], "smoke_pm25": round(alpha * s[i]),
                "est_pm25": est, "est_pm25_band": [rules.est_total(base, alpha, lo[i]), rules.est_total(base, alpha, hi[i])],
                "category": rules.naqi_category(est)}

    window = range(start, end + 1)
    pk = max(window, key=lambda i: s[i])
    daily: dict[str, int] = {}
    for i in window:
        d = (t0 + timedelta(hours=i - 24)).astimezone(IST).strftime("%Y-%m-%d")
        daily[d] = max(daily.get(d, 0), rules.est_total(base, alpha, s[i]) or 0)
    arrival = p.get("arrival_utc")
    aw = p.get("arrival_window")
    return {
        "place": {k: p.get(k) for k in ("id", "name", "kind", "district", "state")},
        "from_ist": _short(t0 + timedelta(hours=start - 24)), "to_ist": _short(t0 + timedelta(hours=end - 24)),
        "arrival_ist": ist_str(arrival) if arrival else None,
        "arrival_window_ist": [ist_str(aw[0]), ist_str(aw[1])] if aw else None,
        "arrival_note": "first hour the median forecast crosses the arrival threshold" if arrival else "smoke not expected to cross the arrival threshold in this run",
        "peak": {"time_ist": ist_str(t0 + timedelta(hours=pk - 24)), "smoke_index": s[pk], "smoke_pm25": round(alpha * s[pk]),
                 "est_pm25": rules.est_total(base, alpha, s[pk]),
                 "est_pm25_band": [rules.est_total(base, alpha, lo[pk]), rules.est_total(base, alpha, hi[pk])],
                 "category": rules.naqi_category(rules.est_total(base, alpha, s[pk]) or 0)},
        "daily_max_est_pm25": daily,
        "series_3h": [row(i) for i in range(start, end + 1, 3)],
        "baseline_pm25": round(base, 1), "baseline_basis": basis,
        "alpha": alpha, "alpha_region": regions.region_of(p.get("district"), p.get("state")),
        "uncertainty": "est_pm25_band is the p10-p90 spread across ensemble members; alpha is "
                       + ("a provisional calibration against stations" if (data.meta() or {}).get("calibrated") else "NOT yet calibrated (alpha=1.0 default), so PM2.5 values are rough"),
        "units": "est. smoke PM2.5 (provisional calibration) in ug/m3; smoke_index is relative model units",
        "source": SMOKE_SOURCE, "run": _run_info(),
    }


@tool
def get_attribution(place_id: str) -> dict:
    """Where the smoke reaching a place comes from over the next 48 hours: shares by source district and the top fire clusters.

    Clusters are described by village/tehsil, district and coordinates only (never by person).

    Args:
        place_id: Place id from search_place.
    """
    p = data.place(place_id)
    if not p:
        return _not_found(place_id)
    tops = []
    for tc in p.get("top_clusters", []):
        c = data.cluster(tc.get("cluster_id")) or {}
        tops.append({"cluster_id": tc.get("cluster_id"), "share_pct": round(100 * float(tc.get("share", 0))),
                     "near": c.get("nearest_place"), "district": c.get("district"), "state": c.get("state"),
                     "lat": round(c["lat"], 3) if "lat" in c else None, "lon": round(c["lon"], 3) if "lon" in c else None,
                     "n_detections": c.get("n_detections"), "last_seen_ist": ist_str(c.get("last_seen_utc"))})
    return {"place": {k: p.get(k) for k in ("id", "name", "district", "state")},
            "window": "next 48 hours from the run start",
            "districts": [{"district": a.get("district"), "state": a.get("state"), "share_pct": round(100 * float(a.get("share", 0)))}
                          for a in p.get("attribution", [])],
            "top_clusters": tops, "source": SMOKE_SOURCE, "run": _run_info()}


@tool
def get_air_quality_now(place_id: str) -> dict:
    """Latest measured PM2.5 at the nearest monitoring station (CPCB/state stations via OpenAQ) within 50 km of a place.

    Args:
        place_id: Place id from search_place.
    """
    p = data.place(place_id)
    if not p:
        return _not_found(place_id)
    obs = observed_near(p["lat"], p["lon"])
    if not obs or obs.get("pm25") is None:
        return {"place": p.get("name"), "available": False,
                "note": "No station reading within 50 km is available right now.", "source": "OpenAQ"}
    t = parse_utc(obs.get("measured_utc"))
    age = round(hours_between(t, timeutil.now_utc()), 1) if t else None
    pm = round(float(obs["pm25"]))
    return {"place": p.get("name"), "available": True, "station": obs.get("name"), "station_id": obs.get("station_id"),
            "distance_km": round(float(obs.get("distance_km") or 0), 1), "pm25": pm, "unit": obs.get("unit", "ug/m3"),
            "category": rules.naqi_category(pm), "category_range": rules.CATEGORY_RANGES[rules.naqi_category(pm)],
            "measured_ist": ist_str(t), "age_hours": age, "stale": bool(age is None or age > rules.OBS_MAX_AGE_H),
            "note": "Single latest reading; NAQI categories are defined on 24-hour averages.",
            "source": "OpenAQ (CPCB and state pollution control board stations)"}


@tool
def get_fire_clusters(district: str | None = None, limit: int = 10) -> dict:
    """Active farm-fire clusters ranked by how much smoke exposure they cause downwind (person-hours over the next 48 h).

    Args:
        district: Optional source district to filter by, e.g. "Sangrur". Omit for the whole region.
        limit: Maximum clusters to return (1-20).
    """
    limit = max(1, min(int(limit), 20))
    cs = data.clusters()
    if district:
        d = district.strip().lower()
        cs = [c for c in cs if (c.get("district") or "").lower() == d or (c.get("district") or "").lower().startswith(d)]
    cs = sorted(cs, key=lambda c: -(c.get("exposure_person_hours") or 0))[:limit]
    return {"district": district, "count": len(cs), "clusters": [{
        "cluster_id": c.get("cluster_id"), "rank": c.get("rank"), "near": c.get("nearest_place"),
        "district": c.get("district"), "state": c.get("state"), "lat": round(c.get("lat", 0), 3), "lon": round(c.get("lon", 0), 3),
        "n_detections": c.get("n_detections"), "frp_sum_mw": round(c.get("frp_sum_mw") or 0, 1),
        "exposure_share_pct": round(100 * float(c.get("exposure_share") or 0), 1),
        "first_seen_ist": ist_str(c.get("first_seen_utc")), "last_seen_ist": ist_str(c.get("last_seen_utc")),
        "downwind": [d.get("name") for d in c.get("downwind", [])][:3]} for c in cs],
        "source": "NASA FIRMS / satellite fire detections, clustered; exposure from the Dhuaan smoke model", "run": _run_info()}


@tool
def get_school_day_plan(school_id: str, date_ist: str | None = None) -> dict:
    """Deterministic hour-by-hour outdoor-activity plan for a school day (07:00-14:00 IST), from fixed rules, not opinion.

    est PM2.5 = baseline + alpha x smoke; outdoor "ok" <= 60, "limit" 61-120 (no strenuous PE, short assembly,
    sensitive children indoors), "indoors" > 120. Based on CPCB NAQI health statements and GRAP.

    Args:
        school_id: Place id of the school (or any place) from search_place.
        date_ist: Date in IST as YYYY-MM-DD. Omit for the next school day.
    """
    p = data.place(school_id)
    if not p:
        return _not_found(school_id)
    try:
        plan = rules.school_day_plan(p, data.alpha_for(p), _published_baseline(school_id) or observed_near(p["lat"], p["lon"]),
                                     date_ist or None)
    except ValueError:
        return {"error": "date_ist must be YYYY-MM-DD"}
    plan["run"] = _run_info()
    return plan


@tool
def get_data_freshness() -> dict:
    """How fresh the data is: model run time, age, and each input source's last fetch and latest observation (IST)."""
    m = data.meta()
    if not m:
        return {"available": False, "note": "No model run has been published yet."}
    now = timeutil.now_utc()
    srcs = []
    for s in m.get("sources", []):
        lo = parse_utc(s.get("latest_obs_utc"))
        srcs.append({"name": s.get("name"), "ok": s.get("ok"), "count": s.get("count"),
                     "fetched_ist": ist_str(s.get("fetched_utc")), "latest_obs_ist": ist_str(lo),
                     "latest_obs_age_hours": round(hours_between(lo, now), 1) if lo else None, "note": s.get("note") or ""})
    return {"available": True, **_run_info(), "generated_ist": ist_str(m.get("generated_utc")),
            "now_ist": ist_str(now), "model_version": m.get("model_version"), "members": m.get("members"),
            "afternoon_mode": m.get("afternoon_mode"), "sources": srcs,
            "stale_rule": f"run is stale if older than {RUN_STALE_H:.0f} hours"}


ALL_TOOLS = [search_place, get_smoke_forecast, get_attribution, get_air_quality_now,
             get_fire_clusters, get_school_day_plan, get_data_freshness]


def summarize(name: str, result: Any) -> str:
    """One-line human summary of a tool result for tool_trace."""
    if not isinstance(result, dict):
        return str(result)[:120]
    if "error" in result:
        return f"error: {result['error']}"[:160]
    try:
        if name == "search_place":
            ps = result.get("places", [])
            return f"{len(ps)} match(es)" + (f": {ps[0]['name']} ({ps[0]['id']})" if ps else "")
        if name == "get_smoke_forecast":
            pk = result["peak"]
            return (f"{result['place']['name']}: arrival {result.get('arrival_ist') or 'none'}; peak {pk['time_ist']} "
                    f"~{pk['est_pm25']} ug/m3 ({pk['category']})")
        if name == "get_attribution":
            top = result.get("districts", [])[:2]
            return "top sources: " + ", ".join(f"{d['district']} {d['share_pct']}%" for d in top)
        if name == "get_air_quality_now":
            if not result.get("available"):
                return "no station reading"
            return f"{result['station']}: PM2.5 {result['pm25']} at {result['measured_ist']}"
        if name == "get_fire_clusters":
            return f"{result['count']} cluster(s)" + (f", top near {result['clusters'][0]['near']}" if result["clusters"] else "")
        if name == "get_school_day_plan":
            sm = result.get("summary", {})
            return f"{result['date_ist']}: overall {sm.get('overall_outdoor')}, worst {sm.get('worst_hour_ist')} ~{sm.get('worst_est_pm25')} ug/m3"
        if name == "get_data_freshness":
            return f"run {result.get('run_id')} age {result.get('run_age_hours')} h" + (" (stale)" if result.get("stale") else "")
    except (KeyError, IndexError, TypeError):
        pass
    return name
