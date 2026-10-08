"""Lightweight validators for every artifact in docs/CONTRACTS.md (no external deps).

Each validate_* raises SchemaError (a ValueError) with a path to the offending field.
`validate_artifacts(dict)` dispatches on filename ("places/<id>.json" etc.) and skips keys
starting with "_". Other components use these in their tests.
"""
from __future__ import annotations

import base64
import math
import re
from typing import Any

ISO_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")
N_HOURS = 97
NAQI = ("good", "satisfactory", "moderate", "poor", "very_poor", "severe")
SENSORS = {"VIIRS_SNPP", "VIIRS_NOAA20", "VIIRS_NOAA21", "MODIS", "MSG_IODC", "GK2A"}
KINDS = {"village", "town", "city", "school", "ward"}


class SchemaError(ValueError):
    pass


def _fail(path: str, msg: str) -> None:
    raise SchemaError(f"{path}: {msg}")


def _req(obj: Any, keys: list[str] | tuple[str, ...], path: str) -> None:
    if not isinstance(obj, dict):
        _fail(path, f"expected object, got {type(obj).__name__}")
    missing = [k for k in keys if k not in obj]
    if missing:
        _fail(path, f"missing keys {missing}")


def _num(v: Any, path: str, *, nullable: bool = False, lo: float | None = None, hi: float | None = None) -> None:
    if v is None and nullable:
        return
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        _fail(path, f"expected finite number, got {v!r}")
    if lo is not None and v < lo:
        _fail(path, f"{v} < {lo}")
    if hi is not None and v > hi:
        _fail(path, f"{v} > {hi}")


def _str(v: Any, path: str, *, nullable: bool = False) -> None:
    if v is None and nullable:
        return
    if not isinstance(v, str):
        _fail(path, f"expected string, got {v!r}")


def _time(v: Any, path: str, *, nullable: bool = False) -> None:
    if v is None and nullable:
        return
    if not isinstance(v, str) or not ISO_Z.match(v):
        _fail(path, f"expected UTC ISO-8601 with Z, got {v!r}")


def _list(v: Any, path: str, n: int | None = None) -> list:
    if not isinstance(v, list):
        _fail(path, f"expected list, got {type(v).__name__}")
    if n is not None and len(v) != n:
        _fail(path, f"expected {n} items, got {len(v)}")
    return v


def _lonlat(lon: Any, lat: Any, path: str) -> None:
    _num(lon, path + ".lon", lo=-180, hi=180)
    _num(lat, path + ".lat", lo=-90, hi=90)


def validate_fires(obj: Any, path: str = "fires.geojson") -> None:
    _req(obj, ["type", "features"], path)
    if obj["type"] != "FeatureCollection":
        _fail(path, "type must be FeatureCollection")
    for i, f in enumerate(_list(obj["features"], path + ".features")):
        fp = f"{path}.features[{i}]"
        _req(f, ["type", "geometry", "properties"], fp)
        g = f["geometry"]
        _req(g, ["type", "coordinates"], fp + ".geometry")
        if g["type"] != "Point":
            _fail(fp, "geometry must be Point")
        c = _list(g["coordinates"], fp + ".geometry.coordinates", 2)
        _lonlat(c[0], c[1], fp)
        pr = f["properties"]
        _req(pr, ["id", "sensor", "frp_mw", "confidence", "acq_utc", "cluster_id", "afternoon"], fp + ".properties")
        _str(pr["id"], fp + ".id")
        if pr["sensor"] not in SENSORS:
            _fail(fp + ".sensor", f"unknown sensor {pr['sensor']!r}")
        _num(pr["frp_mw"], fp + ".frp_mw", nullable=True, lo=0)
        if pr["confidence"] not in ("low", "nominal", "high"):
            _fail(fp + ".confidence", f"bad confidence {pr['confidence']!r}")
        _time(pr["acq_utc"], fp + ".acq_utc")
        _str(pr["cluster_id"], fp + ".cluster_id", nullable=True)
        if not isinstance(pr["afternoon"], bool):
            _fail(fp + ".afternoon", "expected bool")


