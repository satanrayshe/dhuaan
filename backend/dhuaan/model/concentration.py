"""Concentration: C(x, t) = sum_p w_p K(|x - x_p|, h) / BLH(x, t), Gaussian K with h = 10 km.

Implementation: particles are deposited (cloud-in-cell) onto a 0.025 deg node grid, the
deposit is convolved with the separable Gaussian (dense banded matrices; the x kernel
uses the row's latitude), divided by BLH at each node, and sampled at the 0.1 deg output
cell centres (every 4th node) and bilinearly at receptors. With h = 10 km and 2.5 km nodes
the discretisation error is well under 1 %.

Units: w in kg, K in 1/km2, BLH in m -> C in ug/m3 (C = 1e3 * sum w K / BLH).
"""
from __future__ import annotations

import numpy as np

from .common import M_PER_DEG_LAT, Grid, bilinear_setup, m_per_deg_lon

KG_PER_KM2_PER_M_TO_UG_M3 = 1e3   # 1 kg/km2 spread over 1 m depth = 1e9 ug / 1e6 m3


def gaussian_kernel(r_km: np.ndarray, h_km: float) -> np.ndarray:
    """2D Gaussian kernel density (1/km2); integrates to 1 over the plane."""
    r = np.asarray(r_km, dtype=np.float64)
    return np.exp(-0.5 * (r / h_km) ** 2) / (2.0 * np.pi * h_km * h_km)


def _gauss1d(d_km: np.ndarray, h_km: float) -> np.ndarray:
    return np.exp(-0.5 * (d_km / h_km) ** 2) / (np.sqrt(2.0 * np.pi) * h_km)


class GaussOp:
    """Separable Gaussian convolution on a node grid: mass per node (kg) -> density (kg/km2)."""

    def __init__(self, grid: Grid, h_km: float, band_rows: int = 8):
        self.grid = grid
        jj = np.arange(grid.ny)
        dy_km = grid.dlat * M_PER_DEG_LAT / 1000.0
        self.gy = _gauss1d((jj[:, None] - jj[None, :]) * dy_km, h_km)        # (ny, ny) 1/km
        ii = np.arange(grid.nx)
        self.bands: list[tuple[int, int, np.ndarray]] = []
        for r0 in range(0, grid.ny, band_rows):
            r1 = min(grid.ny, r0 + band_rows)
            lat_mid = grid.lat0 + grid.dlat * 0.5 * (r0 + r1 - 1)
            dx_km = grid.dlon * float(m_per_deg_lon(lat_mid)) / 1000.0
            self.bands.append((r0, r1, _gauss1d((ii[:, None] - ii[None, :]) * dx_km, h_km)))

    def _xconv(self, a: np.ndarray) -> np.ndarray:
        out = np.empty_like(a)
        for r0, r1, gx in self.bands:
            out[..., r0:r1, :] = a[..., r0:r1, :] @ gx
        return out

    def forward(self, mass: np.ndarray) -> np.ndarray:
        """(..., ny, nx) mass per node -> (..., ny, nx) density, x-conv (source row kernel) then y-conv."""
        return self.gy @ self._xconv(mass)

    def adjoint(self, q: np.ndarray) -> np.ndarray:
        """Transpose of forward(): sum_n q[n] * forward(m)[n] == sum_n m[n] * adjoint(q)[n]."""
        return self._xconv(self.gy @ q)


def deposit(grid: Grid, lon: np.ndarray, lat: np.ndarray, w: np.ndarray, n_layers: int = 1,
            layer: np.ndarray | None = None) -> np.ndarray:
    """Cloud-in-cell deposit of weights onto grid nodes -> (n_layers, ny, nx).

    `layer` (same shape as w) selects the output layer of each point (e.g. member index)."""
    idx, cw, inside = bilinear_setup(grid, lon, lat)
    keep = inside & (w != 0)
    idx, cw, w = idx[:, keep], cw[:, keep], w[keep]
    ncell = grid.nx * grid.ny
    if layer is not None:
        idx = idx + layer[keep][None, :] * ncell
    out = np.bincount(idx.ravel(), (cw * w[None, :]).ravel(), minlength=n_layers * ncell)
    return out.reshape(n_layers, grid.ny, grid.nx)


def sample(grid: Grid, field: np.ndarray, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    """Bilinear sample of field (..., ny, nx) at points -> (..., n). Points outside are clamped."""
    idx, cw, _ = bilinear_setup(grid, lon, lat)
    f = field.reshape(*field.shape[:-2], -1)
    return (f[..., idx] * cw).sum(axis=-2)


def concentration_nodes(op: GaussOp, mass: np.ndarray, blh_nodes: np.ndarray, blh_floor: float = 50.0) -> np.ndarray:
    """Mass per node (..., ny, nx) and BLH (ny, nx) in m -> concentration (ug/m3) at nodes."""
    return op.forward(mass) * (KG_PER_KM2_PER_M_TO_UG_M3 / np.maximum(blh_nodes, blh_floor))


def concentration_points(lon_p, lat_p, w_p, lon_r, lat_r, blh_r, h_km: float = 10.0) -> np.ndarray:
    """Direct (slow, exact) evaluation at a few receptors; used as a reference in tests."""
    lon_p, lat_p, w_p = map(np.asarray, (lon_p, lat_p, w_p))
    lon_r, lat_r, blh_r = (np.atleast_1d(np.asarray(a, dtype=np.float64)) for a in (lon_r, lat_r, blh_r))
    dx = (lon_p[None, :] - lon_r[:, None]) * m_per_deg_lon(lat_r)[:, None] / 1000.0
    dy = (lat_p[None, :] - lat_r[:, None]) * M_PER_DEG_LAT / 1000.0
    k = gaussian_kernel(np.hypot(dx, dy), h_km)
    return KG_PER_KM2_PER_M_TO_UG_M3 * (k * w_p[None, :]).sum(axis=1) / blh_r
