"""Per-district afternoon ratio (GK2A late-afternoon detections / VIIRS+MODIS detections, 2025 season) and the
headline afternoon-share fact.

    uv run python -m dhuaan.backtest.ratio      # writes backend/data/afternoon_ratio.json and facts.json

Method (documented in facts.json too):
- Season: 1 Oct - 30 Nov 2025 (the GK2A files cover Oct-Nov). Polar = FIRMS VIIRS S-NPP/NOAA-20/NOAA-21 + MODIS
  (all overpasses), static hotspots masked. GK2A = flags >= 2 (README guidance), IST hour >= 16, i.e. the
  16:00-19:00 IST window the model's "estimated" mode fills.
- Districts by dhuaan.geo.districts.district_of (same names the model uses). GK2A only covers Punjab and
  Haryana, so only their districts get a value; everything else falls back to "_default".
- Shrinkage towards the pooled ratio R: r_d = (G_d + m R) / (V_d + m), m = PRIOR_M polar detections, so a
  district with few detections does not get an extreme ratio; then capped to [CAP_LO, CAP_HI].
- This is a ratio of detection COUNTS from a ~4 km geostationary pixel vs 375 m / 1 km polar pixels, not an
  energy ratio. It is a relative index of how much burning the polar overpasses miss, nothing more.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import date
from typing import Any, Callable, Iterable

from dhuaan.config import DATA_DIR
from dhuaan.ingest.common import iso_z, now_utc
from dhuaan.model.types import POLAR_SENSORS, Fire

from . import gk2a

RATIO_FILE = DATA_DIR / "afternoon_ratio.json"
FACTS_FILE = DATA_DIR / "facts.json"
SEASON = (date(2025, 10, 1), date(2025, 11, 30))
LATE_HOUR_IST = 16
PRIOR_M = 30.0
CAP_LO, CAP_HI = 0.25, 4.0


def season_polar(start: date = SEASON[0], end: date = SEASON[1], use_cache: bool | None = True) -> tuple[list[Fire], int, list]:
    """FIRMS VIIRS+MODIS archive start..end, static hotspots masked -> (fires, n_masked, statuses)."""
    from dhuaan.ingest import firms
    fires, st = firms.fetch_archive(start, end, use_cache=use_cache)
    kept, masked = firms.mask_static(fires)
    return kept, len(masked), st


def compute_ratio(gk: Iterable[Fire], polar: Iterable[Fire], district_of: Callable[[float, float], tuple[str, str]],
                  prior_m: float = PRIOR_M, cap: tuple[float, float] = (CAP_LO, CAP_HI),
                  late_hour_ist: int = LATE_HOUR_IST, states: Iterable[str] = ("Punjab", "Haryana"),
                  ) -> tuple[dict[str, float], list[dict[str, Any]]]:
    """-> ({district: ratio, "_default": pooled}, table rows). Only districts in `states` are scored."""
    states = set(states)
    g: Counter = Counter()
    v: Counter = Counter()
    for f in gk:
        if f.time_utc.astimezone(gk2a.IST).hour >= late_hour_ist:
            d, s = district_of(f.lat, f.lon)
            if s in states:
                g[d] += 1
    for f in polar:
        if f.sensor in POLAR_SENSORS:
            d, s = district_of(f.lat, f.lon)
            if s in states:
                v[d] += 1
    G, V = sum(g.values()), sum(v.values())
    clamp = lambda x: round(min(cap[1], max(cap[0], x)), 3)  # noqa: E731
    pooled = G / V if V else 1.0
    out = {"_default": clamp(pooled)}
    rows = []
    for d in sorted(set(g) | set(v)):
        raw = g[d] / v[d] if v[d] else None
        r = clamp((g[d] + prior_m * pooled) / (v[d] + prior_m))
        out[d] = r
        rows.append({"district": d, "gk2a_late": g[d], "polar": v[d], "raw": None if raw is None else round(raw, 3), "ratio": r})
    return out, rows


def main(argv: list[str] | None = None) -> int:
    from dhuaan.geo.districts import district_of
    rows = gk2a.load_rows(2025)
    share_all, late, n = gk2a.afternoon_share([r for r in rows if r["state"] == "Punjab"], LATE_HOUR_IST, min_conf=1)
    share_23, late23, n23 = gk2a.afternoon_share([r for r in rows if r["state"] == "Punjab"], LATE_HOUR_IST, min_conf=2)
    polar, n_masked, _ = season_polar()
    gk = gk2a.to_fires(rows)
    gk = [f for f in gk if SEASON[0] <= f.time_utc.astimezone(gk2a.IST).date() <= SEASON[1]]
    ratios, table = compute_ratio(gk, polar, district_of)
    RATIO_FILE.write_text(json.dumps(ratios, ensure_ascii=False, indent=1), encoding="utf-8")
    facts = {
        "afternoon_share_2025": round(share_all, 4), "n_detections": n, "n_late": late,
        "definition": "Share of 2025 Punjab GK2A detections (Oct-Nov, 12:00-18:59 IST, all confidence flags) "
                      "whose IST hour is >= 16:00",
        "afternoon_share_2025_conf23": round(share_23, 4), "n_detections_conf23": n23,
        "source": gk2a.CITATION, "generated_utc": iso_z(now_utc()),
        "afternoon_ratio": {
            "file": "afternoon_ratio.json", "season": f"{SEASON[0]}..{SEASON[1]}",
            "method": "r_d = (G_d + m*R)/(V_d + m), G = GK2A flag>=2 detections at >=16:00 IST, V = FIRMS VIIRS+MODIS "
                      f"detections (static hotspots masked, {n_masked} masked), R = pooled G/V, m = {PRIOR_M:g}, "
                      f"capped to [{CAP_LO}, {CAP_HI}]. Count ratio (4 km vs 375 m/1 km pixels), not an energy ratio. "
                      "Only Punjab and Haryana districts (GK2A coverage); others use _default.",
            "n_gk2a": sum(r["gk2a_late"] for r in table), "n_polar": sum(r["polar"] for r in table),
            "districts": table,
        },
    }
    FACTS_FILE.write_text(json.dumps(facts, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Punjab 2025 GK2A: {late}/{n} = {share_all:.1%} at >=16:00 IST (flags 2-3: {late23}/{n23} = {share_23:.1%})")
    print(f"pooled ratio {ratios['_default']}; {len(table)} districts; polar masked {n_masked}")
    for r in sorted(table, key=lambda r: -r["polar"])[:20]:
        print(f"  {r['district']:<22} G={r['gk2a_late']:<5} V={r['polar']:<5} raw={r['raw']}  r={r['ratio']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
