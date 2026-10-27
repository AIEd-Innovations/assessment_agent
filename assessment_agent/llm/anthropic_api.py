"""Claude models through the Anthropic Messages API."""
from __future__ import annotations

import anthropic

from .base import LLMAuthError, timed_json


class AnthropicProvider:
    def __init__(self, model: str, api_key: str) -> None:
        self.model_id = model
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    async def complete_with_raw(self, prompt: str) -> tuple[dict, str, int]:
        return await timed_json(self._complete(prompt))

    async def _complete(self, prompt: str) -> str:
        try:
            message = await self._client.messages.create(
                model=self.model_id,
                max_tokens=16000,
                messages=[{"role": "user", "content": prompt}],
            )
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as exc:
            raise LLMAuthError("The Anthropic API key was rejected.") from exc
        if message.stop_reason == "refusal":
            raise RuntimeError("The model declined to respond.")
        # Thinking blocks come first on current models; only the text blocks hold the answer.
        return "".join(block.text for block in message.content if block.type == "text")
