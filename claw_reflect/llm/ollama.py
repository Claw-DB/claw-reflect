"""OllamaAdapter — calls a locally-running Ollama instance for local model inference."""

from __future__ import annotations

import httpx

from claw_reflect.config import settings
from claw_reflect.llm.base import BaseLLMAdapter


class OllamaAdapter(BaseLLMAdapter):
    """LLM adapter that communicates with a locally-running Ollama server."""

    _DEFAULT_BASE_URL = "http://localhost:11434"

    def __init__(self) -> None:
        base = settings.llm_base_url or self._DEFAULT_BASE_URL
        self._api_url = f"{base.rstrip('/')}/api/chat"
        self._client = httpx.AsyncClient(timeout=settings.llm_timeout_secs)

    async def complete(self, system: str, user: str, **kwargs: object) -> str:
        """Send a chat request to Ollama and return the assistant message content."""
        payload = {
            "model": settings.llm_model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        response = await self._client.post(self._api_url, json=payload)
        response.raise_for_status()
        data = response.json()
        return str(data["message"]["content"])