def validate_clusters(obj: Any, path: str = "clusters.json") -> None:
    _req(obj, ["t0_utc", "clusters"], path)
    _time(obj["t0_utc"], path + ".t0_utc")
    last_rank = 0
    share = 0.0
    for i, c in enumerate(_list(obj["clusters"], path + ".clusters")):
        cp = f"{path}.clusters[{i}]"
        _req(c, ["cluster_id", "lat", "lon", "n_detections", "frp_sum_mw", "first_seen_utc", "last_seen_utc",
                 "district", "state", "nearest_place", "rank", "exposure_person_hours", "exposure_share",
                 "downwind"], cp)
        _str(c["cluster_id"], cp + ".cluster_id")
        _lonlat(c["lon"], c["lat"], cp)
        _num(c["n_detections"], cp + ".n_detections", lo=1)
        _num(c["frp_sum_mw"], cp + ".frp_sum_mw", lo=0)
        _time(c["first_seen_utc"], cp + ".first_seen_utc")
        _time(c["last_seen_utc"], cp + ".last_seen_utc")
        _str(c["district"], cp + ".district")
        _str(c["state"], cp + ".state")
        _str(c["nearest_place"], cp + ".nearest_place", nullable=True)
        _num(c["rank"], cp + ".rank", lo=1)
        if c["rank"] <= last_rank:
            _fail(cp + ".rank", "clusters must be sorted by ascending unique rank")
        last_rank = c["rank"]
        _num(c["exposure_person_hours"], cp + ".exposure_person_hours", lo=0)
        _num(c["exposure_share"], cp + ".exposure_share", lo=0, hi=1)
        share += c["exposure_share"]
        for j, d in enumerate(_list(c["downwind"], cp + ".downwind")):
            dp = f"{cp}.downwind[{j}]"
            _req(d, ["place_id", "name", "kind", "arrival_utc", "peak_utc", "peak_smoke"], dp)
            _str(d["place_id"], dp + ".place_id")
            _time(d["arrival_utc"], dp + ".arrival_utc", nullable=True)
            _time(d["peak_utc"], dp + ".peak_utc")
            _num(d["peak_smoke"], dp + ".peak_smoke", lo=0)
        if len(c["downwind"]) > 5:
            _fail(cp + ".downwind", "at most 5 entries")
    if share > 1.0 + 1e-3:
        _fail(path, f"exposure shares sum to {share} > 1")


def validate_trips(obj: Any, path: str = "trips.json") -> None:
    _req(obj, ["t0_utc", "step_minutes", "trips"], path)
    _time(obj["t0_utc"], path + ".t0_utc")
    _num(obj["step_minutes"], path + ".step_minutes", lo=1)
    trips = _list(obj["trips"], path + ".trips")
    if len(trips) > 6000:
        _fail(path + ".trips", f"{len(trips)} > 6000 trips")
    for i, t in enumerate(trips):
        tp = f"{path}.trips[{i}]"
        _req(t, ["cluster_id", "path", "ts"], tp)
        pts = _list(t["path"], tp + ".path")
        ts = _list(t["ts"], tp + ".ts", len(pts))
        for j, pt in enumerate(pts):
            if not isinstance(pt, list) or len(pt) != 2:
                _fail(f"{tp}.path[{j}]", "expected [lon, lat]")
            _lonlat(pt[0], pt[1], f"{tp}.path[{j}]")
        for j in range(1, len(ts)):
            if not ts[j] > ts[j - 1]:
                _fail(f"{tp}.ts[{j}]", "timestamps must increase")
        if ts:
            _num(ts[0], tp + ".ts[0]", lo=0)


def validate_grid(obj: Any, path: str = "grid.json") -> None:
    _req(obj, ["lon0", "lat0", "dlon", "dlat", "nx", "ny", "t0_utc", "hours", "scale", "frames"], path)
    for k in ("lon0", "lat0"):
        _num(obj[k], f"{path}.{k}")
    for k in ("dlon", "dlat", "scale"):
        _num(obj[k], f"{path}.{k}", lo=1e-12)
    _time(obj["t0_utc"], path + ".t0_utc")
    if obj["hours"] != N_HOURS:
        _fail(path + ".hours", f"expected {N_HOURS}")
    n = int(obj["nx"]) * int(obj["ny"])
    for i, fr in enumerate(_list(obj["frames"], path + ".frames", N_HOURS)):
        try:
            raw = base64.b64decode(fr, validate=True)
        except Exception as e:  # noqa: BLE001
            _fail(f"{path}.frames[{i}]", f"bad base64: {e}")
        if len(raw) != n:
            _fail(f"{path}.frames[{i}]", f"decoded {len(raw)} bytes, expected nx*ny={n}")


