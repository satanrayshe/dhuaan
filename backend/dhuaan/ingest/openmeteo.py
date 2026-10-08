"""Open-Meteo winds (10 m, 925 hPa, 850 hPa) and boundary-layer height on the 0.25 deg met grid.

Live: api.open-meteo.com/v1/forecast with past_days=1. forecast_days is 4, not 3: with past_days=1 the
series starts at yesterday 00Z, and 1+3 days ends at day+2 23Z, which is short of t0+72 h for any t0
after 00Z. Cost stays at one call per location (7 variables < 10, 5 days < 14).
Backtest: historical-forecast-api.open-meteo.com (archived forecasts; the ERA5 archive has no pressure levels).

u/v names (wind_u_component_*) are undocumented; if they are rejected we fall back to speed/direction.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

import numpy as np

from dhuaan.config import DOMAIN
from dhuaan.ingest.common import fetch, grid_axis, iso_z, source_status
from dhuaan.model.types import MetField

log = logging.getLogger("dhuaan.ingest.openmeteo")

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
HISTORICAL_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"
STEP = 0.25
MAX_LOCATIONS = 1000
LEVELS = ("10m", "925hPa", "850hPa")
UV_VARS = [f"wind_{c}_component_{lv}" for lv in LEVELS for c in ("u", "v")] + ["boundary_layer_height"]
SD_VARS = [f"wind_{c}_{lv}" for lv in LEVELS for c in ("speed", "direction")] + ["boundary_layer_height"]
FIELD_OF = {"10m": ("u10", "v10"), "925hPa": ("u925", "v925"), "850hPa": ("u850", "v850")}
BLH_DEFAULT = 500.0


def grid() -> tuple[np.ndarray, np.ndarray]:
    """(lons (27,), lats (20,)) ascending."""
    lons = np.array(grid_axis(DOMAIN["lon_min"], DOMAIN["lon_max"], STEP))
    lats = np.array(grid_axis(DOMAIN["lat_min"], DOMAIN["lat_max"], STEP))
    return lons, lats


def call_weight(n_locations: int, n_vars: int, n_days: int) -> float:
    """Open-Meteo free-tier accounting: each location is >=1 call, x(vars/10) above 10 vars, x(days/14) above 14 days."""
    return n_locations * max(1.0, n_vars / 10) * max(1.0, n_days / 14)


def _points(lons: np.ndarray, lats: np.ndarray) -> list[tuple[float, float]]:
    """Row-major (lat outer, lon inner) so point k -> (k // nx, k % nx)."""
    return [(float(la), float(lo)) for la in lats for lo in lons]


def _request(url: str, pts: list[tuple[float, float]], variables: list[str], extra: dict[str, Any],
             use_cache: bool | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i in range(0, len(pts), MAX_LOCATIONS):
        chunk = pts[i:i + MAX_LOCATIONS]
        data = {
            "latitude": ",".join(f"{p[0]:.2f}" for p in chunk),
            "longitude": ",".join(f"{p[1]:.2f}" for p in chunk),
            "hourly": ",".join(variables), "wind_speed_unit": "ms", "timezone": "GMT", **extra,
        }
        body = fetch(url, namespace="openmeteo", method="POST", data=data, timeout=120, use_cache=use_cache)
        j = json.loads(body)
        out.extend(j if isinstance(j, list) else [j])
    return out


def _parse_time(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def _fill(a: np.ndarray, default: float) -> np.ndarray:
    """Fill NaNs: along time (nearest valid hour), then with the field mean, then `default`."""
    a = a.copy()
    nt = a.shape[0]
    if np.isnan(a).any():
        flat = a.reshape(nt, -1)
        for k in range(flat.shape[1]):
            col = flat[:, k]
            bad = np.isnan(col)
            if bad.all() or not bad.any():
                continue
            idx = np.arange(nt)
            col[bad] = np.interp(idx[bad], idx[~bad], col[~bad])
        a = flat.reshape(a.shape)
    if np.isnan(a).any():
        m = np.nanmean(a) if not np.isnan(a).all() else default
        a[np.isnan(a)] = m
    return a


def assemble(responses: list[dict[str, Any]], lons: np.ndarray, lats: np.ndarray,
             times: list[datetime], speed_direction: bool = False) -> MetField:
    """Turn per-location JSON responses (row-major order) into a MetField on `times` (hourly UTC)."""
    ny, nx, nt = len(lats), len(lons), len(times)
    if len(responses) != ny * nx:
        raise RuntimeError(f"Open-Meteo returned {len(responses)} locations, expected {ny * nx}")
    want = {iso_z(t): i for i, t in enumerate(times)}
    fields = {k: np.full((nt, ny, nx), np.nan, dtype=np.float32)
              for k in ("u10", "v10", "u925", "v925", "u850", "v850", "blh")}
    for k, resp in enumerate(responses):
        j, i = divmod(k, nx)
        h = resp["hourly"]
        tidx = [want.get(iso_z(_parse_time(s)), -1) for s in h["time"]]
        sel = np.array([t >= 0 for t in tidx])
        dst = np.array([t for t in tidx if t >= 0], dtype=int)
        if not len(dst):
            continue

        def col(name: str) -> np.ndarray:
            v = np.array([np.nan if x is None else x for x in h[name]], dtype=np.float64)
            return v[sel]

        for lv in LEVELS:
            fu, fv = FIELD_OF[lv]
            if speed_direction:
                spd, dirn = col(f"wind_speed_{lv}"), np.deg2rad(col(f"wind_direction_{lv}"))
                u, v = -spd * np.sin(dirn), -spd * np.cos(dirn)  # direction the wind blows FROM
            else:
                u, v = col(f"wind_u_component_{lv}"), col(f"wind_v_component_{lv}")
            fields[fu][dst, j, i] = u
            fields[fv][dst, j, i] = v
        fields["blh"][dst, j, i] = col("boundary_layer_height")
    for k in fields:
        fields[k] = _fill(fields[k], BLH_DEFAULT if k == "blh" else 0.0)
    fields["blh"] = np.maximum(fields["blh"], 10.0)
    return MetField(lons=lons.astype(np.float64), lats=lats.astype(np.float64), times=list(times), **fields)


def run_times(t0: datetime) -> list[datetime]:
    """97 hourly steps t0-24h .. t0+72h."""
    return [t0 + timedelta(hours=h) for h in range(-24, 73)]


def _fetch_grid(url: str, extra: dict[str, Any], times: list[datetime], use_cache: bool | None,
                n_days: int) -> tuple[MetField, str]:
    lons, lats = grid()
    pts = _points(lons, lats)
    try:
        resp = _request(url, pts, UV_VARS, extra, use_cache)
        sd = False
    except RuntimeError as e:
        if "HTTP 400" not in str(e):
            raise
        log.warning("u/v variable names rejected (%s); falling back to speed/direction", e)
        resp = _request(url, pts, SD_VARS, extra, use_cache)
        sd = True
    w = call_weight(len(pts), len(UV_VARS), n_days)
    log.info("Open-Meteo %s: %d locations, weight ~%.0f calls", url.split("//")[1].split("/")[0], len(pts), w)
    note = f"{len(lons)}x{len(lats)} @0.25deg, ~{w:.0f} API-call weight" + ("; speed/direction fallback" if sd else "")
    return assemble(resp, lons, lats, times, speed_direction=sd), note


def fetch_forecast(t0: datetime, use_cache: bool | None = None) -> tuple[MetField, dict[str, Any]]:
    """MetField covering t0-24h .. t0+72h (97 h). Raises on failure (the caller records it)."""
    t0 = t0.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    times = run_times(t0)
    today = datetime.now(timezone.utc).date()
    past = max(1, (today - times[0].date()).days)
    fdays = max(4, (times[-1].date() - today).days + 1)
    met, note = _fetch_grid(FORECAST_URL, {"past_days": past, "forecast_days": fdays}, times, use_cache, past + fdays)
    return met, source_status("Open-Meteo forecast", ok=True, count=len(met.lons) * len(met.lats),
                              latest_obs=times[-1], note=note)


def fetch_historical(start: date, end: date, use_cache: bool | None = True) -> tuple[MetField, dict[str, Any]]:
    """Archived forecasts, hourly from start 00Z to end 23Z inclusive."""
    t_start = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
    n = ((end - start).days + 1) * 24
    times = [t_start + timedelta(hours=h) for h in range(n)]
    met, note = _fetch_grid(HISTORICAL_URL, {"start_date": start.isoformat(), "end_date": end.isoformat()},
                            times, use_cache, (end - start).days + 1)
    return met, source_status("Open-Meteo historical-forecast", ok=True, count=len(met.lons) * len(met.lats),
                              latest_obs=times[-1], note=note)
