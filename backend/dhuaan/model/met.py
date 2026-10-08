"""Mixed-layer mean wind and BLH, interpolated bilinearly in space and linearly in time.

Level heights: 10 m, 925 hPa ~ 750 m, 850 hPa ~ 1500 m. The mixed-layer wind at a met grid
point is the mean of the levels at or below the BLH (10 m is always included). It is computed
on the met grid at each met hour, then interpolated to particles. Outside the met grid in
space a particle is dead; outside the met time range the nearest met hour is used
(persistence), so the pipeline should supply met covering t0-48h .. t0+72h.
"""
from __future__ import annotations

from datetime import datetime

import numpy as np

from .common import Grid, bilinear_setup
from .params import Params
from .types import MetField


def met_grid(met: MetField) -> Grid:
    lons = np.asarray(met.lons, dtype=np.float64)
    lats = np.asarray(met.lats, dtype=np.float64)
    if lons.size < 2 or lats.size < 2:
        raise ValueError("met grid needs at least 2 points per axis")
    dlon = np.diff(lons)
    dlat = np.diff(lats)
    if not (np.allclose(dlon, dlon[0], rtol=1e-4) and np.allclose(dlat, dlat[0], rtol=1e-4)) or dlon[0] <= 0 or dlat[0] <= 0:
        raise ValueError("met grid must be regular and ascending")
    return Grid(float(lons[0]), float(lats[0]), float(dlon[0]), float(dlat[0]), lons.size, lats.size)


def mixed_layer_wind(met: MetField, p: Params) -> tuple[np.ndarray, np.ndarray]:
    blh = np.asarray(met.blh, dtype=np.float64)
    w925 = (blh >= p.z925_m).astype(np.float64)
    w850 = (blh >= p.z850_m).astype(np.float64)
    n = 1.0 + w925 + w850
    u = (np.asarray(met.u10) + w925 * np.asarray(met.u925) + w850 * np.asarray(met.u850)) / n
    v = (np.asarray(met.v10) + w925 * np.asarray(met.v925) + w850 * np.asarray(met.v850)) / n
    return u, v


class MetInterp:
    """Samples (u_ml, v_ml, blh) at particle positions and times (seconds since t0)."""

    def __init__(self, met: MetField, t0: datetime, params: Params | None = None):
        p = params or Params()
        self.grid = met_grid(met)
        self.t = np.array([(t - t0).total_seconds() for t in met.times], dtype=np.float64)
        if self.t.size == 0 or np.any(np.diff(self.t) <= 0):
            raise ValueError("met times must be non-empty and strictly increasing")
        u, v = mixed_layer_wind(met, p)
        nt = self.t.size
        if (np.shape(met.blh) != (nt, self.grid.ny, self.grid.nx)) or u.shape != np.shape(met.blh):
            raise ValueError(f"met arrays must have shape (nt, ny, nx) = {(nt, self.grid.ny, self.grid.nx)}")
        # Missing values: calm wind, and a neutral 500 m mixed layer.
        u, v = np.nan_to_num(u, nan=0.0), np.nan_to_num(v, nan=0.0)
        blh = np.maximum(np.nan_to_num(np.asarray(met.blh, dtype=np.float64), nan=500.0), 1.0)
        self.fields = np.stack([u, v, blh], axis=-1).reshape(nt, -1, 3)   # (nt, ny*nx, 3)
        self._cache_t: float | None = None
        self._cache_f: np.ndarray | None = None
        self._coef_t: float | None = None
        self._coef: np.ndarray | None = None
        self._grid_cache: dict[Grid, tuple[np.ndarray, np.ndarray]] = {}

    def fields_at(self, t_s: float) -> np.ndarray:
        if self._cache_t == t_s:
            return self._cache_f
        t = self.t
        if t_s <= t[0]:
            f = self.fields[0]
        elif t_s >= t[-1]:
            f = self.fields[-1]
        else:
            i = int(np.searchsorted(t, t_s, side="right") - 1)
            a = (t_s - t[i]) / (t[i + 1] - t[i])
            f = (1.0 - a) * self.fields[i] + a * self.fields[i + 1]
        self._cache_t, self._cache_f = t_s, f
        return f

    def _coeffs(self, t_s: float) -> list[np.ndarray]:
        """Per-cell bilinear coefficients: 12 flat tables [u, v, blh] x [A, B, C, D] with
        f(ax, ay) = A + ax (B + ay D) + ay C inside the cell."""
        if self._coef_t == t_s:
            return self._coef
        g = self.grid
        f = self.fields_at(t_s).reshape(g.ny, g.nx, 3)
        tabs = []
        for c in range(3):
            q = f[..., c]
            f00, f10, f01, f11 = q[:-1, :-1], q[:-1, 1:], q[1:, :-1], q[1:, 1:]
            tabs += [np.ascontiguousarray(a).ravel() for a in (f00, f10 - f00, f01 - f00, f11 - f10 - f01 + f00)]
        self._coef_t, self._coef = t_s, tabs
        return tabs

    def sample(self, lon: np.ndarray, lat: np.ndarray, t_s: float, need_blh: bool = True):
        """Returns u, v (m/s), blh (m) (None if not need_blh), inside (bool) for each point."""
        g = self.grid
        fx = (lon - g.lon0) * (1.0 / g.dlon)
        fy = (lat - g.lat0) * (1.0 / g.dlat)
        inside = (fx >= 0) & (fx <= g.nx - 1) & (fy >= 0) & (fy <= g.ny - 1)
        np.clip(fx, 0, g.nx - 1, out=fx)
        np.clip(fy, 0, g.ny - 1, out=fy)
        ix = np.minimum(fx.astype(np.intp), g.nx - 2)
        iy = np.minimum(fy.astype(np.intp), g.ny - 2)
        fx -= ix
        fy -= iy
        cell = iy * (g.nx - 1) + ix
        tabs = self._coeffs(t_s)
        out = []
        for c in range(3 if need_blh else 2):
            a, b, cc, d = (tabs[4 * c + k][cell] for k in range(4))
            d *= fy
            d += b
            d *= fx
            cc *= fy
            d += cc
            d += a
            out.append(d)
        if not need_blh:
            out.append(None)
        return out[0], out[1], out[2], inside

    def blh_on(self, grid: Grid, t_s: float) -> np.ndarray:
        """BLH (m) at every node of `grid`, shape (ny, nx). Nodes outside the met grid are clamped."""
        if grid not in self._grid_cache:
            lon2, lat2 = np.meshgrid(grid.lons, grid.lats)
            idx, w, _ = bilinear_setup(self.grid, lon2.ravel(), lat2.ravel())
            self._grid_cache[grid] = (idx, w)
        idx, w = self._grid_cache[grid]
        b = self.fields_at(t_s)[:, 2]
        return (w * b[idx]).sum(axis=0).reshape(grid.ny, grid.nx)
