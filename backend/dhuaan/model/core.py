"""model.run(): fires + met + receptors -> artifact dict (see docs/CONTRACTS.md)."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable

import numpy as np

from dhuaan.config import DOMAIN

from .advect import integrate
from .attribution import AttributionAccumulator
from .common import FINE_PER_OUT, HOURS_BEFORE, N_HOURS, fine_grid, floor_hour, output_grid
from .concentration import GaussOp, concentration_nodes, deposit, sample
from .emission import Sources, build_sources
from .exposure import ExposureAccumulator, school_mask
from .met import MetInterp
from .params import Member, Params, members_for
from .types import Fire, MetField, Receptor


@dataclass
class ModelResult:
    t0: datetime
    fires: list[Fire]
    receptors: list[Receptor]
    sources: Sources
    members: tuple[Member, ...]
    afternoon_mode: str
    params: Params
    grid_members: np.ndarray          # (M, 97, ny, nx) float32 smoke at output cell centres
    rec_members: np.ndarray           # (M, 97, Nr) float32 smoke at receptors
    exposure: np.ndarray              # (K,) person-hours, next 48 h, ensemble mean
    contrib: np.ndarray               # (K, Nr) per-cluster smoke integrated over t0..t0+48h
    trips: list[tuple[int, list[list[float]], list[int]]] = field(default_factory=list)
    t_start_s: float = 0.0
    runtime_s: float = 0.0


def simulate(
    fires: list[Fire],
    met: MetField,
    receptors: list[Receptor],
    population_grid: np.ndarray,
    t0: datetime,
    *,
    members: int | tuple[Member, ...] = 5,
    seed: int = 0,
    afternoon_mode: str = "none",
    district_of: Callable[[float, float], tuple[str, str]] | None = None,
    params: Params | None = None,
    afternoon_ratio: dict[str, float] | None = None,
) -> ModelResult:
    t_wall = time.perf_counter()
    p = params or Params()
    t0 = floor_hour(t0)
    if isinstance(members, int):
        mem = tuple(p.members[:members]) if members <= len(p.members) else members_for(members)
    else:
        mem = tuple(members)
    if not mem:
        raise ValueError("need at least one ensemble member")
    if 3600 % int(p.dt_s) or (p.trip_step_min * 60) % int(p.dt_s):
        raise ValueError("dt_s must divide 3600 s and the trip step")
    M = len(mem)
    src = build_sources(fires, t0, afternoon_mode, district_of, p, seed, afternoon_ratio)
    parts = src.particles
    K = len(src.clusters)

    met_i = MetInterp(met, t0, p)
    fine, out = fine_grid(), output_grid()
    op_fine = GaussOp(fine, p.h_km)
    op_out = GaussOp(out, p.h_km)
    bounds = (max(DOMAIN["lon_min"], met_i.grid.lon0), min(DOMAIN["lon_max"], met_i.grid.lons[-1]),
              max(DOMAIN["lat_min"], met_i.grid.lat0), min(DOMAIN["lat_max"], met_i.grid.lats[-1]))

    rlon = np.array([r.lon for r in receptors], dtype=np.float64)
    rlat = np.array([r.lat for r in receptors], dtype=np.float64)
    nr = len(receptors)
    grid_m = np.zeros((M, N_HOURS, out.ny, out.nx), dtype=np.float32)
    rec_m = np.zeros((M, N_HOURS, nr), dtype=np.float32)
    attr = AttributionAccumulator(out, op_out, K, M, p.blh_floor_m)
    expo = ExposureAccumulator(fine, op_fine, out, population_grid, school_mask(out, receptors), K, M, p)

    first_out_s = -HOURS_BEFORE * 3600.0
    t_end_s = (N_HOURS - 1 - HOURS_BEFORE) * 3600.0
    t_start_s = first_out_s
    if parts.n:
        t_start_s = min(first_out_s, np.floor(parts.t_rel.min() / p.dt_s) * p.dt_s)
    t_start_s = max(t_start_s, -p.lookback_h * 3600.0)

    # trips: member-0 particles, recorded every trip_step_min from t0-24h
    rng = np.random.default_rng(seed + 1)
    n_cand = min(parts.n, int(p.max_trips * 1.5) + 50)
    cand = np.sort(rng.choice(parts.n, size=n_cand, replace=False)) if parts.n else np.zeros(0, dtype=np.int64)
    trip_lon, trip_lat, trip_ok, trip_t = [], [], [], []
    trip_step_s = p.trip_step_min * 60.0
    exp_lo, exp_hi = 0.0, p.exposure_hours * 3600.0
    c = FINE_PER_OUT // 2

    for snap in integrate(parts, met_i, mem, p, t_start_s, t_end_s, bounds, seed):
        t = snap.t_s
        if t < first_out_s:
            continue
        rel = t - first_out_s
        if rel % trip_step_s == 0 and cand.size:
            trip_lon.append(snap.lon[0, cand].copy())
            trip_lat.append(snap.lat[0, cand].copy())
            trip_ok.append(snap.w[0, cand] > 0)
            trip_t.append(int(round(rel / 60.0)))
        if rel % 3600.0:
            continue
        k = int(round(rel / 3600.0))
        live = np.flatnonzero(snap.w.reshape(-1) > 0)
        mi, pi = np.divmod(live, max(parts.n, 1))
        lon = snap.lon.reshape(-1)[live]
        lat = snap.lat.reshape(-1)[live]
        w = snap.w.reshape(-1)[live]
        blh_f = met_i.blh_on(fine, t)
        mass = deposit(fine, lon, lat, w, n_layers=M, layer=mi)
        conc = concentration_nodes(op_fine, mass, blh_f, p.blh_floor_m)
        grid_m[:, k] = conc[:, c::FINE_PER_OUT, c::FINE_PER_OUT][:, : out.ny, : out.nx]
        if nr:
            rec_m[:, k] = sample(fine, conc, rlon, rlat)
        if exp_lo <= t < exp_hi and live.size:
            blh_o = met_i.blh_on(out, t)
            cl = parts.cluster[pi]
            attr.add(lon, lat, w, cl, blh_o)
            expo.add(t0 + timedelta(seconds=t), lon, lat, w, cl, blh_o)

    np.maximum(grid_m, 0, out=grid_m)
    np.maximum(rec_m, 0, out=rec_m)
    contrib = attr.at_points(rlon, rlat) if nr else np.zeros((K, 0))

    trips: list[tuple[int, list[list[float]], list[int]]] = []
    if trip_ok:
        ok = np.array(trip_ok)            # (T, C)
        tl, ta = np.array(trip_lon), np.array(trip_lat)
        for j in range(cand.size):
            rows = np.flatnonzero(ok[:, j])
            if rows.size < 2:
                continue
            path = np.round(np.stack([tl[rows, j], ta[rows, j]], axis=1), 4).tolist()
            trips.append((int(parts.cluster[cand[j]]), path, [trip_t[r] for r in rows]))
            if len(trips) >= p.max_trips:
                break

    return ModelResult(t0, list(fires), list(receptors), src, mem, afternoon_mode, p, grid_m, rec_m,
                       expo.person_hours, contrib, trips, t_start_s, time.perf_counter() - t_wall)


def run(
    fires: list[Fire],
    met: MetField,
    receptors: list[Receptor],
    population_grid: np.ndarray,
    t0: datetime,
    *,
    members: int = 5,
    seed: int = 0,
    afternoon_mode: str = "none",
    district_of: Callable[[float, float], tuple[str, str]] | None = None,
    params: Params | None = None,
    afternoon_ratio: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Run the smoke model and return {filename: JSON-serialisable object} for artifacts 1-6,
    plus "_summary" (for meta.json; the pipeline must not write it as a file)."""
    from .artifacts import build_artifacts

    t_wall = time.perf_counter()
    res = simulate(fires, met, receptors, population_grid, t0, members=members, seed=seed,
                   afternoon_mode=afternoon_mode, district_of=district_of, params=params,
                   afternoon_ratio=afternoon_ratio)
    arts = build_artifacts(res)
    arts["_summary"]["runtime_s"] = round(time.perf_counter() - t_wall, 2)
    return arts