def _place_base(p: Any, pp: str) -> None:
    _str(p["id"], pp + ".id")
    _str(p["name"], pp + ".name")
    if p["kind"] not in KINDS:
        _fail(pp + ".kind", f"unknown kind {p['kind']!r}")
    _str(p["district"], pp + ".district")
    _str(p["state"], pp + ".state")
    _lonlat(p["lon"], p["lat"], pp)


def validate_receptors_index(obj: Any, path: str = "receptors_index.json", max_bytes: int | None = None) -> None:
    _req(obj, ["t0_utc", "places"], path)
    _time(obj["t0_utc"], path + ".t0_utc")
    for i, p in enumerate(_list(obj["places"], path + ".places")):
        pp = f"{path}.places[{i}]"
        _req(p, ["id", "name", "kind", "district", "state", "lat", "lon", "peak_smoke", "peak_utc", "arrival_utc"], pp)
        _place_base(p, pp)
        _num(p["peak_smoke"], pp + ".peak_smoke", lo=0)
        _time(p["peak_utc"], pp + ".peak_utc")
        _time(p["arrival_utc"], pp + ".arrival_utc", nullable=True)
    if max_bytes is not None:
        import json
        size = len(json.dumps(obj, separators=(",", ":")).encode("utf-8"))
        if size > max_bytes:
            _fail(path, f"{size} bytes > {max_bytes}")


def validate_place(obj: Any, path: str = "places/<id>.json") -> None:
    _req(obj, ["id", "name", "kind", "district", "state", "lat", "lon", "t0_utc", "series", "p10", "p90",
               "arrival_utc", "arrival_window", "peak_utc", "peak_smoke", "attribution", "top_clusters"], path)
    _place_base(obj, path)
    _time(obj["t0_utc"], path + ".t0_utc")
    for k in ("series", "p10", "p90"):
        for i, v in enumerate(_list(obj[k], f"{path}.{k}", N_HOURS)):
            _num(v, f"{path}.{k}[{i}]", lo=0)
    for i, (a, b) in enumerate(zip(obj["p10"], obj["p90"])):
        if a > b + 0.011:
            _fail(f"{path}.p10[{i}]", "p10 > p90")
    _time(obj["arrival_utc"], path + ".arrival_utc", nullable=True)
    w = obj["arrival_window"]
    if w is not None:
        w = _list(w, path + ".arrival_window", 2)
        _time(w[0], path + ".arrival_window[0]")
        _time(w[1], path + ".arrival_window[1]")
        if w[0] > w[1]:
            _fail(path + ".arrival_window", "earliest after latest")
    _time(obj["peak_utc"], path + ".peak_utc")
    _num(obj["peak_smoke"], path + ".peak_smoke", lo=0)
    tot = 0.0
    for i, a in enumerate(_list(obj["attribution"], path + ".attribution")):
        _req(a, ["district", "share"], f"{path}.attribution[{i}]")
        _str(a["district"], f"{path}.attribution[{i}].district")
        _num(a["share"], f"{path}.attribution[{i}].share", lo=0, hi=1)
        tot += a["share"]
    if obj["attribution"] and abs(tot - 1.0) > 1e-3:
        _fail(path + ".attribution", f"shares sum to {tot}, expected 1")
    if len(obj["attribution"]) > 6:
        _fail(path + ".attribution", "top 5 plus Other at most")
    for i, c in enumerate(_list(obj["top_clusters"], path + ".top_clusters")):
        _req(c, ["cluster_id", "share"], f"{path}.top_clusters[{i}]")
        _num(c["share"], f"{path}.top_clusters[{i}].share", lo=0, hi=1)


