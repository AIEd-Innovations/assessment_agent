"""The models an assignment can be graded with, and which vendor serves each one."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Vendor = Literal["anthropic", "openai", "gemini"]


@dataclass(frozen=True)
class Model:
    id: str
    vendor: Vendor
    name: str


SUPPORTED_MODELS: dict[str, Model] = {
    m.id: m
    for m in (
        Model("claude-opus-5-5", "anthropic", "Claude Opus 5.5"),
        Model("claude-sonnet-5-5", "anthropic", "Claude Sonnet 5.5"),
        Model("claude-haiku-5-5", "anthropic", "Claude Haiku 5.5"),
        Model("gpt-6-astra", "openai", "GPT-6 Astra"),
        Model("gpt-6.1-sol", "openai", "GPT-6.1 Sol"),
        Model("gpt-6-luna", "openai", "GPT-6 Luna"),
        Model("gemini-4-argon", "gemini", "Gemini 4 Argon"),
        Model("gemini-3.8-flash", "gemini", "Gemini 3.8 Flash"),
        Model("gemini-3.5-flash-lite", "gemini", "Gemini 3.5 Flash-Lite"),
    )
}
