"""Offline tests for districts, receptors and population (synthetic inputs + the committed data files)."""
from __future__ import annotations

import json
import struct
import zlib

import numpy as np
import pytest

from dhuaan.geo import districts, population, receptors

SQ = {"type": "Polygon", "coordinates": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]],
                                         [[4, 4], [6, 4], [6, 6], [4, 6], [4, 4]]]}


# ---------- districts ----------

def test_point_in_polygon_with_hole():
    polys = districts._polys(SQ)
    assert districts.in_polygons(1, 1, polys)
    assert not districts.in_polygons(5, 5, polys)  # in the hole
    assert not districts.in_polygons(11, 5, polys)


def test_build_features_assigns_state_and_skips_outside():
    adm1 = [{"properties": {"shapeName": "Haryāna"},
             "geometry": {"type": "Polygon", "coordinates": [[[74, 28], [78, 28], [78, 31], [74, 31], [74, 28]]]}}]
    adm2 = [{"properties": {"shapeName": "Kaithal", "shapeID": "a"},
             "geometry": {"type": "Polygon", "coordinates": [[[76, 29.5], [76.5, 29.5], [76.5, 30], [76, 30], [76, 29.5]]]}},
            {"properties": {"shapeName": "Far", "shapeID": "b"},
             "geometry": {"type": "Polygon", "coordinates": [[[90, 20], [91, 20], [91, 21], [90, 21], [90, 20]]]}}]
    out = districts.build_features(adm2, adm1, "IND")
    assert len(out) == 1 and out[0]["properties"]["state"] == "Haryana" and out[0]["properties"]["district"] == "Kaithal"
    idx = districts._Index(out)
    assert idx.lookup(29.7, 76.2) == ("Kaithal", "Haryana")
    assert idx.lookup(29.7, 76.6) == ("Kaithal", "Haryana")  # outside: nearest fallback


def test_interior_point_concave():
    u = [[(0, 0), (3, 0), (3, 3), (2, 3), (2, 1), (1, 1), (1, 3), (0, 3), (0, 0)]]
    x, y = districts._interior_point([u])
    assert districts.in_polygons(x, y, [u])


@pytest.mark.parametrize("lat,lon,exp", [
    (30.266, 76.04, ("Sangrur", "Punjab")), (30.34, 76.39, ("Patiala", "Punjab")),
    (28.61, 77.21, ("New Delhi", "Delhi")), (31.52, 74.35, ("Lahore", "Punjab (Pakistan)")),
    (29.69, 76.98, ("Karnal", "Haryana")),
])
def test_district_of_real_file(lat, lon, exp):
    assert districts.district_of(lat, lon) == exp


# ---------- receptors ----------

GN = "\t".join


def test_parse_geonames_and_kind():
    rows = [GN(["1", "Patiala", "Patiala", "", "30.33", "76.39", "P", "PPLA2", "IN", "", "23", "", "", "", "446246", "", "", "", ""]),
            GN(["2", "Old Fort", "Old Fort", "", "30.33", "76.39", "P", "PPLH", "IN", "", "23", "", "", "", "0", "", "", "", ""]),
            GN(["3", "Kot", "Kot", "", "30.20", "76.10", "P", "PPL", "IN", "", "23", "", "", "", "0", "", "", "", ""]),
            GN(["4", "Chennai", "Chennai", "", "13.08", "80.27", "P", "PPLA", "IN", "", "25", "", "", "", "4000000", "", "", "", ""]),
            GN(["5", "River", "River", "", "30.20", "76.10", "H", "STM", "IN", "", "23", "", "", "", "0", "", "", "", ""])]
    out = receptors.parse_geonames("\n".join(rows))
    assert [r["gid"] for r in out] == [1, 3]
    assert receptors.kind_for(446246, "PPLA2") == "city"
    assert receptors.kind_for(5000, "PPLA2") == "town"
    assert receptors.kind_for(12000, "PPL") == "town"
    assert receptors.kind_for(0, "PPL") == "village"
    sel = receptors.select_settlements(out, lambda la, lo: "Punjab")
    assert {r["gid"] for r in sel} == {1, 3}  # Patiala kept by population, Kot as the cell's village


def test_parse_schools_and_thin():
    els = [{"type": "way", "id": 1, "center": {"lat": 30.2666, "lon": 76.0401}, "tags": {"name": "Govt  School"}},
           {"type": "node", "id": 2, "lat": 30.27, "lon": 76.04, "tags": {}},
           {"type": "node", "id": 3, "lat": 28.70, "lon": 77.10, "tags": {"name": "A"}},
           {"type": "node", "id": 4, "lat": 28.701, "lon": 77.101, "tags": {"name": "B"}}]
    s = receptors.parse_schools(els)
    assert [x["id"] for x in s] == ["osm-n3", "osm-n4", "osm-w1"] and s[2]["name"] == "Govt School"
    thin = receptors.thin_schools(s, lambda la, lo: ("Sangrur" if la > 30 else "North", ""))
    assert [x["id"] for x in thin] == ["osm-n3", "osm-w1"]
    receptors.add_locality(thin, [{"name": "Bhawanigarh", "lat": 30.266, "lon": 76.04, "pop": 20000}])
    assert thin[1]["name"] == "Govt School, Bhawanigarh"


def test_parse_wards_centroid():
    doc = {"features": [{"properties": {"Ward_Name": "ROHINI", "Ward_No": "21"},
                         "geometry": {"type": "Polygon", "coordinates": [[[77, 28], [77.2, 28], [77.2, 28.2], [77, 28.2], [77, 28]]]}}]}
    w = receptors.parse_wards(doc)[0]
    assert w["id"] == "dlw-21" and w["lat"] == pytest.approx(28.1) and w["lon"] == pytest.approx(77.1)
    assert "pre-2022" in w["name"] and w["name"].startswith("Rohini")


