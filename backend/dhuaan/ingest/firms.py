"""NASA FIRMS area API: VIIRS (SNPP, NOAA-20, NOAA-21) and MODIS active-fire detections over DOMAIN.

URL: https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{SOURCE}/{W,S,E,N}/{DAYS}[/{YYYY-MM-DD}]
With a date, the API returns DATE .. DATE+DAYS-1 (checked live on 8 Oct 2026). DAYS is 1..5.
acq_time is UTC HHMM (leading zeros dropped, e.g. "820" = 08:20Z).
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

from dhuaan.config import DOMAIN, settings
from dhuaan.ingest.common import fetch, in_domain, source_status
from dhuaan.model.types import Fire

log = logging.getLogger("dhuaan.ingest.firms")

BASE = "https://firms.modaps.eosdis.nasa.gov/api"
NRT_SOURCES = ("VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT", "MODIS_NRT")
BBOX = f"{DOMAIN['lon_min']},{DOMAIN['lat_min']},{DOMAIN['lon_max']},{DOMAIN['lat_max']}"


def sensor_of(source: str) -> str:
    """'VIIRS_NOAA20_NRT' -> 'VIIRS_NOAA20'; 'MODIS_SP' -> 'MODIS'."""
    return source.rsplit("_", 1)[0]


def normalise_confidence(raw: str) -> str:
    """VIIRS gives l/n/h; MODIS gives 0-100 (FIRMS classes: <30 low, 30-79 nominal, >=80 high)."""
    s = (raw or "").strip().lower()
    if s in ("l", "low"):
        return "low"
    if s in ("n", "nominal"):
        return "nominal"
    if s in ("h", "high"):
        return "high"
    try:
        v = float(s)
    except ValueError:
        return "nominal"
    return "low" if v < 30 else ("high" if v >= 80 else "nominal")


def _acq_dt(acq_date: str, acq_time: str) -> datetime:
    t = acq_time.strip().zfill(4)
    return datetime.strptime(f"{acq_date.strip()} {t}", "%Y-%m-%d %H%M").replace(tzinfo=timezone.utc)


def fire_id(sensor: str, t: datetime, lat: float, lon: float) -> str:
    return f"{sensor}_{t:%Y%m%d%H%M}_{lat:.4f}_{lon:.4f}"


def parse_csv(text: str, source: str) -> list[Fire]:
    """Parse one FIRMS area-API CSV body into Fire objects (rows outside DOMAIN are dropped)."""
    sensor = sensor_of(source)
    text = text.lstrip("﻿")
    if not text.strip() or not text.lstrip().lower().startswith("latitude"):
        if text.strip():
            raise RuntimeError(f"FIRMS {source}: unexpected body: {text.strip()[:120]!r}")
        return []
    out: list[Fire] = []
    for row in csv.DictReader(io.StringIO(text)):
        try:
            lat, lon = float(row["latitude"]), float(row["longitude"])
            t = _acq_dt(row["acq_date"], row["acq_time"])
        except (KeyError, ValueError, TypeError):
            continue
        if not in_domain(lat, lon):
            continue
        frp_s = (row.get("frp") or "").strip()
        frp = float(frp_s) if frp_s not in ("", "nan") else None
        out.append(Fire(id=fire_id(sensor, t, lat, lon), lat=lat, lon=lon, time_utc=t, frp_mw=frp,
                        sensor=sensor, confidence=normalise_confidence(row.get("confidence", ""))))
    return out


def dedupe(fires: Iterable[Fire]) -> list[Fire]:
    """Drop exact repeats (same sensor, minute and 4-dp position: overlapping day windows return them twice).

    Detections of one fire by different sensors are kept: they are separate observations and the model
    clusters them. Output is sorted by time then id so runs are deterministic.
    """
    seen: dict[str, Fire] = {}
    for f in fires:
        seen.setdefault(f.id, f)
    return sorted(seen.values(), key=lambda f: (f.time_utc, f.id))


def _area_url(source: str, days: int, day: date | None = None) -> str:
    if not 1 <= days <= 5:
        raise ValueError("FIRMS DAYS must be 1..5")
    url = f"{BASE}/area/csv/{settings.firms_map_key}/{source}/{BBOX}/{days}"
    return f"{url}/{day.isoformat()}" if day else url


def fetch_source(source: str, days: int = 2, day: date | None = None, use_cache: bool | None = None) -> list[Fire]:
    if not settings.firms_map_key:
        raise RuntimeError("FIRMS_MAP_KEY not set")
    body = fetch(_area_url(source, days, day), namespace="firms", timeout=90, use_cache=use_cache)
    return parse_csv(body.decode("utf-8", errors="replace"), source)


def fetch_recent(days: int = 2, sources: Iterable[str] = NRT_SOURCES,
                 use_cache: bool | None = None) -> tuple[list[Fire], list[dict[str, Any]]]:
    """All NRT sources for the last `days` days. Returns (fires, meta.sources entries). Never raises per source."""
    fires: list[Fire] = []
    statuses: list[dict[str, Any]] = []
    for src in sources:
        try:
            got = fetch_source(src, days, use_cache=use_cache)
            fires.extend(got)
            latest = max((f.time_utc for f in got), default=None)
            statuses.append(source_status(f"FIRMS {src}", ok=True, count=len(got), latest_obs=latest,
                                          note=f"area API, last {days} d"))
        except Exception as e:  # one sensor failing must not sink the run
            log.warning("FIRMS %s failed: %s", src, e)
            statuses.append(source_status(f"FIRMS {src}", ok=False, note=str(e)[:200]))
    return dedupe(fires), statuses


# ---------- archive (backtest) ----------

_availability: dict[str, tuple[date, date]] | None = None


def availability(use_cache: bool | None = None) -> dict[str, tuple[date, date]]:
    """{data_id: (min_date, max_date)} from /api/data_availability (cached per process)."""
    global _availability
    if _availability is None:
        body = fetch(f"{BASE}/data_availability/csv/{settings.firms_map_key}/ALL", namespace="firms",
                     use_cache=use_cache).decode()
        out = {}
        for row in csv.DictReader(io.StringIO(body)):
            try:
                out[row["data_id"]] = (date.fromisoformat(row["min_date"]), date.fromisoformat(row["max_date"]))
            except (KeyError, ValueError):
                continue
        _availability = out
    return _availability


def archive_source_for(sensor_prefix: str, start: date, end: date, avail: dict[str, tuple[date, date]]) -> str | None:
    """Prefer the science-quality (SP) product when it covers [start, end], else NRT, else None."""
    for suffix in ("SP", "NRT"):
        name = f"{sensor_prefix}_{suffix}"
        if name in avail and avail[name][0] <= start and end <= avail[name][1]:
            return name
    return None


def fetch_archive(start: date, end: date, sensors: Iterable[str] = ("VIIRS_SNPP", "VIIRS_NOAA20", "VIIRS_NOAA21", "MODIS"),
                  use_cache: bool | None = True) -> tuple[list[Fire], list[dict[str, Any]]]:
    """Detections for start..end inclusive (5-day chunks). Archive calls are cached by default."""
    avail = availability(use_cache=use_cache)
    fires: list[Fire] = []
    statuses = []
    for sp in sensors:
        src = archive_source_for(sp, start, end, avail)
        if src is None:
            statuses.append(source_status(f"FIRMS {sp}", ok=False, note=f"no product covers {start}..{end}"))
            continue
        n0 = len(fires)
        try:
            d = start
            while d <= end:
                days = min(5, (end - d).days + 1)
                fires.extend(fetch_source(src, days, d, use_cache=use_cache))
                d += timedelta(days=days)
            statuses.append(source_status(f"FIRMS {src}", ok=True, count=len(fires) - n0, note=f"archive {start}..{end}"))
        except Exception as e:
            statuses.append(source_status(f"FIRMS {src}", ok=False, note=str(e)[:200]))
    return dedupe(fires), statuses
