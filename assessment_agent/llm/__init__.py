"""
LLM providers. Each grading request names a model (from the assignment's spec)
and may carry the teacher's API key for that model's vendor.
"""
from __future__ import annotations

from .base import LLMAuthError, LLMProvider, extract_json
from .models import SUPPORTED_MODELS

__all__ = ["LLMAuthError", "LLMProvider", "SUPPORTED_MODELS", "extract_json", "get_llm_provider"]


def get_llm_provider(model: str, api_key: str | None) -> LLMProvider:
    """Return a provider for the model, or the offline mock when there is no API key."""
    if not api_key:
        from .fake import FakeLLMProvider

        return FakeLLMProvider()

    vendor = SUPPORTED_MODELS[model].vendor
    if vendor == "anthropic":
        from .anthropic_api import AnthropicProvider

        return AnthropicProvider(model, api_key)
    if vendor == "openai":
        from .openai_api import OpenAIProvider

        return OpenAIProvider(model, api_key)
    from .gemini_api import GeminiProvider

    return GeminiProvider(model, api_key)
