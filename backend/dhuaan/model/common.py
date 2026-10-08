"""Constants, grid definitions and time helpers used across the model."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np

from dhuaan.config import DOMAIN

UTC = timezone.utc
IST = timezone(timedelta(hours=5, minutes=30))
M_PER_DEG_LAT = 110_574.0
M_PER_DEG_LON_EQ = 111_320.0

HOURS_BEFORE = 24          # run covers t0-24h .. t0+72h
HOURS_AFTER = 72
N_HOURS = HOURS_BEFORE + HOURS_AFTER + 1   # 97

OUT_D = 0.1                # output grid spacing (deg)
OUT_NX, OUT_NY = 66, 48    # fixed by the contract (spans lon 72.5-79.1, lat 28.0-32.8)
FINE_PER_OUT = 4           # fine concentration nodes per output cell (0.025 deg)


def iso(t: datetime) -> str:
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def floor_hour(t: datetime) -> datetime:
    if t.tzinfo is None:
        t = t.replace(tzinfo=UTC)
    return t.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


def m_per_deg_lon(lat) -> np.ndarray:
    return M_PER_DEG_LON_EQ * np.cos(np.deg2rad(lat))


_LAT_REF = 30.0
_C0, _S0 = float(np.cos(np.deg2rad(_LAT_REF))), float(np.sin(np.deg2rad(_LAT_REF)))


def inv_m_per_deg_lon_fast(lat: np.ndarray) -> np.ndarray:
    """1 / m_per_deg_lon(lat) via a 4th-order Taylor expansion of cos about 30 N (relative error
    < 3e-6 for 25-35 N, ~10x faster than np.cos). Used in the advection inner loop."""
    d = (lat - _LAT_REF) * (np.pi / 180.0)
    d2 = d * d
    c = _C0 * (1.0 - d2 * (0.5 - d2 / 24.0)) - _S0 * d * (1.0 - d2 / 6.0)
    return 1.0 / (M_PER_DEG_LON_EQ * c)


@dataclass(frozen=True)
class Grid:
    """Regular lon/lat node grid. Nodes at lon0 + i*dlon, lat0 + j*dlat; row 0 = south."""
    lon0: float
    lat0: float
    dlon: float
    dlat: float
    nx: int
    ny: int

    @property
    def lons(self) -> np.ndarray:
        return self.lon0 + self.dlon * np.arange(self.nx)

    @property
    def lats(self) -> np.ndarray:
        return self.lat0 + self.dlat * np.arange(self.ny)

    def cell_area_m2(self) -> np.ndarray:
        """(ny,) area represented by one node in each row."""
        return (self.dlat * M_PER_DEG_LAT) * (self.dlon * m_per_deg_lon(self.lats))


def output_grid() -> Grid:
    """0.1 deg output grid; the nodes are the cell centres (66 x 48)."""
    return Grid(DOMAIN["lon_min"] + OUT_D / 2, DOMAIN["lat_min"] + OUT_D / 2, OUT_D, OUT_D, OUT_NX, OUT_NY)


def fine_grid() -> Grid:
    """0.025 deg node grid spanning the domain edges; output cell centre (i, j) is fine node
    (2 + 4i, 2 + 4j)."""
    d = OUT_D / FINE_PER_OUT
    return Grid(DOMAIN["lon_min"], DOMAIN["lat_min"], d, d, OUT_NX * FINE_PER_OUT + 1, OUT_NY * FINE_PER_OUT + 1)


def bilinear_setup(grid: Grid, lon: np.ndarray, lat: np.ndarray):
    """Corner indices/weights for bilinear interpolation (or CIC deposit) on node grid.

    Returns (flat_idx (4, n), weights (4, n), inside (n,)). Points outside the grid get
    clamped indices and inside=False."""
    fx = (np.asarray(lon, dtype=np.float64) - grid.lon0) / grid.dlon
    fy = (np.asarray(lat, dtype=np.float64) - grid.lat0) / grid.dlat
    inside = (fx >= 0) & (fx <= grid.nx - 1) & (fy >= 0) & (fy <= grid.ny - 1)
    fx = np.clip(fx, 0, grid.nx - 1 - 1e-9)
    fy = np.clip(fy, 0, grid.ny - 1 - 1e-9)
    ix = fx.astype(np.int64)
    iy = fy.astype(np.int64)
    ax = fx - ix
    ay = fy - iy
    i00 = iy * grid.nx + ix
    idx = np.stack([i00, i00 + 1, i00 + grid.nx, i00 + grid.nx + 1])
    w = np.stack([(1 - ax) * (1 - ay), ax * (1 - ay), (1 - ax) * ay, ax * ay])
    return idx, w, inside
