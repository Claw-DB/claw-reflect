"""AnthropicAdapter — calls the Anthropic Claude API using httpx with retry logic."""

from __future__ import annotations

import httpx

from claw_reflect.config import settings
from claw_reflect.llm.base import BaseLLMAdapter


class AnthropicAdapter(BaseLLMAdapter):
    """LLM adapter that sends requests to the Anthropic Messages API."""

    _API_URL = "https://api.anthropic.com/v1/messages"
    _ANTHROPIC_VERSION = "2023-06-01"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=settings.llm_timeout_secs)

    async def complete(self, system: str, user: str, **kwargs: object) -> str:
        """Call the Anthropic API and return the assistant message text."""
        headers = {
            "x-api-key": settings.llm_api_key.get_secret_value(),
            "anthropic-version": self._ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        payload = {
            "model": settings.llm_model,
            "max_tokens": settings.llm_max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        response = await self._client.post(self._API_URL, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        return str(data["content"][0]["text"])
