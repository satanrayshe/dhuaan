"""Lambda Function URL handler (payload format 2.0) implementing the CONTRACTS API.

GET  /api/health                      -> {ok, run_id, model_provider}
GET  /api/search?q=<text>&limit=10    -> {places: [index entries]}
POST /api/ask {question, place_id?, lang} -> {answer, lang, tool_trace, grounding, model, cached}
GET  /api/advisory?school_id=<id>&lang=en -> advisory artifact (+ lang, notice_text)
CORS headers come from settings.allowed_origin (comma-separated list allowed; "*" locally). Configure CORS here
only, not also on the Function URL, or browsers see duplicate Access-Control-Allow-Origin headers.
"""
from __future__ import annotations

import base64
import json
import logging
import re
from typing import Any

from dhuaan.agent import data
from dhuaan.api import ratelimit
from dhuaan.config import settings

log = logging.getLogger(__name__)
LANGS = ("en", "hi", "pa")
MAX_QUESTION = 500
MAX_BODY = 8192
_ID = re.compile(r"^[A-Za-z0-9_.\-]{1,100}$")


class ApiError(Exception):
    def __init__(self, status: int, message: str, headers: dict | None = None):
        super().__init__(message)
        self.status, self.message, self.headers = status, message, headers or {}


def _cors(origin: str | None) -> dict:
    allowed = [o.strip() for o in (settings.allowed_origin or "*").split(",") if o.strip()]
    if "*" in allowed:
        allow = "*"
    elif origin and origin in allowed:
        allow = origin
    else:
        allow = allowed[0] if allowed else "*"
    h = {"Access-Control-Allow-Origin": allow, "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
         "Access-Control-Allow-Headers": "content-type", "Access-Control-Max-Age": "86400"}
    if allow != "*":
        h["Vary"] = "Origin"
    return h


def _resp(status: int, body: Any, origin: str | None, extra: dict | None = None) -> dict:
    headers = {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store", **_cors(origin), **(extra or {})}
    return {"statusCode": status, "headers": headers,
            "body": "" if body is None else json.dumps(body, ensure_ascii=False, separators=(",", ":"))}


def _header(event: dict, name: str) -> str | None:
    for k, v in (event.get("headers") or {}).items():
        if k.lower() == name:
            return v
    return None


def _query(event: dict) -> dict:
    return {k: v for k, v in (event.get("queryStringParameters") or {}).items() if v is not None}


def _body(event: dict) -> dict:
    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8", "replace")
    if len(raw) > MAX_BODY:
        raise ApiError(413, "request body too large")
    try:
        obj = json.loads(raw or "{}")
    except ValueError:
        raise ApiError(400, "body must be JSON")
    if not isinstance(obj, dict):
        raise ApiError(400, "body must be a JSON object")
    return obj


def _client_ip(event: dict) -> str:
    return ((event.get("requestContext") or {}).get("http") or {}).get("sourceIp") or "unknown"


def health(event: dict) -> dict:
    return {"ok": data.meta() is not None, "run_id": data.run_id(), "model_provider": settings.model_provider}


def search(event: dict) -> dict:
    q = _query(event).get("q", "").strip()
    if not q or len(q) > 100:
        raise ApiError(400, "q must be 1-100 characters")
    try:
        limit = int(_query(event).get("limit", "10"))
    except ValueError:
        raise ApiError(400, "limit must be an integer")
    if not 1 <= limit <= 50:
        raise ApiError(400, "limit must be 1-50")
    return {"places": data.search(q, limit)}


def ask(event: dict) -> dict:
    b = _body(event)
    q, lang, pid = b.get("question"), b.get("lang", "en"), b.get("place_id")
    if not isinstance(q, str) or not q.strip():
        raise ApiError(400, "question is required")
    if len(q) > MAX_QUESTION:
        raise ApiError(400, f"question must be at most {MAX_QUESTION} characters")
    if lang not in LANGS:
        raise ApiError(400, "lang must be one of en, hi, pa")
    if pid in ("", None):
        pid = None
    elif not isinstance(pid, str) or not _ID.match(pid):
        raise ApiError(400, "place_id is invalid")
    elif data.place(pid) is None:
        raise ApiError(404, f"unknown place_id '{pid}'")
    from dhuaan.agent import agent as ag  # lazy: health/search never import Strands

    hit = data.store().get_json(ag.cache_key(q, pid, lang))
    if hit:  # cached answers don't count against the rate limit
        return {**hit, "cached": True}
    d = ratelimit.get_limiter().check(_client_ip(event))
    if not d.allowed:
        raise ApiError(429, d.reason, {"Retry-After": str(d.retry_after_s)})
    try:
        return ag.ask(q, place_id=pid, lang=lang)
    except ValueError as e:
        raise ApiError(400, str(e))
    except Exception as e:
        log.exception("ask failed")
        throttled = "Throttl" in type(e).__name__ or "RESOURCE_EXHAUSTED" in str(e)
        raise ApiError(503, "the language model is busy, please try again in a minute" if throttled
                       else "the assistant is unavailable right now")


def advisory(event: dict) -> dict:
    qs = _query(event)
    sid, lang = qs.get("school_id", ""), qs.get("lang", "en")
    if not _ID.match(sid or ""):
        raise ApiError(400, "school_id is required")
    if lang not in LANGS:
        raise ApiError(400, "lang must be one of en, hi, pa")
    art = data.advisory(sid)
    if not art:
        raise ApiError(404, f"no advisory for '{sid}'")
    return {**art, "lang": lang, "notice_text": (art.get("notice") or {}).get(lang)}


ROUTES = {("GET", "/api/health"): health, ("GET", "/api/search"): search,
          ("POST", "/api/ask"): ask, ("GET", "/api/advisory"): advisory}


def handler(event: dict, context: Any = None) -> dict:
    method = ((event.get("requestContext") or {}).get("http") or {}).get("method") or event.get("httpMethod") or "GET"
    method = method.upper()
    path = (event.get("rawPath") or event.get("path") or "/").rstrip("/") or "/"
    origin = _header(event, "origin")
    if method == "OPTIONS":
        return _resp(204, None, origin)
    fn = ROUTES.get((method, path))
    if fn is None:
        if any(p == path for _, p in ROUTES):
            return _resp(405, {"error": "method not allowed"}, origin)
        return _resp(404, {"error": "not found"}, origin)
    try:
        return _resp(200, fn(event), origin)
    except ApiError as e:
        return _resp(e.status, {"error": e.message}, origin, e.headers)
    except Exception:
        log.exception("unhandled error on %s %s", method, path)
        return _resp(500, {"error": "internal error"}, origin)
