"""LSA SAF Meteosat IODC FRP-PIXEL (15-min) ListProduct HDF5: live afternoon fires with FRP.

Listing (public): https://datalsasaf.lsasvcs.ipma.pt/PRODUCTS/MSG-IODC/FRP-PIXEL/HDF5/YYYY/MM/DD/
Files: HDF5_LSASAF_MSG-IODC_FRP-PIXEL-ListProduct_IODC-Disk_YYYYMMDDHHMM (download needs HTTP Basic auth).

ListProduct layout (inspected 8 Oct 2026, algorithm v2.4.0, MSG2 at 45.5E): one 1-D dataset per field,
length = number of detections on the disk. Physical value = raw / SCALING_FACTOR attribute:
LATITUDE, LONGITUDE (int16, /100 deg; missing 19000), FRP (int32, /10 MW), FIRE_CONFIDENCE (int16, /100, 0..1),
PIXEL_SIZE (int16, /100 km), ACQTIME (int16, scan-line time HHMM UTC). Lat/lon are only 0.01 deg precise.
Over Punjab the SEVIRI pixel is ~4-5 km (view zenith ~50 deg), so one detection can cover several fields.
We fetch at most one slot per hour (the HH:00 file, or the first one in that hour) to stay light.
"""
from __future__ import annotations

import io
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np

from dhuaan.config import settings
from dhuaan.ingest.common import fetch, in_domain, now_utc, source_status
from dhuaan.model.types import Fire

log = logging.getLogger("dhuaan.ingest.lsasaf")

BASE = "https://datalsasaf.lsasvcs.ipma.pt/PRODUCTS/MSG-IODC/FRP-PIXEL/HDF5"
PREFIX = "HDF5_LSASAF_MSG-IODC_FRP-PIXEL-ListProduct_IODC-Disk_"
_NAME_RE = re.compile(re.escape(PREFIX) + r"(\d{12})")
SENSOR = "MSG_IODC"


def day_url(d: datetime) -> str:
    return f"{BASE}/{d:%Y/%m/%d}/"


def parse_listing(html: str) -> dict[datetime, str]:
    """{slot time: file name} for every ListProduct in a directory listing."""
    out = {}
    for m in _NAME_RE.finditer(html):
        t = datetime.strptime(m.group(1), "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
        out[t] = PREFIX + m.group(1)
    return out


def hourly_pick(slots: dict[datetime, str], start: datetime, end: datetime) -> list[tuple[datetime, str]]:
    """At most one file per hour in [start, end): the earliest slot of each hour."""
    by_hour: dict[datetime, tuple[datetime, str]] = {}
    for t, name in sorted(slots.items()):
        if start <= t < end:
            by_hour.setdefault(t.replace(minute=0), (t, name))
    return [by_hour[h] for h in sorted(by_hour)]


def confidence_class(c: float) -> str:
    return "low" if c < 0.3 else ("high" if c >= 0.8 else "nominal")


def _scaled(f: Any, name: str) -> np.ndarray:
    ds = f[name]
    raw = ds[:].astype(np.float64)
    miss = ds.attrs.get("MISSING_VALUE")
    scale = float(ds.attrs.get("SCALING_FACTOR", 1.0)) or 1.0
    val = raw / scale
    if miss is not None:
        val[raw == float(miss)] = np.nan
    return val


def parse_h5(data: bytes, slot: datetime) -> tuple[list[Fire], float | None]:
    """Detections inside DOMAIN from one ListProduct. Returns (fires, mean pixel size km in domain)."""
    import h5py
    with h5py.File(io.BytesIO(data), "r") as f:
        if "LATITUDE" not in f:
            return [], None
        lat, lon = _scaled(f, "LATITUDE"), _scaled(f, "LONGITUDE")
        frp = _scaled(f, "FRP")
        conf = _scaled(f, "FIRE_CONFIDENCE") if "FIRE_CONFIDENCE" in f else np.full(lat.shape, 0.5)
        psize = _scaled(f, "PIXEL_SIZE") if "PIXEL_SIZE" in f else np.full(lat.shape, np.nan)
        acq = f["ACQTIME"][:].astype(int) if "ACQTIME" in f else np.full(lat.shape, -999)
    fires: list[Fire] = []
    sizes = []
    for k in range(lat.shape[0]):
        la, lo = lat[k], lon[k]
        if np.isnan(la) or np.isnan(lo) or not in_domain(la, lo):
            continue
        t = slot
        a = int(acq[k])
        if 0 <= a <= 2359:
            t = slot.replace(hour=a // 100, minute=a % 100)
            if t < slot - timedelta(hours=12):  # scan crossed midnight
                t += timedelta(days=1)
        fr = None if np.isnan(frp[k]) else round(float(frp[k]), 1)
        c = 0.5 if np.isnan(conf[k]) else float(conf[k])
        fires.append(Fire(id=f"{SENSOR}_{t:%Y%m%d%H%M}_{la:.2f}_{lo:.2f}", lat=round(float(la), 2),
                          lon=round(float(lo), 2), time_utc=t, frp_mw=fr, sensor=SENSOR,
                          confidence=confidence_class(c)))
        if not np.isnan(psize[k]):
            sizes.append(float(psize[k]))
    return fires, (float(np.mean(sizes)) if sizes else None)


def fetch_recent(now: datetime | None = None, hours: int = 24,
                 use_cache: bool | None = None) -> tuple[list[Fire], dict[str, Any]]:
    """Detections for the last `hours` hours, one slot per hour. Raises if credentials are missing."""
    if not (settings.lsasaf_username and settings.lsasaf_password):
        raise RuntimeError("LSASAF_USERNAME/PASSWORD not set")
    now = (now or now_utc()).astimezone(timezone.utc)
    start = now - timedelta(hours=hours)
    slots: dict[datetime, str] = {}
    d = start.replace(hour=0, minute=0, second=0, microsecond=0)
    while d <= now:
        # listings change every 15 min: never serve today's from cache unless explicitly asked
        html = fetch(day_url(d), namespace="lsasaf", timeout=60, use_cache=use_cache).decode("utf-8", "replace")
        slots.update({t: day_url(t) + n for t, n in parse_listing(html).items()})
        d += timedelta(days=1)
    picks = hourly_pick(slots, start, now)
    fires: list[Fire] = []
    sizes: list[float] = []
    failed = 0
    auth = (settings.lsasaf_username, settings.lsasaf_password)
    for t, url in picks:
        try:
            # a published slot file never changes, so always reuse a cached copy
            body = fetch(url, namespace="lsasaf", auth=auth, timeout=90, use_cache=True)
            got, ps = parse_h5(body, t)
            fires.extend(got)
            if ps is not None:
                sizes.append(ps)
        except Exception as e:
            failed += 1
            log.warning("LSA SAF %s failed: %s", url.rsplit("_", 1)[-1], e)
    if picks and failed == len(picks):
        raise RuntimeError(f"all {failed} LSA SAF downloads failed")
    fires = sorted({f.id: f for f in fires}.values(), key=lambda f: (f.time_utc, f.id))
    note = f"{len(picks) - failed}/{len(picks)} hourly slots read (1 of 4 per hour)"
    if sizes:
        note += f"; mean pixel {np.mean(sizes):.1f} km"
    latest = max((t for t, _ in picks), default=None)
    return fires, source_status("LSA SAF MSG-IODC FRP-PIXEL", ok=True, count=len(fires), latest_obs=latest, note=note)
