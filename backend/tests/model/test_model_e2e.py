import base64
import copy
import json

import numpy as np
import pytest

from dhuaan.model import run
from dhuaan.model.schema import SchemaError, validate_artifact, validate_artifacts, validate_meta
from dhuaan.model.synthetic import district_grid, make_fires, make_met, make_population, make_receptors

from .helpers import T0


@pytest.fixture(scope="module")
def arts():
    fires = make_fires(T0, 25, 3, seed=2, geo_fraction=0.1)
    met = make_met(T0, u=1.8, v=-0.9, veer=True)
    rec = make_receptors(120, n_schools=10)
    return run(fires, met, rec, make_population(), T0, members=5, seed=0, afternoon_mode="estimated",
               district_of=district_grid)


def test_artifacts_pass_schema(arts):
    validate_artifacts(arts)
    names = {k for k in arts if not k.startswith("places/")}
    assert names == {"fires.geojson", "clusters.json", "trips.json", "grid.json", "receptors_index.json", "_summary"}
    assert sum(k.startswith("places/") for k in arts) == 120
    json.dumps({k: v for k, v in arts.items()})                 # JSON-serialisable


def test_summary_and_content(arts):
    s = arts["_summary"]
    for k in ("n_fires", "n_clusters", "n_particles", "runtime_s", "scale", "arrival_threshold"):
        assert k in s
    assert s["n_clusters"] == len(arts["clusters.json"]["clusters"]) > 0
    assert np.isclose(s["arrival_threshold"], 0.15 * s["scale"], rtol=1e-3)
    g = arts["grid.json"]
    assert (g["nx"], g["ny"], g["hours"], g["lon0"], g["lat0"]) == (66, 48, 97, 72.5, 28.0)
    frames = [np.frombuffer(base64.b64decode(f), np.uint8) for f in g["frames"]]
    assert max(f.max() for f in frames) == 255
    cl = arts["clusters.json"]["clusters"]
    assert [c["rank"] for c in cl] == list(range(1, len(cl) + 1))
    assert abs(sum(c["exposure_share"] for c in cl) - 1) < 1e-3
    assert all(cl[i]["exposure_person_hours"] >= cl[i + 1]["exposure_person_hours"] for i in range(len(cl) - 1))
    trips = arts["trips.json"]["trips"]
    assert 0 < len(trips) <= 6000
    assert all(t % 30 == 0 for tr in trips[:50] for t in tr["ts"])
    places = [v for k, v in arts.items() if k.startswith("places/")]
    smoky = [p for p in places if p["arrival_utc"]]
    assert smoky, "expected some places to see smoke arrive"
    for p in smoky:
        assert p["arrival_window"] is not None
        assert p["arrival_window"][0] <= p["arrival_utc"] <= p["arrival_window"][1]
    gk = [f for f in arts["fires.geojson"]["features"] if f["properties"]["sensor"] == "GK2A"]
    assert gk and all(f["properties"]["cluster_id"] is None for f in gk)     # not sources in "estimated"


def test_schema_rejects_bad_artifacts(arts):
    bad = copy.deepcopy(arts["places/R00000.json"])
    bad["series"] = bad["series"][:-1]
    with pytest.raises(SchemaError):
        validate_artifact("places/R00000.json", bad)
    g = copy.deepcopy(arts["grid.json"])
    g["frames"][3] = base64.b64encode(b"\x00" * 10).decode()
    with pytest.raises(SchemaError):
        validate_artifact("latest/grid.json", g)
    c = copy.deepcopy(arts["clusters.json"])
    c["t0_utc"] = "2026-10-08 12:00"
    with pytest.raises(SchemaError):
        validate_artifact("runs/abc/clusters.json", c)
    with pytest.raises(SchemaError):
        validate_meta({"run_id": "x"})


def test_deterministic(arts):
    fires = make_fires(T0, 25, 3, seed=2, geo_fraction=0.1)
    met = make_met(T0, u=1.8, v=-0.9, veer=True)
    rec = make_receptors(120, n_schools=10)
    again = run(fires, met, rec, make_population(), T0, members=5, seed=0, afternoon_mode="estimated",
                district_of=district_grid)
    assert again["grid.json"]["frames"] == arts["grid.json"]["frames"]
    assert again["clusters.json"] == arts["clusters.json"]


def test_empty_inputs():
    met = make_met(T0)
    out = run([], met, make_receptors(5, n_schools=1), make_population(), T0, members=2)
    validate_artifacts(out)
    assert out["_summary"]["n_clusters"] == 0 and out["trips.json"]["trips"] == []
