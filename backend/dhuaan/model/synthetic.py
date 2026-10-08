"""Synthetic inputs for tests, benchmarks and offline development (no network, no data files)."""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np

from dhuaan.config import DOMAIN

from .common import IST, UTC, output_grid
from .types import Fire, MetField, Receptor


def make_met(t0: datetime, *, hours_before: int = 48, hours_after: int = 73, u: float = 2.0, v: float = -1.0,
             blh: float | None = None, dlon: float = 0.25, dlat: float = 0.25, veer: bool = False) -> MetField:
    """Uniform-in-space met on the 0.25 deg domain grid. With blh=None a diurnal BLH cycle is
    used (about 1400 m mid-afternoon IST, 150 m at night). veer=True slowly rotates the wind."""
    lons = np.arange(DOMAIN["lon_min"], DOMAIN["lon_max"] + 1e-9, dlon)
    lats = np.arange(DOMAIN["lat_min"], DOMAIN["lat_max"] + 1e-9, dlat)
    times = [t0 + timedelta(hours=h) for h in range(-hours_before, hours_after + 1)]
    nt, ny, nx = len(times), lats.size, lons.size
    shape = (nt, ny, nx)
    ang = np.zeros(nt)
    if veer:
        ang = np.deg2rad(40.0) * np.sin(2 * np.pi * np.arange(nt) / 36.0)
    uu = (u * np.cos(ang) - v * np.sin(ang))[:, None, None] * np.ones(shape)
    vv = (u * np.sin(ang) + v * np.cos(ang))[:, None, None] * np.ones(shape)
    if blh is None:
        hr = np.array([t.astimezone(IST).hour + t.astimezone(IST).minute / 60 for t in times])
        day = np.clip(np.sin(np.pi * (hr - 8.0) / 10.0), 0.0, None)    # 08:00-18:00 IST
        b = 150.0 + 1250.0 * day
        bl = b[:, None, None] * np.ones(shape)
    else:
        bl = np.full(shape, float(blh))
    return MetField(lons, lats, times, uu, vv, uu * 1.4, vv * 1.4, uu * 1.8, vv * 1.8, bl)


def make_fires(t0: datetime, n_clusters: int = 50, per_cluster: int = 3, seed: int = 0,
               box: tuple[float, float, float, float] = (73.8, 77.2, 29.3, 31.8),
               days: int = 2, geo_fraction: float = 0.0) -> list[Fire]:
    """Clusters of VIIRS-like detections near 13:30 IST on the last `days` days before t0."""
    rng = np.random.default_rng(seed)
    fires: list[Fire] = []
    base_day = t0.astimezone(IST).replace(hour=13, minute=30, second=0, microsecond=0)
    if base_day >= t0:
        base_day -= timedelta(days=1)
    for k in range(n_clusters):
        lon = rng.uniform(box[0], box[1])
        lat = rng.uniform(box[2], box[3])
        when = (base_day - timedelta(days=int(rng.integers(0, days)))).astimezone(UTC)
        for j in range(per_cluster):
            geo = rng.random() < geo_fraction
            sensor = "GK2A" if geo else ("VIIRS_SNPP", "VIIRS_NOAA20", "VIIRS_NOAA21")[j % 3]
            t = when + timedelta(minutes=float(rng.uniform(-20, 20)) + (150.0 if geo else 0.0))
            fires.append(Fire(
                id=f"F{k:04d}_{j}", lat=float(lat + rng.normal(0, 0.003)), lon=float(lon + rng.normal(0, 0.003)),
                time_utc=t, frp_mw=None if geo else float(rng.lognormal(2.0, 0.8)), sensor=sensor,
                confidence="nominal"))
    return fires


def make_receptors(n: int = 300, seed: int = 0, n_schools: int = 20) -> list[Receptor]:
    rng = np.random.default_rng(seed + 100)
    out: list[Receptor] = []
    kinds = ("village", "town", "city")
    for i in range(n):
        kind = "school" if i < n_schools else kinds[int(rng.integers(0, 3))]
        pop = None if kind == "school" else int(rng.lognormal(8.0, 1.2))
        out.append(Receptor(
            id=f"R{i:05d}", name=f"Place {i}", kind=kind, district=f"D{i % 7}", state="Punjab",
            lat=float(rng.uniform(DOMAIN["lat_min"] + 0.05, DOMAIN["lat_max"] - 0.05)),
            lon=float(rng.uniform(DOMAIN["lon_min"] + 0.05, DOMAIN["lon_max"] - 0.05)), population=pop))
    return out


def make_population(seed: int = 0) -> np.ndarray:
    out = output_grid()
    rng = np.random.default_rng(seed + 200)
    return rng.lognormal(9.0, 1.0, size=(out.ny, out.nx))


def district_grid(lat: float, lon: float) -> tuple[str, str]:
    """Toy district lookup: 1 x 1 degree boxes."""
    return (f"D{int(lon)}_{int(lat)}", "Punjab" if lon < 76.5 else "Haryana")
