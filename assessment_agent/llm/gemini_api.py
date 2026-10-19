"""Gemini models through the Google Gen AI SDK."""
from __future__ import annotations

from google import genai
from google.genai import errors

from .base import LLMAuthError, timed_json


class GeminiProvider:
    def __init__(self, model: str, api_key: str) -> None:
        self.model_id = model
        self._client = genai.Client(api_key=api_key)

    async def complete_with_raw(self, prompt: str) -> tuple[dict, str, int]:
        return await timed_json(self._complete(prompt))

    async def _complete(self, prompt: str) -> str:
        try:
            response = await self._client.aio.models.generate_content(
                model=self.model_id,
                contents=prompt,
                config={"response_mime_type": "application/json"},
            )
        except errors.ClientError as exc:
            # An invalid key comes back as 400 API_KEY_INVALID rather than 401.
            if exc.code in (401, 403) or "API_KEY_INVALID" in str(exc.details):
                raise LLMAuthError("The Gemini API key was rejected.") from exc
            raise
        return response.text or ""
