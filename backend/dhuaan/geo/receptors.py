"""Receptors: villages, towns, cities (GeoNames), schools (OpenStreetMap) and Delhi wards (datameet).

Runtime: load_receptors() reads backend/data/receptors.json (built by `python -m dhuaan.geo.receptors`).

Build rules
- GeoNames IN.zip (CC BY 4.0), feature class P inside DOMAIN, excluding sections/historical/abandoned
  (PPLX, PPLH, PPLQ, PPLW). Kept: population >= 2000 or an admin seat (PPLA*, PPLC).
  kind = city (pop >= 100k), town (pop >= 10k, or a PPLA/PPLA2 seat), village otherwise.
  GeoNames has no populations for most villages, so for coverage we add one village per 0.1 deg cell
  across Punjab, Haryana and Chandigarh (the most populous by GeoNames, ties by lowest id).
- OSM amenity=school (ODbL) in Punjab, Haryana, Chandigarh and Delhi via Overpass (User-Agent, mirror retry).
  Unnamed schools are dropped; every school in Sangrur district is kept; elsewhere at most one per 0.03 deg cell.
  A school name gets ", <nearest GeoNames place within 3 km>" appended so search can tell them apart.
- Delhi wards: centroids of datameet Municipal_Spatial_Data/Delhi/Delhi_Wards.geojson (CC BY-SA 2.5 IN),
  the PRE-2022 290 wards (before the 2022 MCD merger and delimitation), labelled that way.
District and state come from district_of(). IDs: gn-<geonameid>, osm-<n|w|r><id>, dlw-<ward no>.
"""
from __future__ import annotations

import io
import json
import logging
import math
import re
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any

from dhuaan.config import DATA_DIR, DOMAIN
from dhuaan.geo.districts import district_of
from dhuaan.model.types import Receptor

log = logging.getLogger("dhuaan.geo.receptors")

RECEPTORS_FILE = DATA_DIR / "receptors.json"
DEMO_FILE = DATA_DIR / "demo_places.json"
GEONAMES_URL = "https://download.geonames.org/export/dump/IN.zip"
WARDS_URL = "https://raw.githubusercontent.com/datameet/Municipal_Spatial_Data/master/Delhi/Delhi_Wards.geojson"
OVERPASS_MIRRORS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)
SCHOOL_QUERY = ('[out:json][timeout:180];(area["ISO3166-2"="IN-PB"];area["ISO3166-2"="IN-HR"];'
                'area["ISO3166-2"="IN-CH"];area["ISO3166-2"="IN-DL"];)->.a;nwr["amenity"="school"](area.a);out center tags;')
SKIP_CODES = {"PPLX", "PPLH", "PPLQ", "PPLW", "PPLCH"}
VILLAGE_STATES = {"Punjab", "Haryana", "Chandigarh"}
BHAWANIGARH = (30.266, 76.04)
ROHINI = (28.735, 77.115)


def _in_domain(lat: float, lon: float) -> bool:
    return DOMAIN["lat_min"] <= lat <= DOMAIN["lat_max"] and DOMAIN["lon_min"] <= lon <= DOMAIN["lon_max"]


def km(a: tuple[float, float], b: tuple[float, float]) -> float:
    k = math.cos(math.radians((a[0] + b[0]) / 2))
    return 111.2 * math.hypot(a[0] - b[0], (a[1] - b[1]) * k)


def title(s: str) -> str:
    return " ".join(w.capitalize() if w.isupper() or w.islower() else w for w in s.split())


# ---------- GeoNames ----------

def parse_geonames(text: str) -> list[dict[str, Any]]:
    """IN.txt rows -> settlement dicts inside DOMAIN (feature class P, minus SKIP_CODES)."""
    out = []
    for line in text.splitlines():
        c = line.split("\t")
        if len(c) < 15 or c[6] != "P" or c[7] in SKIP_CODES:
            continue
        lat, lon = float(c[4]), float(c[5])
        if not _in_domain(lat, lon):
            continue
        out.append({"gid": int(c[0]), "name": c[2] or c[1], "lat": lat, "lon": lon, "code": c[7],
                    "pop": int(c[14] or 0)})
    return out


def kind_for(pop: int, code: str) -> str:
    if pop >= 100_000:
        return "city"
    if pop >= 10_000 or code in ("PPLA", "PPLA2", "PPLC"):
        return "town"
    return "village"


