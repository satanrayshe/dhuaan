"""District lookup: district_of(lat, lon) -> (district, state), pure Python point-in-polygon.

Data: backend/data/districts.geojson, built by `python -m dhuaan.geo.districts` from geoBoundaries
(simplified) IND ADM2 (ODbL 1.0, 2021 LGD-based units) plus PAK ADM2 (public domain), because the
domain's west edge (72.5E) reaches Lahore/Faisalabad and cross-border fires must not be pinned on an
Indian district. Every district whose bbox meets DOMAIN is kept whole (not cut at the edge), so lookups
near the edge stay correct. State names come from IND/PAK ADM1 by point-in-polygon at build time
(diacritics stripped: "Haryāna" -> "Haryana"); Pakistani units get "<province> (Pakistan)".
Outside every polygon (e.g. a river-bed point on a simplified border) we return the nearest district.
"""
from __future__ import annotations

import json
import math
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from dhuaan.config import DATA_DIR, DOMAIN

DISTRICTS_FILE = DATA_DIR / "districts.geojson"
GB = "https://github.com/wmgeolab/geoBoundaries/raw/9469f09/releaseData/gbOpen"

Ring = list[tuple[float, float]]  # (lon, lat)


def ascii_name(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().strip()


def _polys(geom: dict[str, Any]) -> list[list[Ring]]:
    """GeoJSON Polygon/MultiPolygon -> list of polygons, each a list of rings (outer first)."""
    if geom["type"] == "Polygon":
        return [[[(float(x), float(y)) for x, y, *_ in r] for r in geom["coordinates"]]]
    if geom["type"] == "MultiPolygon":
        return [[[(float(x), float(y)) for x, y, *_ in r] for r in p] for p in geom["coordinates"]]
    return []


def _in_ring(x: float, y: float, ring: Ring) -> bool:
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def in_polygons(x: float, y: float, polys: list[list[Ring]]) -> bool:
    for rings in polys:
        if rings and _in_ring(x, y, rings[0]) and not any(_in_ring(x, y, h) for h in rings[1:]):
            return True
    return False


def _bbox(polys: list[list[Ring]]) -> tuple[float, float, float, float]:
    xs = [p[0] for rings in polys for p in rings[0]]
    ys = [p[1] for rings in polys for p in rings[0]]
    return min(xs), min(ys), max(xs), max(ys)


def _interior_point(polys: list[list[Ring]]) -> tuple[float, float]:
    """A point inside the largest polygon: its vertex centroid if inside, else the middle of the widest
    horizontal chord through that latitude."""
    def area(r: Ring) -> float:
        return abs(sum(r[i][0] * r[i - 1][1] - r[i - 1][0] * r[i][1] for i in range(len(r)))) / 2
    rings = max(polys, key=lambda p: area(p[0]))
    outer = rings[0]
    cx = sum(p[0] for p in outer) / len(outer)
    cy = sum(p[1] for p in outer) / len(outer)
    if in_polygons(cx, cy, [rings]):
        return cx, cy
    xs = []
    for i in range(len(outer)):
        (x1, y1), (x2, y2) = outer[i - 1], outer[i]
        if (y1 > cy) != (y2 > cy):
            xs.append(x1 + (cy - y1) * (x2 - x1) / (y2 - y1))
    xs.sort()
    best = max(((xs[k], xs[k + 1]) for k in range(0, len(xs) - 1, 2)), key=lambda c: c[1] - c[0], default=(cx, cx))
    return (best[0] + best[1]) / 2, cy


# ---------- runtime lookup ----------

class _Index:
    def __init__(self, features: list[dict[str, Any]]):
        self.items = []
        for f in features:
            polys = _polys(f["geometry"])
            if polys:
                self.items.append((f["properties"]["district"], f["properties"]["state"], _bbox(polys), polys))

    def lookup(self, lat: float, lon: float) -> tuple[str, str]:
        for name, state, (x0, y0, x1, y1), polys in self.items:
            if x0 <= lon <= x1 and y0 <= lat <= y1 and in_polygons(lon, lat, polys):
                return name, state
        return self.nearest(lat, lon)

    def nearest(self, lat: float, lon: float) -> tuple[str, str]:
        k = math.cos(math.radians(lat))
        best, bd = ("Unknown", "Unknown"), float("inf")
        for name, state, (x0, y0, x1, y1), polys in self.items:
            # cheap bbox distance bound first
            dx = max(x0 - lon, 0, lon - x1) * k
            dy = max(y0 - lat, 0, lat - y1)
            if dx * dx + dy * dy >= bd:
                continue
            for rings in polys:
                for x, y in rings[0]:
                    d = ((x - lon) * k) ** 2 + (y - lat) ** 2
                    if d < bd:
                        bd, best = d, (name, state)
        return best


@lru_cache(maxsize=1)
def _index(path: str = str(DISTRICTS_FILE)) -> _Index:
    return _Index(json.loads(Path(path).read_text(encoding="utf-8"))["features"])


def district_of(lat: float, lon: float) -> tuple[str, str]:
    """(district, state) containing the point, else the nearest district."""
    return _index().lookup(float(lat), float(lon))


def load_districts(path: Path = DISTRICTS_FILE) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))["features"]


