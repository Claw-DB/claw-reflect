"""OpenAIAdapter — calls the OpenAI Chat Completions API using httpx."""

from __future__ import annotations

import httpx

from claw_reflect.config import settings
from claw_reflect.llm.base import BaseLLMAdapter


class OpenAIAdapter(BaseLLMAdapter):
    """LLM adapter that sends requests to the OpenAI Chat Completions API."""

    _API_URL = "https://api.openai.com/v1/chat/completions"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=settings.llm_timeout_secs)

    async def complete(self, system: str, user: str, **kwargs: object) -> str:
        """Call the OpenAI API and return the assistant message content."""
        headers = {
            "Authorization": f"Bearer {settings.llm_api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": settings.llm_model,
            "max_tokens": settings.llm_max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        response = await self._client.post(self._API_URL, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        return str(data["choices"][0]["message"]["content"])
