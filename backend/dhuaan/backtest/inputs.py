"""Backtest inputs: station list, hourly PM2.5 from the OpenAQ archive, archived-forecast met, fires."""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

import numpy as np

from dhuaan.ingest.common import cache_path, iso_z
from dhuaan.model.types import MetField

log = logging.getLogger("dhuaan.backtest")
UTC = timezone.utc

# Pre-registered station set: PPCB stations in Punjab (Patiala, Bathinda, Ludhiana where hourly PM2.5 exists, plus
# the other PPCB reference monitors) and 3 DPCC stations in Delhi. OpenAQ location ids (provider CPCB).
STATIONS = [
    {"id": 5544, "name": "Model Town, Patiala (PPCB)", "region": "Punjab"},
    {"id": 6939, "name": "Hardev Nagar, Bathinda (PPCB)", "region": "Punjab"},
    {"id": 5569, "name": "PAU, Ludhiana (PPCB)", "region": "Punjab"},
    {"id": 5551, "name": "Golden Temple, Amritsar (PPCB)", "region": "Punjab"},
    {"id": 5542, "name": "Civil Line, Jalandhar (PPCB)", "region": "Punjab"},
    {"id": 6940, "name": "Kalal Majra, Khanna (PPCB)", "region": "Punjab"},
    {"id": 5625, "name": "RIMT Univ., Mandi Gobindgarh (PPCB)", "region": "Punjab"},
    {"id": 10831, "name": "Rohini, Delhi (DPCC)", "region": "Delhi"},
    {"id": 235, "name": "Anand Vihar, Delhi (DPCC)", "region": "Delhi"},
    {"id": 50, "name": "Punjabi Bagh, Delhi (DPCC)", "region": "Delhi"},
]
PM_VALID = (0.0, 1000.0)   # open interval (0, 1000]: zeros and >1000 are instrument flags, not air


def hour_axis(start: datetime, end: datetime) -> list[datetime]:
    n = int((end - start).total_seconds() // 3600) + 1
    return [start + timedelta(hours=h) for h in range(n)]


def hourly_pm(records: list[dict], axis: list[datetime]) -> np.ndarray:
    """15-min records [{t, value}] -> hourly mean on `axis`. A 15-min stamp is the END of its averaging period,
    so a record at HH:15..(HH+1):00 belongs to hour HH. Values outside PM_VALID are dropped."""
    idx = {t: i for i, t in enumerate(axis)}
    acc: dict[int, list[float]] = defaultdict(list)
    for r in records:
        v = r["value"]
        if not (PM_VALID[0] < v <= PM_VALID[1]):
            continue
        t = datetime.fromisoformat(r["t"].replace("Z", "+00:00")) - timedelta(seconds=1)
        i = idx.get(t.replace(minute=0, second=0, microsecond=0))
        if i is not None:
            acc[i].append(v)
    out = np.full(len(axis), np.nan)
    for i, vs in acc.items():
        out[i] = float(np.mean(vs))
    return out


def station_meta(ids: list[int]) -> dict[int, dict]:
    from dhuaan.ingest.openaq import load_stations
    return {s["id"]: s for s in load_stations() if s["id"] in ids}


def load_pm(station_id: int, axis: list[datetime], use_cache: bool | None = True) -> np.ndarray:
    from dhuaan.ingest import openaq
    d0 = (axis[0] + timedelta(hours=5, minutes=30)).date() - timedelta(days=1)
    d1 = (axis[-1] + timedelta(hours=5, minutes=30)).date() + timedelta(days=1)
    recs: list[dict] = []
    d = d0
    while d <= d1:
        recs.extend(openaq.fetch_archive(station_id, d, use_cache=use_cache))
        d += timedelta(days=1)
    return hourly_pm(recs, axis)


def _concat(parts: list[MetField]) -> MetField:
    keys = ("u10", "v10", "u925", "v925", "u850", "v850", "blh")
    times = [t for p in parts for t in p.times]
    return MetField(lons=parts[0].lons, lats=parts[0].lats, times=times,
                    **{k: np.concatenate([getattr(p, k) for p in parts], axis=0) for k in keys})


def load_met(start: date, end: date, chunk_days: int = 14, use_cache: bool | None = True) -> tuple[MetField, list[dict]]:
    """Open-Meteo historical-forecast API in <= 14-day chunks (one chunk ~540 call-weight, under the 600/min cap);
    waits 65 s between chunks that are not cached."""
    from dhuaan.ingest import openmeteo
    parts, sts, d, fetched = [], [], start, False
    while d <= end:
        e = min(end, d + timedelta(days=chunk_days - 1))
        for attempt in range(3):
            try:
                if fetched:
                    time.sleep(65)
                t0 = time.perf_counter()
                m, s = openmeteo.fetch_historical(d, e, use_cache=use_cache)
                fetched = time.perf_counter() - t0 > 1.0
                break
            except RuntimeError as ex:
                if attempt == 2 or "429" not in str(ex):
                    raise
                log.warning("Open-Meteo rate limit, waiting: %s", ex)
                fetched = True
        parts.append(m)
        sts.append(s)
        d = e + timedelta(days=1)
    return _concat(parts), sts


def slice_met(met: MetField, t_start: datetime, t_end: datetime) -> MetField:
    i0 = max(0, next((i for i, t in enumerate(met.times) if t >= t_start), 0))
    i1 = max(i0 + 1, next((i for i, t in enumerate(met.times) if t > t_end), len(met.times)))
    keys = ("u10", "v10", "u925", "v925", "u850", "v850", "blh")
    return MetField(lons=met.lons, lats=met.lats, times=met.times[i0:i1], **{k: getattr(met, k)[i0:i1] for k in keys})


__all__ = ["STATIONS", "hour_axis", "hourly_pm", "load_pm", "load_met", "slice_met", "station_meta", "iso_z", "cache_path"]
