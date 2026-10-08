"""Persistent (static) hotspots: likely industrial / brick-kiln / flare sources, not crop fires.

Rule (fixed before looking at the result): FIRMS VIIRS (S-NPP, NOAA-20, NOAA-21) detections from the
off-season 1 Jan - 31 Aug 2025 inside DOMAIN, binned to 0.01 deg cells (~1 km); a cell detected on
>= MIN_DAYS distinct UTC days is a static hotspot. Live detections within MASK_RADIUS_KM of a hotspot
cell centre are dropped by dhuaan.ingest.firms.mask_static().

    uv run python -m dhuaan.backtest.hotspots
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import date
from typing import Any, Iterable

from dhuaan.config import DATA_DIR
from dhuaan.ingest.common import iso_z, now_utc
from dhuaan.model.types import Fire

OUT_FILE = DATA_DIR / "static_hotspots.json"
CELL_DEG = 0.01
MIN_DAYS = 8
START, END = date(2025, 1, 1), date(2025, 8, 31)
SENSORS = ("VIIRS_SNPP", "VIIRS_NOAA20", "VIIRS_NOAA21")


def cell_of(lat: float, lon: float, step: float = CELL_DEG) -> tuple[int, int]:
    return math.floor(lat / step + 1e-9), math.floor(lon / step + 1e-9)


def find_hotspots(fires: Iterable[Fire], min_days: int = MIN_DAYS, step: float = CELL_DEG) -> list[dict[str, Any]]:
    """Cells with detections on >= min_days distinct UTC days -> [{lat, lon, days, n, months}] (cell centres)."""
    days: dict[tuple[int, int], set] = defaultdict(set)
    n: dict[tuple[int, int], int] = defaultdict(int)
    for f in fires:
        c = cell_of(f.lat, f.lon, step)
        days[c].add(f.time_utc.date())
        n[c] += 1
    out = []
    for c, ds in days.items():
        if len(ds) >= min_days:
            out.append({"lat": round((c[0] + 0.5) * step, 3), "lon": round((c[1] + 0.5) * step, 3),
                        "days": len(ds), "n": n[c], "months": len({(d.year, d.month) for d in ds})})
    return sorted(out, key=lambda h: (-h["days"], h["lat"], h["lon"]))


def build(use_cache: bool = True) -> dict[str, Any]:
    from dhuaan.geo.districts import district_of
    from dhuaan.ingest import firms
    fires, statuses = firms.fetch_archive(START, END, sensors=SENSORS, use_cache=use_cache)
    hs = find_hotspots(fires)
    for h in hs:
        h["district"], h["state"] = district_of(h["lat"], h["lon"])
    return {
        "source": f"NASA FIRMS VIIRS {'/'.join(SENSORS)} archive {START}..{END} (off-season), DOMAIN",
        "rule": f"0.01 deg cell detected on >= {MIN_DAYS} distinct UTC days",
        "mask_radius_km": 1.0, "cell_deg": CELL_DEG, "generated_utc": iso_z(now_utc()),
        "n_input_detections": len(fires), "fetch": [{k: s[k] for k in ("name", "ok", "count", "note")} for s in statuses],
        "n_hotspots": len(hs), "hotspots": hs,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="dhuaan.backtest.hotspots")
    ap.add_argument("--no-cache", action="store_true")
    a = ap.parse_args(argv)
    doc = build(use_cache=not a.no_cache)
    OUT_FILE.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    by: dict[str, int] = defaultdict(int)
    for h in doc["hotspots"]:
        by[f"{h['district']}, {h['state']}"] += 1
    print(f"{doc['n_input_detections']} detections -> {doc['n_hotspots']} static hotspots -> {OUT_FILE}")
    for k, v in sorted(by.items(), key=lambda kv: -kv[1])[:25]:
        print(f"  {v:4d}  {k}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
