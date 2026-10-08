"""Build artifacts 1-6 (docs/CONTRACTS.md) from a ModelResult."""
from __future__ import annotations

import base64
from datetime import timedelta
from typing import Any

import numpy as np

from .attribution import place_attribution
from .common import HOURS_BEFORE, IST, M_PER_DEG_LAT, N_HOURS, iso, m_per_deg_lon, output_grid
from .core import ModelResult

DOWNWIND_N = 5


def _r(x: float, nd: int) -> float:
    return float(round(float(x), nd))


def smoke_scale(grid: np.ndarray, pct: float = 99.0) -> float:
    """99th percentile of the non-negligible smoke values over the run (1.0 if there is none)."""
    g = np.asarray(grid, dtype=np.float64).ravel()
    if g.size == 0 or not np.isfinite(g).any() or g.max() <= 0:
        return 1.0
    pos = g[g > g.max() * 1e-6]
    s = float(np.percentile(pos, pct))
    return s if s > 0 else 1.0


def encode_frame(frame: np.ndarray, scale: float) -> str:
    v = np.round(255.0 * np.minimum(1.0, np.maximum(frame, 0.0) / scale)).astype(np.uint8)
    return base64.b64encode(np.ascontiguousarray(v).tobytes()).decode("ascii")


def first_crossing(series: np.ndarray, thr: float, start: int = HOURS_BEFORE) -> np.ndarray:
    """series (..., 97) -> index of first hour >= start with value >= thr, or -1."""
    s = np.asarray(series)[..., start:] >= thr
    hit = s.any(axis=-1)
    return np.where(hit, s.argmax(axis=-1) + start, -1)


