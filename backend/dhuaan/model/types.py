"""In-memory types shared by every component (see docs/CONTRACTS.md)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np

POLAR_SENSORS = frozenset({"VIIRS_SNPP", "VIIRS_NOAA20", "VIIRS_NOAA21", "MODIS"})
GEO_SENSORS = frozenset({"MSG_IODC", "GK2A"})


@dataclass(frozen=True)
class Fire:
    """One satellite fire detection."""
    id: str
    lat: float
    lon: float
    time_utc: datetime            # tz-aware UTC
    frp_mw: float | None          # None for sources without FRP (e.g. GK2A)
    sensor: str                   # "VIIRS_SNPP"|"VIIRS_NOAA20"|"VIIRS_NOAA21"|"MODIS"|"MSG_IODC"|"GK2A"
    confidence: str               # "low"|"nominal"|"high"


@dataclass
class MetField:
    """Hourly met on a regular lon/lat grid. Wind arrays are m/s, shape (nt, ny, nx)."""
    lons: np.ndarray              # (nx,) ascending
    lats: np.ndarray              # (ny,) ascending
    times: list[datetime]         # (nt,) hourly UTC
    u10: np.ndarray
    v10: np.ndarray
    u925: np.ndarray
    v925: np.ndarray
    u850: np.ndarray
    v850: np.ndarray
    blh: np.ndarray               # boundary-layer height m, (nt, ny, nx)


@dataclass(frozen=True)
class Receptor:
    id: str
    name: str
    kind: str                     # "village"|"town"|"city"|"school"|"ward"
    district: str
    state: str
    lat: float
    lon: float
    population: int | None
