"""Small HTTP helper shared by the ingest clients: retries, a User-Agent, and an on-disk cache.

Every response body is written to settings.cache_dir/<namespace>/<hash>. When `use_cache` is on
(CLI flag --use-cache, or env DHUAAN_USE_CACHE=1), a cached body is returned instead of re-fetching,
which keeps development runs light on the free-tier APIs. Secrets never go into log lines: URLs are
logged through `redact()`.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from dhuaan.config import DOMAIN, settings

log = logging.getLogger("dhuaan.ingest")
USER_AGENT = "dhuaan/0.1 (hackathon smoke forecast; github.com/satanrayshe)"
_USE_CACHE = os.environ.get("DHUAAN_USE_CACHE", "") in ("1", "true", "yes")


def set_use_cache(on: bool) -> None:
    global _USE_CACHE
    _USE_CACHE = on


def use_cache_enabled() -> bool:
    return _USE_CACHE


_SECRET_RE = re.compile(r"(/api/(?:area|data_availability|country)/csv/)[^/]+")


def redact(url: str) -> str:
    url = _SECRET_RE.sub(r"\1***", url)
    key = settings.firms_map_key
    return url.replace(key, "***") if key else url


def cache_path(namespace: str, key: str, suffix: str = "") -> Path:
    h = hashlib.sha1(key.encode("utf-8")).hexdigest()[:20]
    p = Path(settings.cache_dir) / namespace / f"{h}{suffix}"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def fetch(
    url: str,
    *,
    namespace: str,
    method: str = "GET",
    params: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    auth: tuple[str, str] | None = None,
    timeout: float = 60,
    retries: int = 3,
    use_cache: bool | None = None,
    cache_key: str | None = None,
    ok_status: tuple[int, ...] = (200,),
) -> bytes:
    """Fetch a URL and return the body. Raises RuntimeError after `retries` failed attempts."""
    use_cache = _USE_CACHE if use_cache is None else use_cache
    key = cache_key or json.dumps([method, url, params, data], sort_keys=True, default=str)
    cp = cache_path(namespace, key)
    if use_cache and cp.exists():
        return cp.read_bytes()
    hdrs = {"User-Agent": USER_AGENT, **(headers or {})}
    last: str = ""
    for attempt in range(retries):
        try:
            r = requests.request(method, url, params=params, data=data, headers=hdrs, auth=auth, timeout=timeout)
            if r.status_code in ok_status:
                cp.write_bytes(r.content)
                return r.content
            last = f"HTTP {r.status_code}: {r.text[:200]}"
            if r.status_code in (400, 401, 403, 404):
                break  # not retryable
            if r.status_code == 429:
                time.sleep(min(30, 5 * (attempt + 1)))
                continue
        except requests.RequestException as e:
            last = f"{type(e).__name__}: {e}"
        time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"{redact(url)} failed: {redact(last)}")


def grid_axis(lo: float, hi: float, step: float) -> list[float]:
    """Inclusive axis lo..hi at `step` (rounded to 4 dp), e.g. 72.5..79.0 at 0.25 -> 27 values."""
    n = int(round((hi - lo) / step)) + 1
    vals = [round(lo + i * step, 4) for i in range(n)]
    return [v for v in vals if v <= hi + 1e-9]


def iso_z(dt: datetime | None) -> str | None:
    """UTC ISO-8601 with a Z suffix, seconds precision."""
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def source_status(name: str, *, ok: bool, count: int = 0, latest_obs: datetime | None = None,
                  note: str = "", fetched: datetime | None = None) -> dict[str, Any]:
    """One entry of meta.sources (CONTRACTS item 7)."""
    return {"name": name, "fetched_utc": iso_z(fetched or now_utc()), "latest_obs_utc": iso_z(latest_obs),
            "count": int(count), "ok": bool(ok), "note": note}


def in_domain(lat: float, lon: float) -> bool:
    return DOMAIN["lat_min"] <= lat <= DOMAIN["lat_max"] and DOMAIN["lon_min"] <= lon <= DOMAIN["lon_max"]
