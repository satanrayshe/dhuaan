"""Grid-hash DBSCAN-like clustering of fire detections (min_samples=1, i.e. single linkage).

Two detections are neighbours when they are within `eps_km` of each other and within
`window_h` hours. Clusters are the connected components of that neighbour graph.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime

import numpy as np

from .common import M_PER_DEG_LAT, M_PER_DEG_LON_EQ
from .types import Fire


def _find(parent: np.ndarray, i: int) -> int:
    root = i
    while parent[root] != root:
        root = parent[root]
    while parent[i] != root:
        parent[i], i = root, parent[i]
    return root


def cluster_fires(fires: list[Fire], eps_km: float = 1.5, window_h: float = 6.0) -> np.ndarray:
    """Return an int label per fire (0..n_clusters-1). Labels are ordered by the earliest
    detection time, then by latitude/longitude, so they are deterministic."""
    n = len(fires)
    if n == 0:
        return np.zeros(0, dtype=np.int64)
    lat = np.array([f.lat for f in fires])
    lon = np.array([f.lon for f in fires])
    t = np.array([f.time_utc.timestamp() for f in fires]) / 3600.0
    lat_ref = float(np.mean(lat))
    x = lon * (M_PER_DEG_LON_EQ / 1000.0) * np.cos(np.deg2rad(lat_ref))
    y = lat * (M_PER_DEG_LAT / 1000.0)
    cx = np.floor(x / eps_km).astype(np.int64)
    cy = np.floor(y / eps_km).astype(np.int64)
    cells: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i in range(n):
        cells[(int(cx[i]), int(cy[i]))].append(i)
    cell_arr = {k: np.array(v) for k, v in cells.items()}
    parent = np.arange(n)
    eps2 = eps_km * eps_km
    for (gx, gy), members in cell_arr.items():
        # Compare this cell to itself and to half of its neighbours (each pair once).
        for dx, dy in ((0, 0), (1, 0), (-1, 1), (0, 1), (1, 1)):
            other = cell_arr.get((gx + dx, gy + dy))
            if other is None:
                continue
            d2 = (x[members][:, None] - x[other][None, :]) ** 2 + (y[members][:, None] - y[other][None, :]) ** 2
            close = (d2 <= eps2) & (np.abs(t[members][:, None] - t[other][None, :]) <= window_h)
            ai, bi = np.nonzero(close)
            for a, b in zip(members[ai], other[bi]):
                ra, rb = _find(parent, int(a)), _find(parent, int(b))
                if ra != rb:
                    parent[max(ra, rb)] = min(ra, rb)
    roots = np.array([_find(parent, i) for i in range(n)])
    uniq, inv = np.unique(roots, return_inverse=True)
    # Deterministic ordering: earliest time, then lat, then lon of each component.
    k = len(uniq)
    t_min = np.full(k, np.inf)
    np.minimum.at(t_min, inv, t)
    lat_c = np.bincount(inv, lat, k) / np.bincount(inv, minlength=k)
    lon_c = np.bincount(inv, lon, k) / np.bincount(inv, minlength=k)
    order = np.lexsort((lon_c, lat_c, t_min))
    rank = np.empty(k, dtype=np.int64)
    rank[order] = np.arange(k)
    return rank[inv]


def cluster_id(label: int) -> str:
    return f"C{label:04d}"


def time_span(fires: list[Fire]) -> tuple[datetime, datetime]:
    ts = [f.time_utc for f in fires]
    return min(ts), max(ts)