def validate_meta(obj: Any, path: str = "meta.json") -> None:
    _req(obj, ["run_id", "t0_utc", "generated_utc", "model_version", "members", "afternoon_mode", "alpha",
               "calibrated", "arrival_threshold", "scale", "domain", "sources"], path)
    _str(obj["run_id"], path + ".run_id")
    _time(obj["t0_utc"], path + ".t0_utc")
    _time(obj["generated_utc"], path + ".generated_utc")
    _num(obj["members"], path + ".members", lo=1)
    if obj["afternoon_mode"] not in ("none", "estimated", "observed"):
        _fail(path + ".afternoon_mode", "must be none|estimated|observed")
    _num(obj["alpha"], path + ".alpha", lo=0)
    if not isinstance(obj["calibrated"], bool):
        _fail(path + ".calibrated", "expected bool")
    _num(obj["arrival_threshold"], path + ".arrival_threshold", lo=0)
    _num(obj["scale"], path + ".scale", lo=0)
    for i, s in enumerate(_list(obj["sources"], path + ".sources")):
        _req(s, ["name", "fetched_utc", "latest_obs_utc", "count", "ok", "note"], f"{path}.sources[{i}]")


def validate_advisory(obj: Any, path: str = "advisories/<school_id>.json") -> None:
    _req(obj, ["school_id", "date_ist", "plan", "notice", "grounding", "model"], path)
    for i, h in enumerate(_list(obj["plan"], path + ".plan")):
        hp = f"{path}.plan[{i}]"
        _req(h, ["hour_ist", "est_pm25", "category", "outdoor"], hp)
        _num(h["est_pm25"], hp + ".est_pm25", lo=0)
        if h["category"] not in NAQI:
            _fail(hp + ".category", f"bad NAQI category {h['category']!r}")
        if h["outdoor"] not in ("ok", "limit", "indoors"):
            _fail(hp + ".outdoor", f"bad outdoor {h['outdoor']!r}")
    _req(obj["notice"], ["en", "hi", "pa"], path + ".notice")
    _req(obj["grounding"], ["verified", "total"], path + ".grounding")


def validate_backtest(obj: Any, path: str = "backtest.json") -> None:
    _req(obj, ["window", "met_source", "stations", "metrics", "calibration", "notes"], path)
    for i, s in enumerate(_list(obj["stations"], path + ".stations")):
        _req(s, ["id", "name", "lat", "lon", "series"], f"{path}.stations[{i}]")


_DISPATCH = {
    "fires.geojson": validate_fires,
    "clusters.json": validate_clusters,
    "trips.json": validate_trips,
    "grid.json": validate_grid,
    "receptors_index.json": validate_receptors_index,
    "meta.json": validate_meta,
    "backtest.json": validate_backtest,
}


def validate_artifact(name: str, obj: Any) -> None:
    """Validate one artifact; `name` may carry a "latest/" or "runs/<run_id>/" prefix."""
    base = name
    if base.startswith("latest/"):
        base = base[len("latest/"):]
    elif base.startswith("runs/") and base.count("/") >= 2:
        base = base.split("/", 2)[2]
    if base.startswith("places/"):
        return validate_place(obj, base)
    if base.startswith("advisories/"):
        return validate_advisory(obj, base)
    fn = _DISPATCH.get(base)
    if fn is None:
        _fail(name, "unknown artifact name")
    fn(obj, base)


def validate_artifacts(arts: dict[str, Any]) -> None:
    """Validate a whole model output dict (keys starting with '_' are skipped) and the
    cross-file references (cluster ids, place files listed in the index)."""
    for name, obj in arts.items():
        if name.startswith("_"):
            continue
        validate_artifact(name, obj)
    if "clusters.json" in arts:
        ids = {c["cluster_id"] for c in arts["clusters.json"]["clusters"]}
        for f in arts.get("fires.geojson", {}).get("features", []):
            cid = f["properties"]["cluster_id"]
            if cid is not None and cid not in ids:
                _fail("fires.geojson", f"cluster_id {cid} not in clusters.json")
        for t in arts.get("trips.json", {}).get("trips", []):
            if t["cluster_id"] not in ids:
                _fail("trips.json", f"cluster_id {t['cluster_id']} not in clusters.json")
    if "receptors_index.json" in arts:
        for p in arts["receptors_index.json"]["places"]:
            if f"places/{p['id']}.json" not in arts:
                _fail("receptors_index.json", f"no places/{p['id']}.json")
