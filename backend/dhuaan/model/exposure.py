"""Exposure score per cluster: E_k = sum_t sum_cells pop_cell * C_k(cell, t) over the next 48 h.

Computed with the adjoint: E_k(t) = sum_{p in k} w_p * S_t(x_p), where S_t is the kernel
convolution of pop_eff / BLH placed at the output cell centres. This equals the forward sum
over cells (up to float rounding) at the cost of one convolution per hour.

pop_eff = population x school_factor (1.5) during 07:00-14:00 IST in cells containing a
school receptor. Units: persons x ug/m3 x hours ("person-hours" of smoke index).
"""
from __future__ import annotations

from datetime import datetime

import numpy as np

from .common import FINE_PER_OUT, IST, Grid
from .concentration import KG_PER_KM2_PER_M_TO_UG_M3, GaussOp, sample
from .params import Params
from .types import Receptor


def school_mask(out: Grid, receptors: list[Receptor]) -> np.ndarray:
    """(ny, nx) bool: output cells containing at least one school receptor."""
    mask = np.zeros((out.ny, out.nx), dtype=bool)
    for r in receptors:
        if r.kind != "school":
            continue
        i = int(np.floor((r.lon - (out.lon0 - out.dlon / 2)) / out.dlon))
        j = int(np.floor((r.lat - (out.lat0 - out.dlat / 2)) / out.dlat))
        if 0 <= i < out.nx and 0 <= j < out.ny:
            mask[j, i] = True
    return mask


def effective_population(pop: np.ndarray, schools: np.ndarray, t_utc: datetime, p: Params) -> np.ndarray:
    h = t_utc.astimezone(IST).hour
    lo, hi = p.school_hours_ist
    if lo <= h < hi:
        return np.where(schools, pop * p.school_factor, pop)
    return pop


class ExposureAccumulator:
    def __init__(self, fine: Grid, op: GaussOp, out: Grid, population: np.ndarray, schools: np.ndarray,
                 n_clusters: int, n_members: int, params: Params):
        pop = np.nan_to_num(np.asarray(population, dtype=np.float64), nan=0.0)
        if pop.shape != (out.ny, out.nx):
            raise ValueError(f"population_grid must have shape {(out.ny, out.nx)}, got {pop.shape}")
        self.fine, self.op, self.out = fine, op, out
        self.pop = np.maximum(pop, 0.0)
        self.schools = schools
        self.k, self.m, self.p = n_clusters, n_members, params
        self.e = np.zeros(n_clusters)
        self.c = FINE_PER_OUT // 2

    def add(self, t_utc: datetime, lon: np.ndarray, lat: np.ndarray, w: np.ndarray, cluster: np.ndarray,
            blh_out: np.ndarray) -> None:
        if self.k == 0 or w.size == 0:
            return
        q = effective_population(self.pop, self.schools, t_utc, self.p) / np.maximum(blh_out, self.p.blh_floor_m)
        qf = np.zeros((self.fine.ny, self.fine.nx))
        qf[self.c::FINE_PER_OUT, self.c::FINE_PER_OUT][: self.out.ny, : self.out.nx] = q
        s = self.op.adjoint(qf) * KG_PER_KM2_PER_M_TO_UG_M3
        sp = sample(self.fine, s, lon, lat)
        self.e += np.bincount(cluster, w * sp / self.m, minlength=self.k)

    @property
    def person_hours(self) -> np.ndarray:
        return self.e.copy()
