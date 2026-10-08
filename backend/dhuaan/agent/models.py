"""Model provider switch (settings.model_provider): Gemini free tier now, Bedrock Nova 2 Lite when unblocked."""
from __future__ import annotations

from typing import Any

from dhuaan.config import settings

TEMPERATURE = 0.1
MAX_TOKENS = 1024
GEMINI_FALLBACK = "gemini-2.5-flash-lite"  # separate free-tier quota bucket (if still served for this key)


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


# Google retires model ids for new keys (gemini-2.5-flash returned 404 "no longer available to new users" on
# 8 Oct 2026), so after the configured model we fall back to the rolling aliases.
GEMINI_CHAIN = ("gemini-flash-latest", GEMINI_FALLBACK, "gemini-flash-lite-latest")
_unavailable: set[str] = set()


def candidates(provider: str | None = None) -> list[str | None]:
    """Model ids to try in order (None = the provider default from settings)."""
    provider = provider or settings.model_provider
    if provider != "gemini":
        return [None]
    ids = [m for m in dict.fromkeys([settings.gemini_model, *GEMINI_CHAIN]) if m not in _unavailable]
    return ids or [settings.gemini_model]


def classify_error(e: BaseException) -> str | None:
    """'unavailable' (model id gone/unknown), 'throttled' (quota/rate), or None (not a model-choice problem)."""
    name, msg = type(e).__name__, str(e)
    code = getattr(e, "code", None)
    if (name == "ModelThrottledException" or code in (429, 503) or "RESOURCE_EXHAUSTED" in msg
            or "UNAVAILABLE" in msg or "high demand" in msg):
        return "throttled"  # quota or overload: another model id has its own capacity
    if getattr(e, "code", None) == 404 or "NOT_FOUND" in msg or "no longer available" in msg:
        return "unavailable"
    return None


def mark_unavailable(model_id: str | None) -> None:
    if model_id:
        _unavailable.add(model_id)