def select_settlements(rows: list[dict[str, Any]], state_of: Any) -> list[dict[str, Any]]:
    """Towns/cities/large villages plus one village per 0.1 deg cell in VILLAGE_STATES."""
    keep = [r for r in rows if r["pop"] >= 2000 or r["code"].startswith("PPLA") or r["code"] == "PPLC"]
    keep.sort(key=lambda r: (-r["pop"], r["gid"]))
    chosen: list[dict[str, Any]] = []
    for r in keep:  # drop near-duplicates (same name within 3 km of a bigger entry)
        if any(c["name"] == r["name"] and km((c["lat"], c["lon"]), (r["lat"], r["lon"])) < 3 for c in chosen):
            continue
        chosen.append(r)
    taken = {r["gid"] for r in chosen}
    occupied = {(int(r["lat"] * 10), int(r["lon"] * 10)) for r in chosen}
    cells: dict[tuple[int, int], dict[str, Any]] = {}
    for r in sorted(rows, key=lambda r: (-r["pop"], r["gid"])):
        cell = (int(r["lat"] * 10), int(r["lon"] * 10))
        if r["gid"] in taken or cell in occupied or cell in cells:
            continue
        if state_of(r["lat"], r["lon"]) in VILLAGE_STATES:
            cells[cell] = r
    return chosen + list(cells.values())


# ---------- OSM schools ----------

def osm_id(e: dict[str, Any]) -> str:
    return f"osm-{e['type'][0]}{e['id']}"


def parse_schools(elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for e in elements:
        tags = e.get("tags") or {}
        name = " ".join((tags.get("name:en") or tags.get("name") or "").split())
        lat = e.get("lat", (e.get("center") or {}).get("lat"))
        lon = e.get("lon", (e.get("center") or {}).get("lon"))
        if not name or lat is None or lon is None or not _in_domain(lat, lon):
            continue
        out.append({"id": osm_id(e), "name": name, "lat": float(lat), "lon": float(lon)})
    return sorted(out, key=lambda s: s["id"])


def thin_schools(schools: list[dict[str, Any]], district_fn: Any, keep_district: str = "Sangrur",
                 cell_deg: float = 0.03) -> list[dict[str, Any]]:
    out, cells = [], set()
    for s in schools:
        if district_fn(s["lat"], s["lon"])[0] == keep_district:
            out.append(s)
            continue
        cell = (math.floor(s["lat"] / cell_deg), math.floor(s["lon"] / cell_deg))
        if cell not in cells:
            cells.add(cell)
            out.append(s)
    return out


def fetch_schools(use_cache: bool = True) -> list[dict[str, Any]]:
    from dhuaan.ingest.common import fetch
    last: Exception | None = None
    for m in OVERPASS_MIRRORS:
        try:
            body = fetch(m, namespace="osm", method="POST", data={"data": SCHOOL_QUERY}, timeout=240,
                         use_cache=use_cache, cache_key="overpass-schools-v1", retries=2)
            return json.loads(body)["elements"]
        except Exception as e:  # try the next mirror
            last = e
            log.warning("Overpass mirror %s failed: %s", m, e)
    raise RuntimeError(f"all Overpass mirrors failed: {last}")


def add_locality(schools: list[dict[str, Any]], places: list[dict[str, Any]], max_km: float = 3.0) -> None:
    """Append ', <nearest place>' to each school name (in place) unless the name already contains it."""
    grid: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for p in places:
        grid[(int(p["lat"] * 20), int(p["lon"] * 20))].append(p)
    for s in schools:
        ci, cj = int(s["lat"] * 20), int(s["lon"] * 20)
        best, bd = None, max_km
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for p in grid.get((ci + di, cj + dj), ()):
                    d = km((s["lat"], s["lon"]), (p["lat"], p["lon"]))
                    if d < bd or (best is not None and d == bd and p["pop"] > best["pop"]):
                        best, bd = p, d
        if best and best["name"].lower() not in s["name"].lower():
            s["name"] = f"{s['name']}, {best['name']}"
        s["locality"] = best["name"] if best else None


# ---------- Delhi wards ----------

def ring_centroid(ring: list[list[float]]) -> tuple[float, float]:
    """Area centroid (lon, lat) of a closed ring."""
    a = cx = cy = 0.0
    for i in range(len(ring) - 1):
        x0, y0 = ring[i][:2]
        x1, y1 = ring[i + 1][:2]
        f = x0 * y1 - x1 * y0
        a += f
        cx += (x0 + x1) * f
        cy += (y0 + y1) * f
    if abs(a) < 1e-12:
        return sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring)
    return cx / (3 * a), cy / (3 * a)


def parse_wards(doc: dict[str, Any]) -> list[dict[str, Any]]:
    out, seen = [], defaultdict(int)
    for f in doc["features"]:
        g = f["geometry"]
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        biggest = max((p[0] for p in polys), key=len)
        lon, lat = ring_centroid(biggest)
        no = re.sub(r"[^A-Za-z0-9]+", "-", str(f["properties"].get("Ward_No", ""))).strip("-").lower() or "x"
        seen[no] += 1
        wid = f"dlw-{no}" if seen[no] == 1 else f"dlw-{no}-{seen[no]}"
        name = title(str(f["properties"].get("Ward_Name", "")).strip())
        out.append({"id": wid, "name": f"{name} (ward {f['properties'].get('Ward_No', '')}, pre-2022)",
                    "lat": lat, "lon": lon, "ward_name": name})
    return out


