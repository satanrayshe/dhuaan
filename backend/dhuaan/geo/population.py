"""Population on the 0.1 deg output grid (66 x 48 cells, row 0 = south), persons per cell.

Source: Meta/CIESIN High Resolution Settlement Layer v1.5 (CC BY 4.0), AWS Open Data
s3://dataforgood-fb-data/hrsl-cogs/hrsl_general/v1.5/cog_globallat_{30,20}_lon_70_general-v1.5.2.tif.
Tile "lat_30_lon_70" spans lon 70..80, lat 30..40 (origin = top-left); "lat_20" spans lat 20..30. Pixels are
1 arcsec (~30 m) float64 person counts, NaN where nobody lives, 256 x 256 deflate tiles, no predictor.

rasterio/GDAL is blocked on the dev machine (Windows Application Control) and is heavy for Lambda anyway, so
this module carries a ~100-line BigTIFF/COG reader: parse the first IFD, then HTTP range-read only the
full-resolution tiles that cover the output grid (one request per run of adjacent tiles), inflate with zlib
and sum pixel counts into 0.1 deg cells. Full resolution, not overviews: overview pixels are resampled
values, and summing them would not conserve persons.

Build once with `python -m dhuaan.geo.population` (~60 MB of range reads, cached under settings.cache_dir);
the result is committed as backend/data/population_0p1.json. load_population() -> np.ndarray (48, 66).
"""
from __future__ import annotations

import json
import logging
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from dhuaan.config import DATA_DIR

log = logging.getLogger("dhuaan.geo.population")

POP_FILE = DATA_DIR / "population_0p1.json"
LON0, LAT0, DLON, DLAT, NX, NY = 72.5, 28.0, 0.1, 0.1, 66, 48
HRSL = "https://dataforgood-fb-data.s3.amazonaws.com/hrsl-cogs/hrsl_general/v1.5/"
TILES = {"cog_globallat_30_lon_70_general-v1.5.2.tif": (30.0, 40.0),
         "cog_globallat_20_lon_70_general-v1.5.2.tif": (20.0, 30.0)}

_TYPES = {1: "B", 2: "s", 3: "H", 4: "I", 5: "II", 11: "f", 12: "d", 16: "Q", 17: "q"}
_SIZES = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 11: 4, 12: 8, 16: 8, 17: 8}


@dataclass
class CogLevel:
    width: int
    height: int
    tile_w: int
    tile_h: int
    offsets: list[int]
    counts: list[int]
    compression: int
    predictor: int
    bits: int
    sample_format: int
    left: float
    top: float
    res_x: float
    res_y: float


def _range(url: str, start: int, end: int) -> bytes:
    """Bytes [start, end] inclusive (cached)."""
    from dhuaan.ingest.common import fetch
    return fetch(url, namespace="hrsl", headers={"Range": f"bytes={start}-{end}"}, ok_status=(206, 200),
                 cache_key=f"{url}#{start}-{end}", use_cache=True, timeout=120)


def read_first_ifd(url: str, reader: Any = _range) -> CogLevel:
    """Parse the full-resolution IFD of a (Big)TIFF via range reads."""
    head = reader(url, 0, 65535)
    e = "<" if head[:2] == b"II" else ">"
    big = struct.unpack(e + "H", head[2:4])[0] == 43
    off = struct.unpack(e + "Q", head[8:16])[0] if big else struct.unpack(e + "I", head[4:8])[0]
    buf = head

    def need(a: int, n: int) -> bytes:
        nonlocal buf
        if a + n > len(buf):
            buf = buf + reader(url, len(buf), max(a + n, len(buf) + 65536) - 1)
        return buf[a:a + n]

    cnt = struct.unpack(e + ("Q" if big else "H"), need(off, 8 if big else 2))[0]
    es, p = (20, off + 8) if big else (12, off + 2)
    tags: dict[int, tuple] = {}
    for i in range(cnt):
        ent = need(p + i * es, es)
        if big:
            tag, typ, c = struct.unpack(e + "HHQ", ent[:12]); vo = ent[12:20]
        else:
            tag, typ, c = struct.unpack(e + "HHI", ent[:8]); vo = ent[8:12]
        size = _SIZES.get(typ, 1) * c
        raw = vo[:size] if size <= len(vo) else need(struct.unpack(e + ("Q" if big else "I"), vo)[0], size)
        f = _TYPES.get(typ)
        if f and typ != 2:
            k = c * (2 if typ == 5 else 1)
            tags[tag] = struct.unpack(e + (f.replace("II", "I") * k if typ == 5 else f * c), raw[:size])
        else:
            tags[tag] = (raw,)
    scale, tie = tags[33550], tags[33922]
    return CogLevel(width=tags[256][0], height=tags[257][0], tile_w=tags[322][0], tile_h=tags[323][0],
                    offsets=list(tags[324]), counts=list(tags[325]), compression=tags.get(259, (1,))[0],
                    predictor=tags.get(317, (1,))[0], bits=tags[258][0], sample_format=tags.get(339, (1,))[0],
                    left=tie[3] - tie[0] * scale[0], top=tie[4] + tie[1] * scale[1], res_x=scale[0], res_y=scale[1])


