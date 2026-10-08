"""Shared helpers for model tests."""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from dhuaan.config import DOMAIN
from dhuaan.model.advect import integrate
from dhuaan.model.emission import Particles
from dhuaan.model.met import MetInterp
from dhuaan.model.params import Member, Params

T0 = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
BOUNDS = (DOMAIN["lon_min"], DOMAIN["lon_max"], DOMAIN["lat_min"], DOMAIN["lat_max"])


def particles(lon, lat, t_rel=0.0, w0=1.0, cluster=0) -> Particles:
    lon = np.atleast_1d(np.asarray(lon, dtype=np.float64))
    n = lon.size
    lat = np.broadcast_to(np.asarray(lat, dtype=np.float64), (n,)).copy()
    return Particles(lon, lat, np.broadcast_to(np.asarray(t_rel, float), (n,)).copy(),
                     np.broadcast_to(np.asarray(w0, float), (n,)).copy(),
                     np.broadcast_to(np.asarray(cluster, np.int64), (n,)).copy(), np.zeros(n, dtype=bool))


def run_to(parts: Particles, met, t_end_s: float, params: Params | None = None,
           members: tuple[Member, ...] = (Member(),), seed: int = 0, t_start_s: float = 0.0):
    """Integrate and return the final Snapshot copied, plus the list of total masses per step."""
    p = params or Params()
    mi = MetInterp(met, T0, p)
    masses = []
    last = None
    for snap in integrate(parts, mi, members, p, t_start_s, t_end_s, BOUNDS, seed):
        masses.append(float(snap.w.sum()))
        last = (snap.lon.copy(), snap.lat.copy(), snap.w.copy())
    return last, masses
