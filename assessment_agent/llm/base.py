"""
Base protocol and shared utilities for LLM providers.
"""
from __future__ import annotations

import json
import time
from typing import Awaitable, Protocol


class LLMProvider(Protocol):
    """Provider-agnostic interface for LLM inference."""

    model_id: str

    async def complete_with_raw(self, prompt: str) -> tuple[dict, str, int]:
        """Send a prompt and return (parsed_json, raw_response_text, latency_ms)."""
        ...


class LLMAuthError(Exception):
    """The provider rejected the API key. Grading cannot continue with this key."""


async def timed_json(response: Awaitable[str]) -> tuple[dict, str, int]:
    """Await a provider's text response and return (parsed_json, raw_text, latency_ms)."""
    start = time.monotonic()
    raw = await response
    latency_ms = int((time.monotonic() - start) * 1000)
    return extract_json(raw), raw, latency_ms


def extract_json(text: str) -> dict:
    """
    Extract and parse JSON from an LLM response.

    Handles markdown code-block wrappers (```json ... ```) and falls back
    to locating the first '{' to the last '}' when a straight parse fails.
    """
    text = text.strip()

    # Strip markdown code-block wrappers
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object within the response
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
        raise
