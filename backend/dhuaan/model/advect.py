"""Lagrangian transport: RK2 (midpoint) advection by the mixed-layer wind, random-walk
turbulence with sigma = sqrt(2 K_h dt), exponential removal, ensemble perturbations.

All ensemble members are integrated together in (M, P) arrays. Members share the same
random numbers (common random numbers), so with zero perturbation they are identical and
the ensemble spread reflects only the met perturbations.
"""
from __future__ import annotations

import math
from collections.abc import Iterator
import numpy as np

from .common import M_PER_DEG_LAT, inv_m_per_deg_lon_fast
from .emission import Particles
from .met import MetInterp
from .params import Member, Params


def k_h(blh: np.ndarray, p: Params) -> np.ndarray:
    """Horizontal eddy diffusivity (m2/s): kh_night at BLH<=blh_lo -> kh_day at BLH>=blh_hi."""
    a = np.clip((blh - p.blh_lo) / (p.blh_hi - p.blh_lo), 0.0, 1.0)
    return p.kh_night + a * (p.kh_day - p.kh_night)


class Snapshot:
    """State at one time step. Arrays are live views: copy anything you keep."""

    __slots__ = ("t_s", "lon", "lat", "alive", "_parts", "_inv_tau", "_w")

    def __init__(self, t_s, lon, lat, alive, parts, inv_tau):
        self.t_s, self.lon, self.lat, self.alive = t_s, lon, lat, alive
        self._parts, self._inv_tau, self._w = parts, inv_tau, None

    @property
    def w(self) -> np.ndarray:
        """(M, P) weight in kg; 0 for unreleased or dead particles (w0 * exp(-age / tau))."""
        if self._w is None:
            age = np.maximum(self.t_s - self._parts.t_rel, 0.0)
            self._w = np.where(self.alive, self._parts.w0 * np.exp(-age * self._inv_tau), 0.0)
        return self._w


def integrate(
    parts: Particles,
    met: MetInterp,
    members: tuple[Member, ...],
    p: Params,
    t_start_s: float,
    t_end_s: float,
    bounds: tuple[float, float, float, float],
    seed: int = 0,
) -> Iterator[Snapshot]:
    """Yield a Snapshot at t_start_s, t_start_s + dt, ..., t_end_s (inclusive).

    `bounds` = (lon_min, lon_max, lat_min, lat_max); a particle leaving it is dead."""
    rng = np.random.default_rng(seed + 7919)
    M, P = len(members), parts.n
    dt = p.dt_s
    lon = np.broadcast_to(parts.lon, (M, P)).copy()
    lat = np.broadcast_to(parts.lat, (M, P)).copy()
    released = np.zeros(P, dtype=bool)
    alive = np.zeros((M, P), dtype=bool)
    speed = np.array([m.speed for m in members])
    th = np.deg2rad([m.turn_deg for m in members])
    cos_m, sin_m = speed * np.cos(th), speed * np.sin(th)
    khm = np.array([m.kh for m in members]) * p.kh_scale
    inv_tau = 0.0 if not math.isfinite(p.tau_h) else 1.0 / (p.tau_h * 3600.0)
    lo_x, hi_x, lo_y, hi_y = bounds
    n_steps = int(round((t_end_s - t_start_s) / dt))

    for s in range(n_steps + 1):
        t = t_start_s + s * dt
        new = (~released) & (parts.t_rel <= t)
        if new.any():
            lon[:, new] = parts.lon[new]
            lat[:, new] = parts.lat[new]
            alive[:, new] = True
            released |= new
        yield Snapshot(t, lon, lat, alive, parts, inv_tau)
        if s == n_steps:
            break
        flat = np.flatnonzero(alive)
        if flat.size == 0:
            continue
        mi, pi = np.divmod(flat, P)
        x = lon.reshape(-1)[flat]
        y = lat.reshape(-1)[flat]
        cm, sm = cos_m[mi], sin_m[mi]
        u, v, b1, in1 = met.sample(x, y, t, need_blh=p.kh_scale > 0)
        u, v = cm * u - sm * v, sm * u + cm * v
        inv_mx = inv_m_per_deg_lon_fast(y)              # metres -> degrees lon
        xm = x + (0.5 * dt) * u * inv_mx
        ym = y + (0.5 * dt / M_PER_DEG_LAT) * v
        u2, v2, _, in2 = met.sample(xm, ym, t + 0.5 * dt, need_blh=False)
        u2, v2 = cm * u2 - sm * v2, sm * u2 + cm * v2
        inv_mx = inv_m_per_deg_lon_fast(ym)
        x = x + dt * u2 * inv_mx
        y = y + (dt / M_PER_DEG_LAT) * v2
        if p.kh_scale > 0:
            noise = rng.standard_normal((2, P))          # shared by all members
            sig = np.sqrt((2.0 * dt) * k_h(b1, p) * khm[mi])
            x = x + sig * noise[0, pi] * inv_mx
            y = y + sig * noise[1, pi] * (1.0 / M_PER_DEG_LAT)
        ok = in1 & in2 & (x >= lo_x) & (x <= hi_x) & (y >= lo_y) & (y <= hi_y)
        lon.reshape(-1)[flat] = x
        lat.reshape(-1)[flat] = y
        alive.reshape(-1)[flat] = ok