# ---------- build / load ----------

def _rec(id_: str, name: str, kind: str, lat: float, lon: float, pop: int | None) -> dict[str, Any]:
    d, s = district_of(lat, lon)
    return {"id": id_, "name": name, "kind": kind, "district": d, "state": s, "lat": round(lat, 5),
            "lon": round(lon, 5), "population": pop}


def build(use_cache: bool = True) -> list[dict[str, Any]]:
    from dhuaan.ingest.common import fetch
    zb = fetch(GEONAMES_URL, namespace="geo", timeout=300, use_cache=use_cache)
    rows = parse_geonames(zipfile.ZipFile(io.BytesIO(zb)).read("IN.txt").decode("utf-8"))
    settlements = select_settlements(rows, lambda la, lo: district_of(la, lo)[1])
    recs = [_rec(f"gn-{r['gid']}", r["name"], kind_for(r["pop"], r["code"]), r["lat"], r["lon"], r["pop"] or None)
            for r in settlements]
    schools = thin_schools(parse_schools(fetch_schools(use_cache)), district_of)
    add_locality(schools, [r for r in rows if r["pop"] > 0 or r["code"].startswith("PPL")])
    recs += [_rec(s["id"], s["name"], "school", s["lat"], s["lon"], None) for s in schools]
    wards = parse_wards(json.loads(fetch(WARDS_URL, namespace="geo", timeout=120, use_cache=use_cache)))
    recs += [_rec(w["id"], w["name"], "ward", w["lat"], w["lon"], None) for w in wards]
    recs.sort(key=lambda r: r["id"])
    doc = {"attribution": "GeoNames (CC BY 4.0); OpenStreetMap contributors (ODbL 1.0); datameet Municipal_Spatial_Data "
                          "Delhi wards, pre-2022 boundaries (CC BY-SA 2.5 IN)", "receptors": recs}
    RECEPTORS_FILE.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    write_demo_places(recs, wards)
    return recs


def write_demo_places(recs: list[dict[str, Any]], wards: list[dict[str, Any]]) -> dict[str, Any]:
    by_kind = defaultdict(list)
    for r in recs:
        by_kind[r["kind"]].append(r)
    schools = sorted(by_kind["school"], key=lambda r: km((r["lat"], r["lon"]), BHAWANIGARH))
    gov = [s for s in schools[:10] if "gov" in s["name"].lower() and km((s["lat"], s["lon"]), BHAWANIGARH) < 3]
    school = (gov or schools)[0]
    rohini = [w for w in wards if w["ward_name"].upper() == "ROHINI"] or [w for w in wards if "ROHINI" in w["ward_name"].upper()]
    ward = next(r for r in recs if r["id"] == rohini[0]["id"])
    patiala = min((r for r in recs if r["name"] == "Patiala" and r["kind"] in ("city", "town")),
                  key=lambda r: -(r["population"] or 0))
    demo = {
        "school": {**school, "distance_km_from_bhawanigarh": round(km((school["lat"], school["lon"]), BHAWANIGARH), 2),
                   "note": "real OpenStreetMap school; the principal persona is fictional"},
        "ward": {**ward, "note": "pre-2022 Delhi ward (datameet)"},
        "town": {**patiala, "note": "GeoNames"},
    }
    demo["places"] = [demo["school"], demo["ward"], demo["town"]]  # list form, read by dhuaan.agent.advisory
    DEMO_FILE.write_text(json.dumps(demo, ensure_ascii=False, indent=2), encoding="utf-8")
    return demo


def load_receptors(path: Path = RECEPTORS_FILE) -> list[Receptor]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    return [Receptor(id=r["id"], name=r["name"], kind=r["kind"], district=r["district"], state=r["state"],
                     lat=r["lat"], lon=r["lon"], population=r["population"]) for r in doc["receptors"]]


def load_demo_places(path: Path = DEMO_FILE) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    import collections
    logging.basicConfig(level=logging.INFO)
    recs = build()
    print(f"wrote {len(recs)} receptors to {RECEPTORS_FILE} ({RECEPTORS_FILE.stat().st_size // 1024} KB)")
    print(collections.Counter(r["kind"] for r in recs))
    print(collections.Counter(r["state"] for r in recs).most_common(12))
    print(json.dumps(load_demo_places(), ensure_ascii=False, indent=1))
