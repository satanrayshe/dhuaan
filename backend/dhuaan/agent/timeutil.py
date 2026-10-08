"""UTC <-> IST helpers. Artifacts are UTC ISO-8601 with Z; people read IST (UTC+5:30)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30), name="IST")


def now_utc() -> datetime:
    """Single clock for the agent package (tests monkeypatch this)."""
    return datetime.now(timezone.utc)


def parse_utc(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def iso_utc(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ist_str(t: datetime | str | None) -> str | None:
    """'2026-10-08 21:30 IST' (None passes through)."""
    if isinstance(t, str):
        t = parse_utc(t)
    if t is None:
        return None
    return t.astimezone(IST).strftime("%Y-%m-%d %H:%M IST")


def hours_between(a: datetime, b: datetime) -> float:
    return (b - a).total_seconds() / 3600.0
