"""OpenAQ: PM2.5 stations in DOMAIN (v3 API, X-API-Key, 60 req/min) and the public S3 archive for the backtest.

- stations(): every location in DOMAIN with a pm25 sensor (reference monitors and low-cost sensors).
  A static copy lives in backend/data/aq_stations.json (build with `python -m dhuaan.ingest.openaq`).
- latest_near(lat, lon, radius_km=50): newest PM2.5 at the nearest reporting station, preferring reference
  monitors (CPCB/DPCC/state boards) over low-cost sensors. The agent tool depends on the exact return shape.
- fetch_archive(location_id, day): 15-min records from s3://openaq-data-archive (no key), PM2.5 only.
  Archive files are per local (IST) day and timestamps carry +05:30; we convert to UTC.
"""
from __future__ import annotations

import csv
import gzip
import io
import json
import logging
import math
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from dhuaan.config import DATA_DIR, DOMAIN, settings
from dhuaan.ingest.common import fetch, iso_z, now_utc, source_status

log = logging.getLogger("dhuaan.ingest.openaq")

API = "https://api.openaq.org/v3"
ARCHIVE = "https://openaq-data-archive.s3.amazonaws.com/records/csv.gz"
PM25_PARAMETER_ID = 2
STATIONS_FILE = DATA_DIR / "aq_stations.json"
MAX_AGE_H = 36         # CPCB data reaches OpenAQ ~20 h late (seen 8 Oct 2026); older readings are skipped
_MIN_INTERVAL_S = 1.05  # stay under 60 requests/min


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


_last_call = 0.0


def _api(path: str, params: dict[str, Any] | None = None, use_cache: bool | None = None) -> dict[str, Any]:
    global _last_call
    if not settings.openaq_api_key:
        raise RuntimeError("OPENAQ_API_KEY not set")
    wait = _MIN_INTERVAL_S - (time.monotonic() - _last_call)
    if wait > 0 and not use_cache:
        time.sleep(wait)
    _last_call = time.monotonic()
    body = fetch(f"{API}{path}", namespace="openaq", params=params, headers={"X-API-Key": settings.openaq_api_key},
                 timeout=30, use_cache=use_cache)
    return json.loads(body)


def parse_locations(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """v3 /locations results -> station records (only those with a pm25 sensor, inside DOMAIN)."""
    out = []
    for loc in results:
        pm = [s for s in loc.get("sensors") or [] if (s.get("parameter") or {}).get("name") == "pm25"]
        c = loc.get("coordinates") or {}
        lat, lon = c.get("latitude"), c.get("longitude")
        if not pm or lat is None or lon is None:
            continue
        if not (DOMAIN["lat_min"] <= lat <= DOMAIN["lat_max"] and DOMAIN["lon_min"] <= lon <= DOMAIN["lon_max"]):
            continue
        out.append({
            "id": int(loc["id"]), "name": (loc.get("name") or "").strip(), "lat": round(float(lat), 5),
            "lon": round(float(lon), 5), "provider": (loc.get("provider") or {}).get("name") or "unknown",
            "is_monitor": bool(loc.get("isMonitor")), "pm25_sensor_ids": sorted(int(x["id"]) for x in pm),
            "last_utc": (loc.get("datetimeLast") or {}).get("utc"),
        })
    return sorted(out, key=lambda s: s["id"])


def fetch_stations(use_cache: bool | None = None) -> list[dict[str, Any]]:
    bbox = f"{DOMAIN['lon_min']},{DOMAIN['lat_min']},{DOMAIN['lon_max']},{DOMAIN['lat_max']}"
    results: list[dict[str, Any]] = []
    page = 1
    while True:
        j = _api("/locations", {"bbox": bbox, "parameters_id": PM25_PARAMETER_ID, "limit": 1000, "page": page},
                 use_cache=use_cache)
        results.extend(j.get("results") or [])
        found = (j.get("meta") or {}).get("found")
        if not j.get("results") or not isinstance(found, int) or len(results) >= found:
            break
        page += 1
    return parse_locations(results)


def load_stations(path: Path = STATIONS_FILE) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))["stations"] if path.exists() else []


def write_stations(stations: list[dict[str, Any]], path: Path = STATIONS_FILE) -> None:
    doc = {"source": "OpenAQ v3 /locations (bbox = DOMAIN, parameter pm25)", "generated_utc": iso_z(now_utc()),
           "licence": "per-provider; CPCB/DPCC/state boards via OpenAQ; see SOURCES.md", "stations": stations}
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=0), encoding="utf-8")


def _recent(st: dict[str, Any], now: datetime, days: int = 3) -> bool:
    try:
        return datetime.fromisoformat(st["last_utc"].replace("Z", "+00:00")) >= now - timedelta(days=days)
    except (KeyError, AttributeError, TypeError, ValueError):
        return False


_latest_cache: dict[int, tuple[float, dict[str, Any] | None]] = {}