def _decode(level: CogLevel, data: bytes) -> np.ndarray:
    if level.compression == 8 or level.compression == 32946:
        data = zlib.decompress(data)
    elif level.compression != 1:
        raise NotImplementedError(f"TIFF compression {level.compression}")
    if level.predictor != 1:
        raise NotImplementedError(f"TIFF predictor {level.predictor}")
    dt = {(3, 64): "<f8", (3, 32): "<f4"}[(level.sample_format, level.bits)]
    return np.frombuffer(data, dtype=dt).reshape(level.tile_h, level.tile_w)


def aggregate(url: str, level: CogLevel, out: np.ndarray, reader: Any = _range,
              band: tuple[float, float] = (-90.0, 90.0)) -> float:
    """Add HRSL persons from one COG into `out` (NY, NX), using only pixel centres with band[0] <= lat < band[1]
    (adjacent HRSL tiles overlap by ~32 rows, so each tile is clipped to its nominal 10 deg band).
    Returns persons added."""
    lat_top_grid, lon_right_grid = LAT0 + NY * DLAT, LON0 + NX * DLON
    tiles_x = (level.width + level.tile_w - 1) // level.tile_w
    tiles_y = (level.height + level.tile_h - 1) // level.tile_h
    r0 = max(0, int((level.top - lat_top_grid) / level.res_y) // level.tile_h)
    r1 = min(tiles_y - 1, int((level.top - LAT0) / level.res_y) // level.tile_h)
    c0 = max(0, int((LON0 - level.left) / level.res_x) // level.tile_w)
    c1 = min(tiles_x - 1, int((lon_right_grid - level.left) / level.res_x) // level.tile_w)
    if r1 < r0 or c1 < c0:
        return 0.0
    added = 0.0
    th, tw = level.tile_h, level.tile_w
    for tr in range(r0, r1 + 1):
        idx = [tr * tiles_x + tc for tc in range(c0, c1 + 1)]
        live = [(k, level.offsets[k], level.counts[k]) for k in idx if level.counts[k] > 0]
        if not live:
            continue
        # one range request per run of byte-adjacent tiles
        runs: list[list[tuple[int, int, int]]] = [[live[0]]]
        for t in live[1:]:
            prev = runs[-1][-1]
            if t[1] == prev[1] + prev[2] or 0 < t[1] - (prev[1] + prev[2]) < 4096:
                runs[-1].append(t)
            else:
                runs.append([t])
        rows = level.top - (tr * th + np.arange(th) + 0.5) * level.res_y          # pixel-centre lats
        ci = np.floor((rows - LAT0) / DLAT).astype(int)
        ci[(rows < band[0]) | (rows >= band[1])] = -1
        for run in runs:
            a, b = run[0][1], run[-1][1] + run[-1][2] - 1
            blob = reader(url, a, b)
            for k, o, n in run:
                arr = _decode(level, blob[o - a:o - a + n])
                tc = k % tiles_x
                cols = level.left + (tc * tw + np.arange(tw) + 0.5) * level.res_x
                cj = np.floor((cols - LON0) / DLON).astype(int)
                okr, okc = (ci >= 0) & (ci < NY), (cj >= 0) & (cj < NX)
                if not okr.any() or not okc.any():
                    continue
                sub = np.nan_to_num(arr[np.ix_(okr, okc)], nan=0.0)
                sub[sub < 0] = 0.0
                if not sub.any():
                    continue
                cell = (ci[okr][:, None] * NX + cj[okc][None, :]).ravel()
                s = np.bincount(cell, weights=sub.ravel(), minlength=NX * NY)
                out += s.reshape(NY, NX)
                added += float(sub.sum())
    return added


def build_hrsl() -> np.ndarray:
    out = np.zeros((NY, NX), dtype=np.float64)
    for name, band in TILES.items():
        url = HRSL + name
        lvl = read_first_ifd(url)
        n = aggregate(url, lvl, out, band=band)
        log.info("HRSL %s: +%.0f persons", name, n)
    return out


def write_population(grid: np.ndarray, source: str, path: Path = POP_FILE) -> None:
    doc = {"lon0": LON0, "lat0": LAT0, "dlon": DLON, "dlat": DLAT, "nx": NX, "ny": NY, "row0": "south",
           "units": "persons per cell", "source": source, "total": int(round(float(grid.sum()))),
           "rows": [[int(round(v)) for v in row] for row in grid]}
    path.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")


def load_population(path: Path = POP_FILE) -> np.ndarray:
    """(48, 66) float64 persons per 0.1 deg cell, row 0 = south."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    a = np.asarray(doc["rows"], dtype=np.float64)
    if a.shape != (NY, NX):
        raise ValueError(f"population grid shape {a.shape} != {(NY, NX)}")
    return a


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    g = build_hrsl()
    write_population(g, "Meta HRSL v1.5.2 (CC BY 4.0), full-resolution tiles summed to 0.1 deg")
    print(f"total {g.sum():,.0f} persons; max cell {g.max():,.0f}; wrote {POP_FILE}")
