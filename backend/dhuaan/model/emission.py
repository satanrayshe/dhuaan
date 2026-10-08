"""Sources: clusters -> emission masses -> particles (release time, position, weight)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable

import numpy as np

from dhuaan.config import DATA_DIR, DOMAIN

from .cluster import cluster_fires, cluster_id
from .common import IST, M_PER_DEG_LAT, UTC, m_per_deg_lon
from .params import Params
from .types import GEO_SENSORS, POLAR_SENSORS, Fire

DistrictOf = Callable[[float, float], tuple[str, str]]


def _unknown_district(lat: float, lon: float) -> tuple[str, str]:
    return ("Unknown", "Unknown")


@dataclass
class Cluster:
    label: int
    cluster_id: str
    fire_idx: list[int]
    lat: float
    lon: float
    n_detections: int
    frp_sum_mw: float
    first_seen: datetime
    last_seen: datetime
    district: str
    state: str
    mass_kg: float = 0.0              # observed-detection emission
    afternoon_mass_kg: float = 0.0    # estimated missed late-afternoon emission
    n_particles: int = 0


@dataclass
class Particles:
    lon: np.ndarray       # (P,) release position
    lat: np.ndarray
    t_rel: np.ndarray     # (P,) release time, seconds since t0
    w0: np.ndarray        # (P,) kg at release
    cluster: np.ndarray   # (P,) cluster label
    est: np.ndarray       # (P,) bool: estimated afternoon emission

    @property
    def n(self) -> int:
        return int(self.lon.size)


@dataclass
class Sources:
    clusters: list[Cluster]
    particles: Particles
    fire_labels: np.ndarray          # (n_fires,) cluster label or -1 if not modelled
    frp_filled: np.ndarray           # (n_fires,) FRP used (MW)
    notes: list[str] = field(default_factory=list)


def load_afternoon_ratio(path=None) -> dict[str, float]:
    p = path or (DATA_DIR / "afternoon_ratio.json")
    try:
        with open(p, encoding="utf-8") as fh:
            data = json.load(fh)
        return {str(k): float(v) for k, v in data.items()}
    except (OSError, ValueError, TypeError, AttributeError):
        return {}


def in_domain(lat: float, lon: float) -> bool:
    return DOMAIN["lat_min"] <= lat <= DOMAIN["lat_max"] and DOMAIN["lon_min"] <= lon <= DOMAIN["lon_max"]


def allocate_particles(weights: np.ndarray, p: Params) -> np.ndarray:
    """n_k proportional to weight, clamped to [min, max], total <= particle_cap."""
    w = np.asarray(weights, dtype=np.float64)
    if w.size == 0:
        return np.zeros(0, dtype=np.int64)
    lo = max(1, min(p.min_particles, p.particle_cap // w.size))
    hi = max(lo, p.max_particles)

    def count(q: float) -> np.ndarray:
        return np.clip(np.round(w / q), lo, hi).astype(np.int64)

    q_lo = max(float(w.max()), 1e-30) / hi           # biggest source gets `hi`
    if count(q_lo).sum() <= p.particle_cap:
        return count(q_lo)
    q_hi = q_lo
    while count(q_hi).sum() > p.particle_cap and q_hi < 1e30:
        q_hi *= 2.0
    for _ in range(60):                              # bisection on the particle quantum
        q = 0.5 * (q_lo + q_hi)
        if count(q).sum() > p.particle_cap:
            q_lo = q
        else:
            q_hi = q
    return count(q_hi)


def build_sources(
    fires: list[Fire],
    t0: datetime,
    afternoon_mode: str = "none",
    district_of: DistrictOf | None = None,
    params: Params | None = None,
    seed: int = 0,
    afternoon_ratio: dict[str, float] | None = None,
) -> Sources:
    p = params or Params()
    if afternoon_mode not in ("none", "estimated", "observed"):
        raise ValueError(f"afternoon_mode must be none|estimated|observed, got {afternoon_mode!r}")
    district_of = district_of or _unknown_district
    rng = np.random.default_rng(seed)
    notes: list[str] = []

    known = [f.frp_mw for f in fires if f.frp_mw is not None and f.frp_mw > 0]
    frp_fill = float(np.median(known)) if known else p.frp_default_mw
    frp = np.array([f.frp_mw if (f.frp_mw is not None and f.frp_mw > 0) else frp_fill for f in fires],
                   dtype=np.float64)

    t_min = t0 - timedelta(hours=p.lookback_h)
    t_max = t0 + timedelta(hours=1)
    use: list[int] = []
    for i, f in enumerate(fires):
        if not in_domain(f.lat, f.lon) or not (t_min <= f.time_utc <= t_max):
            continue
        if f.sensor in GEO_SENSORS and afternoon_mode != "observed":
            continue   # geostationary detections are emitting sources only in "observed" mode
        use.append(i)
    labels = np.full(len(fires), -1, dtype=np.int64)
    lab = cluster_fires([fires[i] for i in use], p.eps_km, p.window_h)
    if use:
        labels[np.array(use)] = lab
    n_cl = int(lab.max()) + 1 if lab.size else 0

    if afternoon_ratio is None:
        afternoon_ratio = load_afternoon_ratio() if afternoon_mode == "estimated" else {}
    ratio_default = float(afternoon_ratio.get("_default", p.afternoon_ratio_default))

    groups: list[list[int]] = [[] for _ in range(n_cl)]
    for i in use:
        groups[labels[i]].append(i)

    clusters: list[Cluster] = []
    # source tuples: (label, mass_kg, t_start_s, t_end_s, detection indices, is_estimated)
    srcs: list[tuple[int, float, float, float, list[int], bool]] = []
    kg_per_mw = p.burn_duration_s * p.ce_kg_per_mj      # MW x s = MJ; x kg/MJ
    for k, idx in enumerate(groups):
        fr = frp[idx]
        lat_c = float(np.average([fires[i].lat for i in idx], weights=fr))
        lon_c = float(np.average([fires[i].lon for i in idx], weights=fr))
        times = [fires[i].time_utc for i in idx]
        dist, state = district_of(lat_c, lon_c)
        c = Cluster(k, cluster_id(k), idx, lat_c, lon_c, len(idx), float(fr.sum()), min(times), max(times),
                    str(dist), str(state), mass_kg=float(fr.sum() * kg_per_mw))
        ts = (c.first_seen - t0).total_seconds() - p.burn_before_h * 3600
        te = (c.last_seen - t0).total_seconds() + p.burn_after_h * 3600
        srcs.append((k, c.mass_kg, ts, te, idx, False))
        if afternoon_mode == "estimated":
            polar = [i for i in idx if fires[i].sensor in POLAR_SENSORS]
            if polar:
                last_ist = max(fires[i].time_utc for i in polar).astimezone(IST)
                if last_ist.hour + last_ist.minute / 60 < p.afternoon_start_ist:
                    day = last_ist.replace(hour=0, minute=0, second=0, microsecond=0)
                    a0 = (day + timedelta(hours=p.afternoon_start_ist)).astimezone(UTC)
                    a1 = (day + timedelta(hours=p.afternoon_end_ist)).astimezone(UTC)
                    ratio = float(afternoon_ratio.get(c.district, ratio_default))
                    c.afternoon_mass_kg = float(frp[polar].sum() * kg_per_mw * ratio)
                    if c.afternoon_mass_kg > 0:
                        srcs.append((k, c.afternoon_mass_kg, (a0 - t0).total_seconds(),
                                     (a1 - t0).total_seconds(), polar, True))
        clusters.append(c)

    n_per = allocate_particles(np.array([s[1] for s in srcs]), p)
    total = int(n_per.sum())
    lon = np.empty(total)
    lat = np.empty(total)
    t_rel = np.empty(total)
    w0 = np.empty(total)
    cl = np.empty(total, dtype=np.int64)
    est = np.zeros(total, dtype=bool)
    pos = 0
    for (k, mass, ts, te, idx, is_est), n in zip(srcs, n_per):
        n = int(n)
        sl = slice(pos, pos + n)
        t_rel[sl] = ts + (np.arange(n) + rng.random(n)) / n * (te - ts)   # stratified in the window
        pick = rng.choice(len(idx), size=n, p=frp[idx] / frp[idx].sum())
        dlat = np.array([fires[i].lat for i in idx])[pick]
        dlon = np.array([fires[i].lon for i in idx])[pick]
        jit = rng.normal(0.0, p.release_jitter_m, size=(2, n))
        lat[sl] = dlat + jit[1] / M_PER_DEG_LAT
        lon[sl] = dlon + jit[0] / m_per_deg_lon(dlat)
        w0[sl] = mass / n
        cl[sl] = k
        est[sl] = is_est
        clusters[k].n_particles += n
        pos += n
    if total >= p.particle_cap:
        notes.append(f"particle cap {p.particle_cap} reached")
    return Sources(clusters, Particles(lon, lat, t_rel, w0, cl, est), labels, frp, notes)
