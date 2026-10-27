"""OpenAI models through the Responses API."""
from __future__ import annotations

import openai

from .base import LLMAuthError, timed_json


class OpenAIProvider:
    def __init__(self, model: str, api_key: str) -> None:
        self.model_id = model
        self._client = openai.AsyncOpenAI(api_key=api_key)

    async def complete_with_raw(self, prompt: str) -> tuple[dict, str, int]:
        return await timed_json(self._complete(prompt))

    async def _complete(self, prompt: str) -> str:
        try:
            response = await self._client.responses.create(
                model=self.model_id,
                input=prompt,
                text={"format": {"type": "json_object"}},
            )
        except (openai.AuthenticationError, openai.PermissionDeniedError) as exc:
            raise LLMAuthError("The OpenAI API key was rejected.") from exc
        return response.output_text
