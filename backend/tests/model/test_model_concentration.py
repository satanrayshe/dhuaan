import numpy as np

from dhuaan.model import simulate
from dhuaan.model.common import fine_grid, output_grid
from dhuaan.model.concentration import (GaussOp, concentration_nodes, concentration_points, deposit,
                                         gaussian_kernel, sample)
from dhuaan.model.params import Member, Params
from dhuaan.model.synthetic import make_fires, make_met, make_population, make_receptors

from .helpers import T0


def test_kernel_integrates_to_one():
    h = 10.0
    x = np.linspace(-80, 80, 801)
    dx = x[1] - x[0]
    X, Y = np.meshgrid(x, x)
    total = gaussian_kernel(np.hypot(X, Y), h).sum() * dx * dx
    assert abs(total - 1.0) < 1e-3


def test_discrete_operator_conserves_mass():
    g = fine_grid()
    op = GaussOp(g, 10.0)
    m = deposit(g, np.array([75.73]), np.array([30.41]), np.array([1.0]))[0]
    dens = op.forward(m)                                  # kg/km2
    area_km2 = g.cell_area_m2()[:, None] / 1e6
    assert abs((dens * area_km2).sum() - 1.0) < 0.01


def test_adjoint_identity():
    g = output_grid()
    op = GaussOp(g, 10.0)
    rng = np.random.default_rng(0)
    a, b = rng.random((g.ny, g.nx)), rng.random((g.ny, g.nx))
    assert np.isclose((op.forward(a) * b).sum(), (a * op.adjoint(b)).sum(), rtol=1e-12)


def test_halving_blh_doubles_concentration():
    g = fine_grid()
    op = GaussOp(g, 10.0)
    rng = np.random.default_rng(2)
    m = deposit(g, rng.uniform(74, 77, 500), rng.uniform(29, 31, 500), rng.uniform(1, 5, 500))
    blh = rng.uniform(300, 1500, (g.ny, g.nx))
    c1 = concentration_nodes(op, m, blh)
    c2 = concentration_nodes(op, m, blh / 2)
    assert np.allclose(c2, 2 * c1, rtol=1e-12)


def test_halving_blh_doubles_concentration_end_to_end():
    fires = make_fires(T0, 5, 2, seed=4)
    rec = make_receptors(50, n_schools=3)
    p = Params(kh_scale=0.0, members=(Member(),))
    out = []
    for blh in (1000.0, 500.0):
        met = make_met(T0, u=0.0, v=0.0, blh=blh)
        out.append(simulate(fires, met, rec, make_population(), T0, members=1, params=p))
    a, b = out[0].grid_members, out[1].grid_members
    assert a.max() > 0
    assert np.allclose(b, 2 * a, rtol=1e-5, atol=1e-6)


def test_grid_matches_direct_kernel_sum():
    g = fine_grid()
    op = GaussOp(g, 10.0)
    rng = np.random.default_rng(5)
    lon, lat, w = rng.normal(75.5, 0.2, 2000), rng.normal(30.3, 0.15, 2000), rng.uniform(0.5, 1.5, 2000)
    blh = np.full((g.ny, g.nx), 700.0)
    c = concentration_nodes(op, deposit(g, lon, lat, w), blh)[0]
    rlon, rlat = np.array([75.5, 75.62, 75.3, 76.1]), np.array([30.3, 30.41, 30.1, 30.6])
    got = sample(g, c, rlon, rlat)
    ref = concentration_points(lon, lat, w, rlon, rlat, np.full(4, 700.0))
    assert np.all(np.abs(got / ref - 1) < 0.01)