def latest_pm25(station: dict[str, Any]) -> tuple[float, str] | None:
    """(value, measured_utc) of the station's PM2.5 sensor, or None. Memoised for 10 minutes."""
    sid = station["id"]
    hit = _latest_cache.get(sid)
    if hit and time.monotonic() - hit[0] < 600:
        r = hit[1]
    else:
        j = _api(f"/locations/{sid}/latest", use_cache=False)
        ids = set(station.get("pm25_sensor_ids") or [])
        rs = [x for x in j.get("results") or [] if x.get("sensorsId") in ids and x.get("value") is not None]
        r = max(rs, key=lambda x: (x.get("datetime") or {}).get("utc") or "", default=None)
        _latest_cache[sid] = (time.monotonic(), r)
    if not r or r.get("value") is None:
        return None
    return float(r["value"]), (r.get("datetime") or {}).get("utc")


def latest_near(lat: float, lon: float, radius_km: float = 50, *, stations: list[dict[str, Any]] | None = None,
                now: datetime | None = None, max_tries: int = 4) -> dict[str, Any] | None:
    """Newest PM2.5 near a point: {station_id, name, lat, lon, pm25, unit, measured_utc, distance_km} | None.

    Candidates within radius_km that reported in the last 3 days, reference monitors first, then by distance.
    A reading older than MAX_AGE_H hours or a negative/absurd value (<0 or >2000) is skipped.
    """
    now = now or now_utc()
    stations = load_stations() if stations is None else stations
    cands = []
    for st in stations:
        d = haversine_km(lat, lon, st["lat"], st["lon"])
        if d <= radius_km and _recent(st, now):
            cands.append((not st.get("is_monitor", False), d, st))
    cands.sort(key=lambda c: (c[0], c[1]))
    for _, d, st in cands[:max_tries]:
        try:
            got = latest_pm25(st)
        except Exception as e:
            log.warning("OpenAQ latest for %s failed: %s", st["id"], e)
            continue
        if not got:
            continue
        val, measured = got
        try:
            age_h = (now - datetime.fromisoformat(measured.replace("Z", "+00:00"))).total_seconds() / 3600
        except (AttributeError, ValueError):
            continue
        if age_h > MAX_AGE_H or not 0 <= val <= 2000:
            continue
        return {"station_id": st["id"], "name": st["name"], "lat": st["lat"], "lon": st["lon"], "pm25": round(val, 1),
                "unit": "µg/m³", "measured_utc": iso_z(datetime.fromisoformat(measured.replace("Z", "+00:00"))),
                "distance_km": round(d, 1)}
    return None


# ---------- archive (backtest) ----------

def archive_url(location_id: int, day: date) -> str:
    return (f"{ARCHIVE}/locationid={location_id}/year={day.year}/month={day.month:02d}/"
            f"location-{location_id}-{day:%Y%m%d}.csv.gz")


def parse_archive_csv(text: str, parameter: str = "pm25") -> list[dict[str, Any]]:
    """[{t (UTC ISO Z), value, sensor_id}] sorted by time."""
    out = []
    for row in csv.DictReader(io.StringIO(text.lstrip("﻿"))):
        if row.get("parameter") != parameter:
            continue
        try:
            t = datetime.fromisoformat(row["datetime"]).astimezone(timezone.utc)
            v = float(row["value"])
        except (KeyError, ValueError, TypeError):
            continue
        out.append({"t": iso_z(t), "value": v, "sensor_id": int(row.get("sensors_id") or 0)})
    return sorted(out, key=lambda r: r["t"])


def fetch_archive(location_id: int, day: date, parameter: str = "pm25",
                  use_cache: bool | None = True) -> list[dict[str, Any]]:
    """PM2.5 records for one local day ([] when the archive has no file for that day)."""
    try:
        body = fetch(archive_url(location_id, day), namespace="openaq_archive", timeout=60, use_cache=use_cache)
    except RuntimeError as e:
        if "HTTP 404" in str(e) or "HTTP 403" in str(e):  # S3 says 403 for a missing key without ListBucket
            return []
        raise
    return parse_archive_csv(gzip.decompress(body).decode("utf-8", "replace"), parameter)


def status_for_stations(stations: list[dict[str, Any]], now: datetime | None = None) -> dict[str, Any]:
    now = now or now_utc()
    active = [s for s in stations if _recent(s, now)]
    last = max((s["last_utc"] for s in active if s.get("last_utc")), default=None)
    latest = datetime.fromisoformat(last.replace("Z", "+00:00")) if last else None
    return source_status("OpenAQ PM2.5 stations", ok=bool(stations), count=len(active), latest_obs=latest,
                         note=f"{len(active)} of {len(stations)} stations reported in the last 3 days")


if __name__ == "__main__":  # rebuild backend/data/aq_stations.json
    logging.basicConfig(level=logging.INFO)
    st = fetch_stations(use_cache=False)
    write_stations(st)
    print(f"wrote {len(st)} stations ({sum(s['is_monitor'] for s in st)} reference monitors) to {STATIONS_FILE}")
