"""Calibration regions, shared by the pipeline, agent and (mirrored in web/src/lib/regions.ts) the web app.

The backtest's exploratory regional calibration fits one alpha per region:
- "delhi_ncr":      NCT of Delhi plus the adjacent urban NCR districts (DPCC stations calibrate it)
- "punjab_haryana": the rest of Punjab, Haryana and Chandigarh (PPCB stations calibrate it)
- "_default":       anything else (west UP, north Rajasthan, hills): the pooled pre-registered alpha
Keep NCR_DISTRICTS identical to the web mirror.
"""
from __future__ import annotations

from typing import Any, Mapping

REGIONS = ("delhi_ncr", "punjab_haryana")
DEFAULT = "_default"
# District names as they appear in data/districts.geojson (old and new spellings both listed).
NCR_DISTRICTS = frozenset({
    "Gurgaon", "Gurugram", "Faridabad", "Sonipat", "Jhajjar", "Palwal",       # Haryana
    "Ghaziabad", "Gautam Buddha Nagar", "Baghpat",                           # Uttar Pradesh
})
DELHI_STATES = frozenset({"Delhi", "NCT of Delhi"})
PUNJAB_HARYANA_STATES = frozenset({"Punjab", "Haryana", "Chandigarh"})
REGION_LABEL = {"delhi_ncr": "Delhi/NCR", "punjab_haryana": "Punjab/Haryana", DEFAULT: "pooled"}
EST_LABEL = "est. smoke PM2.5 (provisional calibration)"


def region_of(district: str | None, state: str | None) -> str:
    if state in DELHI_STATES or district in NCR_DISTRICTS:
        return "delhi_ncr"
    if state in PUNJAB_HARYANA_STATES:
        return "punjab_haryana"
    return DEFAULT


def station_region(region: str) -> str:
    """Backtest station 'region' field ("Delhi"/"Punjab"/"Haryana") -> calibration region."""
    return "delhi_ncr" if region in DELHI_STATES else "punjab_haryana"


def alpha_for(meta: Mapping[str, Any] | None, district: str | None, state: str | None) -> float:
    """Region-appropriate alpha from meta.alpha_by_region, falling back to the pooled meta.alpha (then 1.0)."""
    meta = meta or {}
    pooled = float(meta.get("alpha") or 1.0)
    by = meta.get("alpha_by_region") or {}
    v = by.get(region_of(district, state)) or by.get(DEFAULT)
    return float(v) if v else pooled
