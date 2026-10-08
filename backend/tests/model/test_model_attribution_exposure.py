import numpy as np
import pytest

from dhuaan.model import simulate
from dhuaan.model.attribution import place_attribution, shares
from dhuaan.model.common import FINE_PER_OUT, fine_grid, output_grid
from dhuaan.model.concentration import GaussOp, concentration_nodes, deposit
from dhuaan.model.exposure import ExposureAccumulator, school_mask
from dhuaan.model.params import Params
from dhuaan.model.synthetic import district_grid, make_fires, make_met, make_population, make_receptors

from .helpers import T0


@pytest.fixture(scope="module")
def small_run():
    fires = make_fires(T0, 12, 3, seed=7)
    rec = make_receptors(150, n_schools=10)
    met = make_met(T0, u=1.5, v=-1.0, veer=True)
    return simulate(fires, met, rec, make_population(), T0, members=3, district_of=district_grid)


def test_attribution_shares_sum_to_one(small_run):
    res = small_run
    contrib = res.contrib
    assert contrib.shape == (len(res.sources.clusters), len(res.receptors))
    hit = np.flatnonzero(contrib.sum(axis=0) > 0)
    assert hit.size > 10
    cids = [c.cluster_id for c in res.sources.clusters]
    dists = [(c.district, c.state) for c in res.sources.clusters]
    for j in hit:
        assert abs(shares(contrib[:, j]).sum() - 1.0) < 1e-12
        attribution, top = place_attribution(contrib[:, j], cids, dists)
        assert abs(sum(a["share"] for a in attribution) - 1.0) < 1e-3
        assert len(attribution) <= 6 and len(top) <= 5


def test_attribution_total_tracks_concentration(small_run):
    """Sum over clusters of the 48 h attributed smoke ~ the 48 h sum of the receptor series."""
    res = small_run
    total_attr = res.contrib.sum(axis=0)
    total_series = res.rec_members[:, 24:72].mean(axis=0).sum(axis=0)
    big = total_series > np.percentile(total_series, 75)
    ratio = total_attr[big].sum() / total_series[big].sum()
    assert 0.85 < ratio < 1.15


def _snapshot(seed=0):
    rng = np.random.default_rng(seed)
    n = 3000
    lon, lat = rng.normal(75.0, 0.3, n), rng.normal(30.5, 0.2, n)
    w = rng.uniform(0.5, 1.5, n)
    cl = rng.integers(0, 4, n)
    return lon, lat, w, cl


def test_exposure_equals_forward_sum():
    fine, out, p = fine_grid(), output_grid(), Params()
    op = GaussOp(fine, p.h_km)
    pop = make_population()
    blh_out = np.full((out.ny, out.nx), 600.0)
    acc = ExposureAccumulator(fine, op, out, pop, np.zeros_like(pop, bool), 4, 1, p)
    lon, lat, w, cl = _snapshot()
    acc.add(T0, lon, lat, w, cl, blh_out)
    c = concentration_nodes(op, deposit(fine, lon, lat, w), np.full((fine.ny, fine.nx), 600.0))[0]
    k = FINE_PER_OUT // 2
    forward = (pop * c[k::FINE_PER_OUT, k::FINE_PER_OUT][: out.ny, : out.nx]).sum()
    assert np.isclose(acc.person_hours.sum(), forward, rtol=1e-9)


def test_more_downwind_population_never_lowers_exposure():
    fine, out, p = fine_grid(), output_grid(), Params()
    op = GaussOp(fine, p.h_km)
    pop = make_population()
    blh_out = np.full((out.ny, out.nx), 600.0)
    lon, lat, w, cl = _snapshot(1)
    base = ExposureAccumulator(fine, op, out, pop, np.zeros_like(pop, bool), 4, 1, p)
    base.add(T0, lon, lat, w, cl, blh_out)
    more_pop = pop.copy()
    more_pop[20:30, 20:40] *= 3.0                            # downwind block gets more people
    more = ExposureAccumulator(fine, op, out, more_pop, np.zeros_like(pop, bool), 4, 1, p)
    more.add(T0, lon, lat, w, cl, blh_out)
    assert np.all(more.person_hours >= base.person_hours)
    assert more.person_hours.sum() > base.person_hours.sum()


def test_more_population_never_lowers_exposure_end_to_end():
    fires = make_fires(T0, 8, 2, seed=11)
    rec = make_receptors(40, n_schools=4)
    met = make_met(T0, u=2.0, v=0.5)
    pop = make_population()
    e1 = simulate(fires, met, rec, pop, T0, members=2).exposure
    pop2 = pop.copy()
    pop2[:, 40:] += 5e4                                     # east (downwind) gets more people
    e2 = simulate(fires, met, rec, pop2, T0, members=2).exposure
    assert np.all(e2 >= e1 * (1 - 1e-12)) and e2.sum() > e1.sum()


def test_school_hours_weighting():
    out, p = output_grid(), Params()
    rec = make_receptors(30, n_schools=30)
    mask = school_mask(out, rec)
    assert mask.sum() > 0
    from dhuaan.model.exposure import effective_population
    from datetime import datetime, timezone
    pop = np.ones((out.ny, out.nx))
    school_time = datetime(2026, 10, 8, 4, 0, tzinfo=timezone.utc)      # 09:30 IST
    night = datetime(2026, 10, 8, 18, 0, tzinfo=timezone.utc)           # 23:30 IST
    assert effective_population(pop, mask, school_time, p)[mask].min() == 1.5
    assert effective_population(pop, mask, night, p).max() == 1.0
