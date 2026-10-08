import math

import numpy as np

from dhuaan.model import simulate
from dhuaan.model.advect import k_h
from dhuaan.model.common import M_PER_DEG_LAT, m_per_deg_lon
from dhuaan.model.met import MetInterp, mixed_layer_wind
from dhuaan.model.params import Member, Params
from dhuaan.model.synthetic import make_fires, make_met, make_population, make_receptors

from .helpers import T0, particles, run_to

NO_DIFF = Params(kh_scale=0.0)


def test_uniform_wind_u_displacement_within_1pct():
    met = make_met(T0, u=5.0, v=0.0, blh=200.0)          # BLH below 925 hPa: 10 m wind only
    parts = particles([73.0, 73.5], [30.0, 29.5])
    (lon, lat, w), _ = run_to(parts, met, 24 * 3600.0, NO_DIFF)
    assert np.all(w > 0)
    dx = (lon[0] - parts.lon) * m_per_deg_lon(parts.lat)
    expected = 5.0 * 24 * 3600
    assert np.all(np.abs(dx / expected - 1) < 0.01)
    assert np.allclose(lat[0], parts.lat)


def test_uniform_wind_v_displacement_within_1pct():
    met = make_met(T0, u=0.0, v=3.0, blh=200.0)          # BLH below 925 hPa: 10 m wind only
    parts = particles([75.0], [29.0])
    (lon, lat, w), _ = run_to(parts, met, 24 * 3600.0, NO_DIFF)
    assert w[0, 0] > 0
    dy = (lat[0, 0] - 29.0) * M_PER_DEG_LAT
    assert abs(dy / (3.0 * 24 * 3600) - 1) < 0.01
    assert abs(lon[0, 0] - 75.0) < 1e-12


def test_uniform_mixed_layer_wind_displacement():
    met = make_met(T0, u=2.0, v=0.0, blh=1000.0)         # 10 m + 925 hPa (u925 = 1.4 u) -> 2.4 m/s
    parts = particles([73.0], [30.5])
    (lon, _, w), _ = run_to(parts, met, 24 * 3600.0, NO_DIFF)
    dx = (lon[0, 0] - 73.0) * m_per_deg_lon(30.5)
    assert w[0, 0] > 0 and abs(dx / (2.4 * 86400) - 1) < 0.01


def test_zero_wind_zero_diffusion_is_static():
    met = make_met(T0, u=0.0, v=0.0, blh=1000.0)
    parts = particles(np.linspace(73, 78, 7), 30.5)
    (lon, lat, w), _ = run_to(parts, met, 48 * 3600.0, NO_DIFF)
    assert np.array_equal(lon[0], parts.lon) and np.array_equal(lat[0], parts.lat)
    assert np.all(w > 0)


def test_infinite_tau_conserves_mass():
    met = make_met(T0, u=0.3, v=0.2, blh=600.0)
    rng = np.random.default_rng(1)
    parts = particles(rng.uniform(75, 76, 200), rng.uniform(30, 31, 200), t_rel=rng.uniform(0, 7200, 200),
                      w0=rng.uniform(0.5, 2.0, 200))
    _, masses = run_to(parts, met, 36 * 3600.0, Params(tau_h=math.inf))
    released = np.array(masses[8:])                     # all released after 2 h (8 steps)
    assert np.allclose(released, parts.w0.sum(), rtol=1e-12)


def test_finite_tau_decays_exponentially():
    met = make_met(T0, u=0.0, v=0.0, blh=600.0)
    parts = particles([75.0], [30.0], w0=1.0)
    _, masses = run_to(parts, met, 48 * 3600.0, Params(kh_scale=0.0))
    assert math.isclose(masses[-1], math.exp(-1.0), rel_tol=1e-9)


def test_out_of_domain_particle_dies():
    met = make_met(T0, u=10.0, v=0.0, blh=800.0)
    parts = particles([78.8], [30.0])
    (_, _, w), _ = run_to(parts, met, 6 * 3600.0, NO_DIFF)
    assert w[0, 0] == 0.0


def test_mixed_layer_levels_and_kh():
    met = make_met(T0, u=1.0, v=0.0, blh=200.0)            # u925 = 1.4, u850 = 1.8 in make_met
    p = Params()
    u, _ = mixed_layer_wind(met, p)
    assert np.allclose(u, 1.0)
    met.blh[:] = 1000.0
    assert np.allclose(mixed_layer_wind(met, p)[0], (1.0 + 1.4) / 2)
    met.blh[:] = 2000.0
    assert np.allclose(mixed_layer_wind(met, p)[0], (1.0 + 1.4 + 1.8) / 3)
    assert k_h(np.array([100.0]), p)[0] == 1e3 and k_h(np.array([3000.0]), p)[0] == 5e3
    assert math.isclose(k_h(np.array([900.0]), p)[0], 3e3)


def test_met_time_interpolation_is_linear():
    met = make_met(T0, u=0.0, v=0.0, blh=500.0)
    for k in range(len(met.times)):
        met.u10[k] = float(k)
    mi = MetInterp(met, T0, Params())
    t_mid = (met.times[10] - T0).total_seconds() + 1800.0
    u, _, _, inside = mi.sample(np.array([75.0]), np.array([30.0]), t_mid)
    assert inside[0] and math.isclose(u[0], 10.5)


def test_ensemble_spread_zero_without_perturbation():
    met = make_met(T0, u=2.0, v=-1.0, veer=True)
    fires = make_fires(T0, 6, 2, seed=3)
    rec = make_receptors(60, n_schools=5)
    zero = Params(members=(Member(),) * 3)
    res = simulate(fires, met, rec, make_population(), T0, members=3, params=zero)
    assert res.rec_members.max() > 0
    assert np.ptp(res.rec_members, axis=0).max() == 0.0
    assert np.ptp(res.grid_members, axis=0).max() == 0.0
    res2 = simulate(fires, met, rec, make_population(), T0, members=3)
    assert np.ptp(res2.rec_members, axis=0).max() > 0            # default perturbations do spread
