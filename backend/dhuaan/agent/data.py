"""Read-only access to run artifacts (CONTRACTS items 2, 5, 6, 7) with a small in-process TTL cache.

Everything goes through one Store (get_store() by default; tests call use_store()).
"""
from __future__ import annotations

import threading
import time
from typing import Any

from dhuaan.store import Store, get_store

TTL_S = 120.0  # Lambda containers live for minutes; artifacts change hourly at most
_lock = threading.Lock()
_cache: dict[str, tuple[float, Any]] = {}
_store: Store | None = None


def use_store(store: Store | None) -> None:
    """Point the agent at a specific store (None = back to get_store()) and clear the cache."""
    global _store
    _store = store
    clear_cache()


def store() -> Store:
    global _store
    if _store is None:
        _store = get_store()
    return _store


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def _get(key: str) -> Any | None:
    now = time.monotonic()
    with _lock:
        hit = _cache.get(key)
        if hit and hit[0] > now:
            return hit[1]
    val = store().get_json(key)
    with _lock:
        if len(_cache) > 512:
            _cache.clear()
        _cache[key] = (now + TTL_S, val)
    return val


def meta() -> dict | None:
    return _get("latest/meta.json")


def run_id() -> str:
    m = meta() or {}
    return str(m.get("run_id") or "none")


def alpha() -> float:
    m = meta() or {}
    try:
        return float(m.get("alpha", 1.0))
    except (TypeError, ValueError):
        return 1.0


def alpha_for(place: dict | None) -> float:
    """Region-appropriate alpha for a place (meta.alpha_by_region via dhuaan.geo.regions), else the pooled alpha."""
    from dhuaan.geo.regions import alpha_for as _af
    try:
        return _af(meta(), (place or {}).get("district"), (place or {}).get("state"))
    except (TypeError, ValueError):
        return alpha()


def index() -> list[dict]:
    idx = _get("latest/receptors_index.json") or {}
    return idx.get("places", []) if isinstance(idx, dict) else []


def place(place_id: str) -> dict | None:
    if not place_id or "/" in place_id or "\\" in place_id or ".." in place_id:
        return None
    return _get(f"latest/places/{place_id}.json")


def clusters() -> list[dict]:
    c = _get("latest/clusters.json") or {}
    return c.get("clusters", []) if isinstance(c, dict) else []


def cluster(cluster_id: str) -> dict | None:
    return next((c for c in clusters() if c.get("cluster_id") == cluster_id), None)


def advisory(school_id: str) -> dict | None:
    if not school_id or "/" in school_id or "\\" in school_id or ".." in school_id:
        return None
    return _get(f"latest/advisories/{school_id}.json")


def _norm(s: str) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in s).split())


def search(query: str, limit: int = 10) -> list[dict]:
    """Rank index entries: exact name > name prefix > word prefix > substring > district/state match; ties by peak smoke."""
    q = _norm(query or "")
    if not q:
        return []
    scored: list[tuple[float, dict]] = []
    for p in index():
        name = _norm(p.get("name", ""))
        district = _norm(p.get("district", ""))
        words = name.split()
        if name == q or p.get("id") == query:
            s = 100.0
        elif name.startswith(q):
            s = 80.0
        elif any(w.startswith(q) for w in words):
            s = 60.0
        elif q in name:
            s = 50.0
        elif all(any(w.startswith(t) for w in words) for t in q.split()):
            s = 45.0
        elif q == district or district.startswith(q):
            s = 30.0
        elif q == _norm(p.get("state", "")):
            s = 10.0
        else:
            continue
        s += {"city": 3, "town": 2, "school": 1}.get(p.get("kind", ""), 0)
        scored.append((s + min(float(p.get("peak_smoke") or 0), 999) / 1e4, p))
    scored.sort(key=lambda x: -x[0])
    return [p for _, p in scored[: max(1, min(limit, 50))]]