def build_artifacts(res: ModelResult) -> dict[str, Any]:
    p = res.params
    t0 = res.t0
    t0s = iso(t0)
    hours = [t0 + timedelta(hours=k - HOURS_BEFORE) for k in range(N_HOURS)]
    hours_iso = [iso(h) for h in hours]
    src = res.sources
    clusters = src.clusters
    K = len(clusters)
    cids = [c.cluster_id for c in clusters]
    receptors = res.receptors
    nr = len(receptors)

    # ---- grid.json (ensemble median) ----
    out = output_grid()
    grid_med = np.median(res.grid_members, axis=0)                     # (97, ny, nx)
    scale = smoke_scale(grid_med, p.scale_pct)
    thr = p.arrival_frac * scale
    grid = {
        "lon0": _r(out.lon0 - out.dlon / 2, 4), "lat0": _r(out.lat0 - out.dlat / 2, 4),
        "dlon": out.dlon, "dlat": out.dlat, "nx": out.nx, "ny": out.ny,
        "t0_utc": t0s, "hours": N_HOURS, "scale": _r(scale, 4),
        "frames": [encode_frame(grid_med[k], scale) for k in range(N_HOURS)],
    }

    # ---- places ----
    rm = res.rec_members.astype(np.float64)                             # (M, 97, Nr)
    if nr:
        med = np.median(rm, axis=0)                                     # (97, Nr)
        p10 = np.percentile(rm, 10, axis=0)
        p90 = np.percentile(rm, 90, axis=0)
        arr = first_crossing(med.T, thr)                                # (Nr,)
        arr_m = first_crossing(np.moveaxis(rm, 1, 2), thr)              # (M, Nr)
        fc = med[HOURS_BEFORE:]
        peak_k = fc.argmax(axis=0) + HOURS_BEFORE
        peak_v = fc.max(axis=0)
    places: dict[str, dict] = {}
    index = []
    dist_of_cluster = [(c.district, c.state) for c in clusters]
    for j, r in enumerate(receptors):
        a = int(arr[j])
        # earliest..latest member crossing, widened to include the median's own arrival
        crossed = arr_m[:, j][arr_m[:, j] >= 0]
        if a >= 0:
            crossed = np.append(crossed, a)
        window = [hours_iso[int(crossed.min())], hours_iso[int(crossed.max())]] if crossed.size else None
        attribution, top_cl = place_attribution(res.contrib[:, j], cids, dist_of_cluster) if K else ([], [])
        base = {"id": r.id, "name": r.name, "kind": r.kind, "district": r.district, "state": r.state,
                "lat": _r(r.lat, 4), "lon": _r(r.lon, 4)}
        pk_utc, pk_v = hours_iso[int(peak_k[j])], _r(peak_v[j], 2)
        arrival = hours_iso[a] if a >= 0 else None
        places[r.id] = {
            **base, "t0_utc": t0s,
            "series": np.round(med[:, j], 2).tolist(),
            "p10": np.round(p10[:, j], 2).tolist(),
            "p90": np.round(p90[:, j], 2).tolist(),
            "arrival_utc": arrival, "arrival_window": window,
            "peak_utc": pk_utc, "peak_smoke": pk_v,
            "attribution": attribution, "top_clusters": top_cl,
        }
        index.append({**base, "peak_smoke": pk_v, "peak_utc": pk_utc, "arrival_utc": arrival})

    # ---- clusters.json ----
    expo = np.asarray(res.exposure, dtype=np.float64)
    tot = expo.sum()
    order = sorted(range(K), key=lambda k: (-expo[k], -clusters[k].frp_sum_mw, k))
    rank = {k: i + 1 for i, k in enumerate(order)}
    pops = np.array([r.population if r.population is not None else np.nan for r in receptors], dtype=np.float64)
    known = pops[np.isfinite(pops)]
    pops = np.where(np.isfinite(pops), pops, float(np.median(known)) if known.size else 1.0)
    rlat = np.array([r.lat for r in receptors])
    rlon = np.array([r.lon for r in receptors])
    cl_items = []
    for k in order:
        c = clusters[k]
        near, near_id, downwind = None, None, []
        if nr:
            d2 = ((rlon - c.lon) * m_per_deg_lon(c.lat)) ** 2 + ((rlat - c.lat) * M_PER_DEG_LAT) ** 2
            jn = int(np.argmin(d2))
            near, near_id = receptors[jn].name, receptors[jn].id
            score = res.contrib[k] * pops
            for j in np.argsort(-score)[:DOWNWIND_N]:
                if score[j] <= 0:
                    break
                pl = places[receptors[j].id]
                downwind.append({"place_id": receptors[j].id, "name": receptors[j].name, "kind": receptors[j].kind,
                                 "arrival_utc": pl["arrival_utc"], "peak_utc": pl["peak_utc"],
                                 "peak_smoke": pl["peak_smoke"]})
        cl_items.append({
            "cluster_id": c.cluster_id, "lat": _r(c.lat, 4), "lon": _r(c.lon, 4),
            "n_detections": c.n_detections, "frp_sum_mw": _r(c.frp_sum_mw, 2),
            "first_seen_utc": iso(c.first_seen), "last_seen_utc": iso(c.last_seen),
            "district": c.district, "state": c.state,
            "nearest_place": near, "nearest_place_id": near_id, "rank": rank[k],
            "exposure_person_hours": _r(expo[k], 1),
            "exposure_share": _r(expo[k] / tot, 6) if tot > 0 else 0.0,
            "afternoon_estimated_kg": _r(c.afternoon_mass_kg, 1),
            "downwind": downwind,
        })

    # ---- fires.geojson ----
    feats = []
    for i, f in enumerate(res.fires):
        lab = int(src.fire_labels[i])
        loc = f.time_utc.astimezone(IST)
        feats.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [_r(f.lon, 5), _r(f.lat, 5)]},
            "properties": {"id": f.id, "sensor": f.sensor,
                           "frp_mw": None if f.frp_mw is None else _r(f.frp_mw, 2),
                           "confidence": f.confidence, "acq_utc": iso(f.time_utc),
                           "cluster_id": cids[lab] if lab >= 0 else None,
                           "afternoon": loc.hour >= 15},
        })

    trips = {"t0_utc": t0s, "step_minutes": p.trip_step_min,
             "trips": [{"cluster_id": cids[k], "path": path, "ts": ts} for k, path, ts in res.trips]}

    arts: dict[str, Any] = {
        "fires.geojson": {"type": "FeatureCollection", "features": feats},
        "clusters.json": {"t0_utc": t0s, "clusters": cl_items},
        "trips.json": trips,
        "grid.json": grid,
        "receptors_index.json": {"t0_utc": t0s, "places": index},
    }
    for pid, pl in places.items():
        arts[f"places/{pid}.json"] = pl
    arts["_summary"] = {
        "n_fires": len(res.fires),
        "n_fires_modelled": int((src.fire_labels >= 0).sum()),
        "n_clusters": K,
        "n_particles": int(src.particles.n),
        "members": len(res.members),
        "runtime_s": round(res.runtime_s, 2),
        "scale": _r(scale, 4),
        "arrival_threshold": _r(thr, 4),
        "sim_start_utc": iso(t0 + timedelta(seconds=res.t_start_s)),
        "afternoon_mode": res.afternoon_mode,
        "notes": list(src.notes),
    }
    return arts