def test_receptors_file():
    recs = receptors.load_receptors()
    assert 1000 < len(recs) <= 3500
    ids = [r.id for r in recs]
    assert len(ids) == len(set(ids))
    kinds = {r.kind for r in recs}
    assert kinds == {"village", "town", "city", "school", "ward"}
    assert all(r.district and r.state for r in recs)
    assert all(28.0 <= r.lat <= 32.75 and 72.5 <= r.lon <= 79.0 for r in recs)
    demo = receptors.load_demo_places()
    by = {r.id: r for r in recs}
    s = by[demo["school"]["id"]]
    assert s.kind == "school" and s.district == "Sangrur" and receptors.km((s.lat, s.lon), receptors.BHAWANIGARH) < 2
    assert by[demo["ward"]["id"]].kind == "ward" and "Rohini" in by[demo["ward"]["id"]].name
    assert by[demo["town"]["id"]].name == "Patiala"
    assert [p["id"] for p in demo["places"]] == [demo["school"]["id"], demo["ward"]["id"], demo["town"]["id"]]


# ---------- population ----------

def _bigtiff(arr: np.ndarray, tile: int, left: float, top: float, res: float) -> bytes:
    """Minimal tiled, deflate, float64 BigTIFF (one IFD) for testing the COG reader."""
    h, w = arr.shape
    tiles = []
    for r in range(0, h, tile):
        for c in range(0, w, tile):
            t = np.full((tile, tile), np.nan)
            blk = arr[r:r + tile, c:c + tile]
            t[:blk.shape[0], :blk.shape[1]] = blk
            tiles.append(zlib.compress(t.astype("<f8").tobytes()))
    n = len(tiles)
    data_off = 16
    offs, pos = [], data_off
    for t in tiles:
        offs.append(pos)
        pos += len(t)
    arrays_off = pos
    offs_blob = struct.pack(f"<{n}Q", *offs)
    cnts_blob = struct.pack(f"<{n}Q", *[len(t) for t in tiles])
    scale_blob = struct.pack("<3d", res, res, 0.0)
    tie_blob = struct.pack("<6d", 0, 0, 0, left, top, 0)
    ext = [offs_blob, cnts_blob, scale_blob, tie_blob]
    ext_offs, p = [], arrays_off
    for b in ext:
        ext_offs.append(p)
        p += len(b)
    ifd_off = p
    entries = [(256, 3, 1, w), (257, 3, 1, h), (258, 3, 1, 64), (259, 3, 1, 8), (317, 3, 1, 1), (322, 3, 1, tile),
               (323, 3, 1, tile), (324, 16, n, ext_offs[0]), (325, 16, n, ext_offs[1]), (339, 3, 1, 3),
               (33550, 12, 3, ext_offs[2]), (33922, 12, 6, ext_offs[3])]
    ifd = struct.pack("<Q", len(entries))
    for tag, typ, cnt, val in entries:
        v = struct.pack("<H", val) + b"\0" * 6 if typ == 3 else struct.pack("<Q", val)
        ifd += struct.pack("<HHQ", tag, typ, cnt) + v  # inline value or offset
    ifd += struct.pack("<Q", 0)
    head = b"II" + struct.pack("<HHHQ", 43, 8, 0, ifd_off)
    return head + b"".join(tiles) + b"".join(ext) + ifd


def test_cog_reader_conserves_persons():
    res = 0.025
    arr = np.full((80, 120), np.nan)  # 2 x 3 deg starting at 72.5E, 30.0N top
    arr[0:4, 0:4] = 1.0      # cell lat 29.9-30.0, lon 72.5-72.6  -> 16 persons
    arr[40, 60] = 7.0        # pixel centre 74.0125E, 28.9875N
    arr[79, 119] = 2.5
    blob = _bigtiff(arr, 32, 72.5, 30.0, res)
    reader = lambda url, a, b: blob[a:b + 1]
    lvl = population.read_first_ifd("mem", reader)
    assert (lvl.width, lvl.height, lvl.tile_w, lvl.compression) == (120, 80, 32, 8)
    assert lvl.left == 72.5 and lvl.top == 30.0
    out = np.zeros((population.NY, population.NX))
    added = population.aggregate("mem", lvl, out, reader)
    assert added == pytest.approx(16 + 7 + 2.5) and out.sum() == pytest.approx(25.5)
    assert out[19, 0] == pytest.approx(16)       # row 19 = 29.9..30.0 (row 0 south)
    assert out[9, 15] == pytest.approx(7)        # 28.9..29.0, 74.0..74.1
    out2 = np.zeros_like(out)
    population.aggregate("mem", lvl, out2, reader, band=(29.0, 40.0))
    assert out2.sum() == pytest.approx(16)       # band clipping drops pixels south of 29N


def test_population_file():
    p = population.load_population()
    assert p.shape == (48, 66) and (p >= 0).all()
    assert 1.5e8 < p.sum() < 3.0e8
    delhi = p[int((28.6 - 28.0) * 10), int((77.2 - 72.5) * 10)]
    rural_rajasthan = p[int((28.3 - 28.0) * 10), int((73.0 - 72.5) * 10)]
    assert delhi > 20 * rural_rajasthan
    doc = json.loads(population.POP_FILE.read_text())
    assert doc["row0"] == "south" and doc["nx"] == 66 and doc["ny"] == 48
