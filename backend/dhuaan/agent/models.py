"""Model provider switch (settings.model_provider): Gemini free tier now, Bedrock Nova 2 Lite when unblocked."""
from __future__ import annotations

import time
from typing import Any, Callable, TypeVar

from dhuaan.config import settings

T = TypeVar("T")
TEMPERATURE = 0.1
MAX_TOKENS = 1024


def model_label(provider: str | None = None, model_id: str | None = None) -> str:
    provider = provider or settings.model_provider
    if provider == "bedrock":
        return f"bedrock:{model_id or settings.bedrock_model_id}"
    return f"gemini:{model_id or settings.gemini_model}"


def build_model(provider: str | None = None, model_id: str | None = None, max_tokens: int = MAX_TOKENS) -> Any:
    """Return a Strands model. Imports are lazy so tests and the API never load a provider they don't use."""
    provider = provider or settings.model_provider
    if provider == "bedrock":
        from strands.models.bedrock import BedrockModel
        return BedrockModel(model_id=model_id or settings.bedrock_model_id, region_name=settings.aws_region,
                            temperature=TEMPERATURE, max_tokens=max_tokens)
    if provider == "gemini":
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        from strands.models.gemini import GeminiModel
        mid = model_id or settings.gemini_model
        params: dict[str, Any] = {"temperature": TEMPERATURE, "max_output_tokens": max_tokens}
        if "2.5" in mid:
            # thinking tokens eat free-tier quota and latency; the tools do the reasoning
            params["thinking_config"] = {"thinking_budget": 0}
        return GeminiModel(client_args={"api_key": settings.gemini_api_key}, model_id=mid, params=params)
    raise ValueError(f"unknown MODEL_PROVIDER '{provider}' (expected gemini or bedrock)")


# Google retires model ids for new keys (gemini-2.5-flash returned 404 "no longer available to new users" on# Google retires model ids for new keys: gemini-2.5-flash and gemini-2.5-flash-lite are still *listed* by
# GET /v1beta/models but return 404 "no longer available to new users" (8 Oct 2026). The chain below was built
# from that listing (models supporting generateContent), minus the retired 2.5 ids. Each id has its own
# free-tier quota bucket, so a 429 on one is worth trying on the next.
GEMINI_PRIMARY = "gemini-flash-lite-latest"
GEMINI_CHAIN = (GEMINI_PRIMARY, "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-flash-latest",
                "gemini-3.5-flash")
OVERLOAD_RETRIES = 2              # 503 "high demand" is usually transient: retry the same id briefly first
OVERLOAD_BACKOFF_S = (1.5, 3.0)
_unavailable: set[str] = set()


def candidates(provider: str | None = None) -> list[str | None]:
    """Model ids to try in order (None = the provider default from settings)."""
    provider = provider or settings.model_provider
    if provider != "gemini":
        return [None]
    ids = [m for m in dict.fromkeys([settings.gemini_model, *GEMINI_CHAIN]) if m not in _unavailable]
    return ids or [settings.gemini_model]


def classify_error(e: BaseException) -> str | None:
    """'unavailable' (id gone/unknown), 'overloaded' (503, transient), 'throttled' (429 quota) or None."""
    name, msg = type(e).__name__, str(e)
    code = getattr(e, "code", None)
    if code == 503 or "UNAVAILABLE" in msg or "high demand" in msg or "overloaded" in msg.lower():
        return "overloaded"
    if name == "ModelThrottledException" or code == 429 or "RESOURCE_EXHAUSTED" in msg:
        return "throttled"  # quota: another model id has its own bucket
    if code == 404 or "NOT_FOUND" in msg or "no longer available" in msg:
        return "unavailable"
    return None


def mark_unavailable(model_id: str | None) -> None:
    if model_id:
        _unavailable.add(model_id)


def call_with_fallback(fn: Callable[[str | None], T], *, sleep: Callable[[float], None] = time.sleep,
                       on_error: Callable[[str | None, str], None] | None = None) -> tuple[T, str | None]:
    """Run fn(model_id) down the candidate chain. 503 -> short backoff on the same id (OVERLOAD_RETRIES), then
    the next id; 429 -> next id; 404 -> mark retired, next id; anything else is raised. Returns (result, id)."""
    last: BaseException | None = None
    for mid in candidates():
        for attempt in range(OVERLOAD_RETRIES + 1):
            try:
                return fn(mid), mid
            except Exception as e:
                kind = classify_error(e)
                if kind is None:
                    raise
                last = e
                if on_error:
                    on_error(mid, kind)
                if kind == "unavailable":
                    mark_unavailable(mid)
                if kind == "overloaded" and attempt < OVERLOAD_RETRIES:
                    sleep(OVERLOAD_BACKOFF_S[min(attempt, len(OVERLOAD_BACKOFF_S) - 1)])
                    continue
                break
    raise last or RuntimeError("no model available")