# ---------- build ----------

def _round_geom(polys: list[list[Ring]], dp: int = 3) -> dict[str, Any]:
    out = []
    for rings in polys:
        rr = []
        for r in rings:
            pts: list[list[float]] = []
            for x, y in r:
                p = [round(x, dp), round(y, dp)]
                if not pts or pts[-1] != p:
                    pts.append(p)
            if len(pts) >= 4:
                rr.append(pts)
        if rr:
            out.append(rr)
    return {"type": "MultiPolygon", "coordinates": out}


def _meets_domain(b: tuple[float, float, float, float], pad: float = 0.0) -> bool:
    return not (b[2] < DOMAIN["lon_min"] - pad or b[0] > DOMAIN["lon_max"] + pad
                or b[3] < DOMAIN["lat_min"] - pad or b[1] > DOMAIN["lat_max"] + pad)


def build_features(adm2: Iterable[dict[str, Any]], adm1: list[dict[str, Any]], country: str) -> list[dict[str, Any]]:
    states = [(ascii_name(f["properties"]["shapeName"]), _polys(f["geometry"])) for f in adm1]
    states = [(n, p, _bbox(p)) for n, p in states if p]
    out = []
    for f in adm2:
        polys = _polys(f["geometry"])
        if not polys:
            continue
        b = _bbox(polys)
        if not _meets_domain(b):
            continue
        x, y = _interior_point(polys)
        state = next((n for n, p, (x0, y0, x1, y1) in states
                      if x0 <= x <= x1 and y0 <= y <= y1 and in_polygons(x, y, p)), "Unknown")
        if country == "PAK":
            state = f"{state} (Pakistan)"
        out.append({"type": "Feature", "properties": {
            "district": ascii_name(f["properties"]["shapeName"]), "state": state, "country": country,
            "gb_id": f["properties"].get("shapeID", "")}, "geometry": _round_geom(polys)})
    return out


def build(use_cache: bool = True) -> Path:
    from dhuaan.ingest.common import fetch
    feats: list[dict[str, Any]] = []
    for c in ("IND", "PAK"):
        get = lambda lv: json.loads(fetch(f"{GB}/{c}/{lv}/geoBoundaries-{c}-{lv}_simplified.geojson",
                                          namespace="geo", timeout=300, use_cache=use_cache))["features"]
        feats += build_features(get("ADM2"), get("ADM1"), c)
    feats.sort(key=lambda f: (f["properties"]["country"], f["properties"]["state"], f["properties"]["district"]))
    doc = {"type": "FeatureCollection",
           "attribution": "geoBoundaries (Runfola et al. 2020): IND ADM2 (ODbL 1.0, Pathways Data / lgdirectory.gov.in), "
                          "IND ADM1 (CC BY 2.5 IN, DataMeet), PAK ADM1/ADM2 (public domain)",
           "features": feats}
    DISTRICTS_FILE.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    _index.cache_clear()
    return DISTRICTS_FILE


if __name__ == "__main__":
    p = build()
    fs = load_districts(p)
    print(f"wrote {len(fs)} districts to {p} ({p.stat().st_size // 1024} KB)")
    for q in [(30.266, 76.04), (28.73, 77.11), (30.34, 76.39), (31.52, 74.35), (28.61, 77.21)]:
        print(q, district_of(*q))
