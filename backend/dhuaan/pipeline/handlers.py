"""Lambda handlers (Step Functions: ingest -> model -> advise -> notify). Kept thin; logic lives in core.py.

ingest_handler  event {t0_utc?, no_lsasaf?}  -> {run_id, t0_utc, n_fires, sources_ok}
model_handler   event {run_id, members?, afternoon_mode?} -> {run_id, n_clusters, scale, ...}
advise_handler  event {run_id}               -> {run_id, advisories: [ids]}   (dhuaan.agent.advisory.generate_all)
notify_handler  event {school_id?, lang?}    -> {sent, school_id}             (Telegram sendMessage)
"Score" is part of model.run (exposure ranking, arrival windows), so there is no separate score handler.
"""
from __future__ import annotations

import logging
from typing import Any

from dhuaan.ingest.common import iso_z, now_utc
from dhuaan.pipeline.core import floor_hour, ingest, load_raw, make_run_id, parse_iso, publish, save_raw
from dhuaan.store import get_store

log = logging.getLogger("dhuaan.pipeline.handlers")
logging.getLogger().setLevel(logging.INFO)


def ingest_handler(event: dict[str, Any] | None, context: Any = None) -> dict[str, Any]:
    event = event or {}
    t0 = floor_hour(parse_iso(event["t0_utc"]) if event.get("t0_utc") else now_utc())
    run_id = make_run_id(t0)
    fires, met, sources = ingest(t0, use_lsasaf=not event.get("no_lsasaf", False))
    save_raw(get_store(), run_id, t0, fires, met, sources)
    return {"run_id": run_id, "t0_utc": iso_z(t0), "n_fires": len(fires),
            "sources_ok": sum(1 for s in sources if s["ok"]), "sources_total": len(sources)}


def model_handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    store = get_store()
    run_id = event["run_id"]
    t0, fires, met, sources = load_raw(store, run_id)
    meta = publish(store, run_id, t0, fires, met, sources, members=int(event.get("members", 5)),
                   afternoon_mode=event.get("afternoon_mode", "estimated"))
    s = meta.get("model_summary", {})
    return {"run_id": run_id, "t0_utc": meta["t0_utc"], "n_fires": s.get("n_fires"), "n_clusters": s.get("n_clusters"),
            "scale": meta.get("scale"), "afternoon_mode": meta["afternoon_mode"], "runtime_s": s.get("runtime_s"),
            "n_artifacts": meta.get("_n_artifacts")}


def advise_handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    # The daily 06:30 IST schedule starts with {"mode": "advise"} and no run_id: advise on the latest published run.
    run_id = (event or {}).get("run_id") or (get_store().get_json("latest/meta.json") or {}).get("run_id")
    if not run_id:
        return {"run_id": None, "advisories": [], "note": "no published run yet"}
    try:
        from dhuaan.agent.advisory import generate_all
    except ImportError as e:
        log.warning("advisory module unavailable: %s", e)
        return {"run_id": run_id, "advisories": [], "note": "dhuaan.agent.advisory not importable"}
    ids = generate_all(get_store(), run_id, event.get("school_ids"))
    return {"run_id": run_id, "advisories": list(ids)}


def _demo_school_id() -> str:
    from dhuaan.geo.receptors import load_demo_places
    return load_demo_places()["school"]["id"]


def format_message(adv: dict[str, Any], school_name: str, langs: list[str]) -> str:
    plan = adv.get("plan") or []
    counts: dict[str, int] = {}
    for h in plan:
        counts[h.get("outdoor", "?")] = counts.get(h.get("outdoor", "?"), 0) + 1
    worst = max(plan, key=lambda h: h.get("est_pm25") or 0, default=None)
    lines = [f"Dhuaan school-day advisory: {school_name}", f"Date (IST): {adv.get('date_ist', '?')}"]
    if worst:
        lines.append(f"Worst hour {worst.get('hour_ist')}: ~{worst.get('est_pm25')} µg/m³ ({worst.get('category')})")
    if counts:
        lines.append("Outdoor hours: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    notice = adv.get("notice") or {}
    for lg in langs:
        if notice.get(lg):
            lines += ["", notice[lg]]
    g = adv.get("grounding") or {}
    if g:
        lines += ["", f"Facts checked against the forecast: {g.get('verified')}/{g.get('total')}"]
    return "\n".join(lines)[:3900]  # Telegram limit is 4096 chars


def notify_handler(event: dict[str, Any] | None = None, context: Any = None) -> dict[str, Any]:
    import requests

    from dhuaan.config import settings
    event = event or {}
    school_id = event.get("school_id") or _demo_school_id()
    langs = event.get("lang") or ["en", "pa"]
    langs = [langs] if isinstance(langs, str) else list(langs)
    adv = get_store().get_json(f"latest/advisories/{school_id}.json")
    if adv is None:
        return {"sent": False, "school_id": school_id, "note": "no advisory"}
    if not (settings.telegram_bot_token and settings.telegram_chat_id):
        return {"sent": False, "school_id": school_id, "note": "TELEGRAM_BOT_TOKEN/CHAT_ID not set"}
    try:
        from dhuaan.geo.receptors import load_demo_places
        demo = load_demo_places()["school"]
        name = demo["name"] if demo["id"] == school_id else school_id
    except Exception:
        name = school_id
    text = format_message(adv, name, langs)
    r = requests.post(f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                      json={"chat_id": settings.telegram_chat_id, "text": text, "disable_web_page_preview": True},
                      timeout=20)
    ok = r.status_code == 200 and r.json().get("ok", False)
    if not ok:  # never log the URL: it contains the bot token
        log.warning("Telegram sendMessage failed: HTTP %s %s", r.status_code, r.text[:200])
    return {"sent": ok, "school_id": school_id, "chars": len(text)}
