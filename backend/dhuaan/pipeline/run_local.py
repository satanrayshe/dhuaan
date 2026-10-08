"""Run the whole pipeline locally: ingest -> model -> artifacts in the store (backend/out by default).

    uv run python -m dhuaan.pipeline.run_local [--members 5] [--afternoon-mode estimated|observed|none]
                                               [--no-lsasaf] [--use-cache] [--t0 2026-10-08T06:00:00Z]
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from collections import Counter

from dhuaan.ingest.common import iso_z, now_utc, set_use_cache
from dhuaan.pipeline.core import floor_hour, ingest, make_run_id, parse_iso, publish, save_raw
from dhuaan.store import get_store


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="dhuaan.pipeline.run_local")
    ap.add_argument("--members", type=int, default=5)
    ap.add_argument("--afternoon-mode", choices=("estimated", "observed", "none"), default="estimated")
    ap.add_argument("--no-lsasaf", action="store_true", help="skip LSA SAF Meteosat-IODC fires")
    ap.add_argument("--use-cache", action="store_true", help="reuse cached API responses (dev)")
    ap.add_argument("--t0", help="override run time (UTC ISO); default: now floored to the hour")
    ap.add_argument("--no-openaq", action="store_true", help="skip the OpenAQ station status check")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    if a.use_cache:
        set_use_cache(True)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    t0 = floor_hour(parse_iso(a.t0) if a.t0 else now_utc())
    run_id = make_run_id(t0)
    store = get_store()
    t_start = time.perf_counter()
    print(f"run {run_id}  t0={iso_z(t0)}  store={type(store).__name__}")
    fires, met, sources = ingest(t0, use_lsasaf=not a.no_lsasaf, with_openaq=not a.no_openaq)
    save_raw(store, run_id, t0, fires, met, sources)
    t_ing = time.perf_counter() - t_start
    for s in sources:
        print(f"  {'ok ' if s['ok'] else 'ERR'} {s['name']:<34} n={s['count']:<5} latest={s['latest_obs_utc']}  {s['note']}")
    print(f"  fires: {len(fires)} {dict(Counter(f.sensor for f in fires))}; met {met.u10.shape} "
          f"{iso_z(met.times[0])}..{iso_z(met.times[-1])}  ({t_ing:.1f}s)")
    meta = publish(store, run_id, t0, fires, met, sources, members=a.members, afternoon_mode=a.afternoon_mode)
    n = meta.pop("_n_artifacts", 0)
    s = meta.get("model_summary", {})
    print(f"  model: {s.get('n_clusters')} clusters, {s.get('n_particles')} particles, {meta['members']} members, "
          f"afternoon={meta['afternoon_mode']}, scale={meta['scale']}, runtime {s.get('runtime_s')}s")
    for note in s.get("notes") or []:
        print(f"    note: {note}")
    print(f"  wrote {n} artifacts to latest/ and runs/{run_id}/  (total {time.perf_counter() - t_start:.1f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
