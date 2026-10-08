"""Source attribution. Every particle keeps its cluster label, so concentration splits exactly
by cluster; districts/states are sums over their clusters.

Per-cluster fields are accumulated over t0 .. t0+48 h on the 0.1 deg output grid (CIC
deposit of w / BLH at the deposit node, then one Gaussian convolution per cluster at the end)
and sampled at receptors. Shares at a receptor therefore sum to 1 by construction.
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np

from .common import Grid, bilinear_setup
from .concentration import KG_PER_KM2_PER_M_TO_UG_M3, GaussOp, sample


class AttributionAccumulator:
    def __init__(self, grid: Grid, op: GaussOp, n_clusters: int, n_members: int, blh_floor: float = 50.0):
        self.grid, self.op = grid, op
        self.k, self.m = n_clusters, n_members
        self.floor = blh_floor
        self.acc = np.zeros(n_clusters * grid.nx * grid.ny)

    def add(self, lon: np.ndarray, lat: np.ndarray, w: np.ndarray, cluster: np.ndarray, blh_nodes: np.ndarray) -> None:
        """Add one hourly snapshot (flat arrays over all members' live particles)."""
        if self.k == 0 or w.size == 0:
            return
        idx, cw, inside = bilinear_setup(self.grid, lon, lat)
        keep = inside & (w > 0)
        idx, cw = idx[:, keep], cw[:, keep]
        b = np.maximum(blh_nodes.reshape(-1), self.floor)
        val = cw * (w[keep] / self.m)[None, :] / b[idx]
        ncell = self.grid.nx * self.grid.ny
        flat = idx + (cluster[keep] * ncell)[None, :]
        self.acc += np.bincount(flat.ravel(), val.ravel(), minlength=self.acc.size)

    def cluster_fields(self) -> np.ndarray:
        """(K, ny, nx) time-integrated concentration per cluster (ug/m3 * h, ensemble mean)."""
        a = self.acc.reshape(self.k, self.grid.ny, self.grid.nx)
        return self.op.forward(a) * KG_PER_KM2_PER_M_TO_UG_M3

    def at_points(self, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
        """(K, n) time-integrated per-cluster concentration at points."""
        if self.k == 0:
            return np.zeros((0, np.size(lon)))
        return np.maximum(sample(self.grid, self.cluster_fields(), np.asarray(lon), np.asarray(lat)), 0.0)


def shares(values: np.ndarray) -> np.ndarray:
    """Normalise non-negative contributions to shares summing to 1 (all-zero -> zeros)."""
    v = np.maximum(np.asarray(values, dtype=np.float64), 0.0)
    s = v.sum()
    return v / s if s > 0 else np.zeros_like(v)


def place_attribution(contrib: np.ndarray, cluster_ids: list[str], districts: list[tuple[str, str]],
                      top: int = 5) -> tuple[list[dict], list[dict]]:
    """contrib: (K,) contributions at one place. Returns (attribution by district, top clusters).

    Attribution lists the top `top` districts plus {"district": "Other"} (if non-zero); shares
    are rounded to 4 dp and sum to 1 within rounding."""
    sh = shares(contrib)
    if sh.sum() == 0:
        return [], []
    by: dict[tuple[str, str], float] = defaultdict(float)
    for k in np.flatnonzero(sh):
        by[districts[k]] += float(sh[k])
    ranked = sorted(by.items(), key=lambda kv: -kv[1])
    head = [(ds, v) for ds, v in ranked[:top] if round(v, 4) > 0]
    attribution = [{"district": d, "state": s, "share": round(v, 4)} for (d, s), v in head]
    other = 1.0 - sum(v for _, v in head)
    if round(other, 4) > 0:
        attribution.append({"district": "Other", "state": "", "share": round(other, 4)})
    order = np.argsort(-sh)[:top]
    top_clusters = [{"cluster_id": cluster_ids[k], "share": round(float(sh[k]), 4)}
                    for k in order if round(float(sh[k]), 4) > 0]
    return attribution, top_clusters
