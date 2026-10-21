"""Resolves the configured LLM client. Returns ``None`` when AI is off or unconfigured.

Tests and simulations swap in a fake with ``set_llm_override``.
"""

from __future__ import annotations

from app.core.config import get_settings
from app.llm.client import LLMClient, OpenAIJSONClient

_override: LLMClient | None = None
_override_set = False
_cached: OpenAIJSONClient | None = None


def set_llm_override(client: LLMClient | None, *, active: bool = True) -> None:
    global _override, _override_set
    _override = client
    _override_set = active


def get_llm() -> LLMClient | None:
    global _cached
    if _override_set:
        return _override
    settings = get_settings()
    if not settings.ai_configured:
        return None
    if _cached is None or _cached.model != settings.openai_model:
        assert settings.openai_api_key
        _cached = OpenAIJSONClient(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            timeout=settings.openai_timeout_seconds,
        )
    return _cached
