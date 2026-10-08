"""GK2A-AMI hourly fire detections (Jethva 2026, NASA GSFC / Morgan State), Zenodo 10.5281/zenodo.20084790, CC BY 4.0.

Files: GK2-AMI_FireHotspotsData_<year>_10-11_<Punjab|Haryana>_India_v1.txt, Oct-Nov, 12:00-18:00 IST.
Columns: y m d hh mm lon lat BTdiff BT3.8 BT11.2 conf. Times are IST (the README says so and hours run 12..18).
No FRP: detections become Fire(sensor="GK2A", frp_mw=None), which the model uses only in "observed" mode.
Confidence flags 1/2/3 -> low/nominal/high. The README recommends flags 2 and 3 for quantitative use and
says flag 1 should be used with caution, so the model input (MIN_CONF) keeps flags >= 2. That choice
follows the data provider's guidance and was made before any backtest result was seen.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable

from dhuaan.ingest.common import fetch, in_domain
from dhuaan.model.types import Fire

RECORD = "20084790"
FILE_URL = "https://zenodo.org/api/records/" + RECORD + "/files/GK2-AMI_FireHotspotsData_{year}_10-11_{state}_India_v1.txt/content"
STATES = ("Punjab", "Haryana")
IST = timezone(timedelta(hours=5, minutes=30))
CONF = {1: "low", 2: "nominal", 3: "high"}
MIN_CONF = 2
CITATION = ("GK2A-AMI hourly fire detections for Punjab and Haryana (Jethva 2026, NASA GSFC / Morgan State Univ.), "
            "Zenodo doi:10.5281/zenodo.20084790, CC BY 4.0")


def parse(text: str, state: str = "") -> list[dict]:
    """Rows -> [{t_ist, lat, lon, conf, state}] (header lines and malformed rows are skipped)."""
    out = []
    for line in text.splitlines():
        p = line.split()
        if len(p) != 11 or not p[0].isdigit():
            continue
        try:
            y, m, d, hh, mm = (int(x) for x in p[:5])
            lon, lat = float(p[5]), float(p[6])
            conf = int(float(p[10]))
            t = datetime(y, m, d, hh, mm, tzinfo=IST)
        except ValueError:
            continue
        out.append({"t_ist": t, "lat": lat, "lon": lon, "conf": conf, "state": state})
    return out


def load_rows(year: int = 2025, states: Iterable[str] = STATES, use_cache: bool | None = True) -> list[dict]:
    rows: list[dict] = []
    for st in states:
        body = fetch(FILE_URL.format(year=year, state=st), namespace="zenodo", timeout=120, use_cache=use_cache)
        rows.extend(parse(body.decode("utf-8", "replace"), st))
    return rows


def to_fires(rows: Iterable[dict], min_conf: int = MIN_CONF) -> list[Fire]:
    """Detections inside DOMAIN with conf >= min_conf, as UTC Fire objects (duplicates across files dropped)."""
    seen: dict[str, Fire] = {}
    for r in rows:
        if r["conf"] < min_conf or not in_domain(r["lat"], r["lon"]):
            continue
        t = r["t_ist"].astimezone(timezone.utc)
        fid = f"GK2A_{t:%Y%m%d%H%M}_{r['lat']:.4f}_{r['lon']:.4f}"
        seen.setdefault(fid, Fire(id=fid, lat=r["lat"], lon=r["lon"], time_utc=t, frp_mw=None, sensor="GK2A",
                                  confidence=CONF.get(r["conf"], "nominal")))
    return sorted(seen.values(), key=lambda f: (f.time_utc, f.id))


def afternoon_share(rows: Iterable[dict], from_hour_ist: int = 16, min_conf: int = 1) -> tuple[float, int, int]:
    """(share, n_late, n_total) of detections in 12:00-18:59 IST whose IST hour is >= from_hour_ist."""
    sel = [r for r in rows if r["conf"] >= min_conf and 12 <= r["t_ist"].hour <= 18]
    late = sum(r["t_ist"].hour >= from_hour_ist for r in sel)
    return (late / len(sel) if sel else float("nan")), late, len(sel)
