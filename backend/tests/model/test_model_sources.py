from datetime import timedelta

import numpy as np

from dhuaan.model.cluster import cluster_fires
from dhuaan.model.common import IST
from dhuaan.model.emission import allocate_particles, build_sources
from dhuaan.model.params import Params
from dhuaan.model.types import Fire

from .helpers import T0


def fire(i, lat, lon, dt_h=-4.0, frp=10.0, sensor="VIIRS_SNPP"):
    return Fire(f"f{i}", lat, lon, T0 + timedelta(hours=dt_h), frp, sensor, "nominal")


def test_cluster_eps_and_time_window():
    d = 1.0 / 111.0                                         # ~1 km in latitude
    fires = [fire(0, 30.0, 75.0), fire(1, 30.0 + d, 75.0), fire(2, 30.0 + 2 * d, 75.0),   # chain -> 1 cluster
             fire(3, 30.0 + 5 * d, 75.0),                    # 3 km away -> separate
             fire(4, 30.0, 75.0, dt_h=-20.0)]               # same place, 16 h earlier -> separate
    lab = cluster_fires(fires)
    assert lab[0] == lab[1] == lab[2]
    assert len({lab[0], lab[3], lab[4]}) == 3


def test_particle_allocation_clamps_and_caps():
    p = Params(particle_cap=50_000)
    n = allocate_particles(np.array([1.0, 1000.0, 50.0]), p)
    assert n.min() >= 20 and n.max() == 400
    n = allocate_particles(np.random.default_rng(0).lognormal(0, 1, 2000), p)
    assert n.sum() <= 50_000 and n.min() >= 20 and n.max() <= 400


def test_frp_none_filled_with_median_and_burn_window():
    fires = [fire(0, 30.0, 75.0, frp=4.0), fire(1, 30.5, 75.5, frp=8.0), fire(2, 31.0, 76.0, frp=None)]
    src = build_sources(fires, T0)
    assert np.allclose(src.frp_filled, [4.0, 8.0, 6.0])
    t_det = -4 * 3600.0
    tr = src.particles.t_rel
    assert tr.min() >= t_det - 0.5 * 3600 - 1e-6 and tr.max() <= t_det + 1.5 * 3600 + 1e-6
    k = src.particles.cluster
    assert np.allclose([src.particles.w0[k == c].sum() for c in range(3)], [c.mass_kg for c in src.clusters])


def test_afternoon_modes():
    day = T0.astimezone(IST).replace(hour=13, minute=30) - timedelta(days=1)
    viirs = Fire("v", 30.0, 75.0, day, 10.0, "VIIRS_NOAA20", "high")
    gk2a = Fire("g", 30.2, 75.2, day + timedelta(hours=3), None, "GK2A", "nominal")
    none = build_sources([viirs, gk2a], T0, "none")
    assert len(none.clusters) == 1 and none.fire_labels[1] == -1
    est = build_sources([viirs, gk2a], T0, "estimated", afternoon_ratio={"_default": 2.0})
    c = est.clusters[0]
    assert np.isclose(c.afternoon_mass_kg, 2.0 * c.mass_kg)
    late = est.particles.t_rel[est.particles.est]
    lo = (day.replace(hour=16, minute=0) - T0).total_seconds()
    assert late.min() >= lo - 1e-6 and late.max() <= lo + 3 * 3600 + 1e-6
    est_d = build_sources([viirs], T0, "estimated", district_of=lambda la, lo: ("Ludhiana", "Punjab"),
                          afternoon_ratio={"Ludhiana": 3.0, "_default": 2.0})
    assert np.isclose(est_d.clusters[0].afternoon_mass_kg, 3.0 * est_d.clusters[0].mass_kg)
    obs = build_sources([viirs, gk2a], T0, "observed")
    assert len(obs.clusters) == 2 and np.all(obs.fire_labels >= 0)
    assert not obs.particles.est.any()


def test_out_of_window_and_domain_fires_ignored():
    fires = [fire(0, 30.0, 75.0, dt_h=-60.0), fire(1, 35.0, 75.0), fire(2, 30.0, 75.0)]
    src = build_sources(fires, T0)
    assert list(src.fire_labels) == [-1, -1, 0]
