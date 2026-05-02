"""OpenAI-compatible adapter for chat completions endpoints."""

from __future__ import annotations

import time

import httpx

from claw_reflect.llm.base import BaseLLMAdapter, LLMMessage, LLMResponse


class OpenAIAdapter(BaseLLMAdapter):
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com",
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout)

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def provider(self) -> str:
        return "openai"

    async def complete(
        self,
        messages: list[LLMMessage],
        max_tokens: int,
        temperature: float = 0.2,
    ) -> LLMResponse:
        payload = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        started = time.perf_counter()
        response = await self._client.post(
            f"{self._base_url}/v1/chat/completions",
            json=payload,
            headers=headers,
        )
        response.raise_for_status()
        latency_ms = (time.perf_counter() - started) * 1000

        data = response.json()
        first_choice = (data.get("choices") or [{}])[0]
        message = first_choice.get("message") or {}
        usage = data.get("usage") or {}

        return LLMResponse(
            content=str(message.get("content", "")),
            model=str(data.get("model", self._model)),
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
            latency_ms=latency_ms,
            finish_reason=str(first_choice.get("finish_reason", "unknown")),
        )

    async def health_check(self) -> bool:
        try:
            await self.complete(
                messages=[LLMMessage(role="user", content="ping")],
                max_tokens=5,
                temperature=0.0,
            )
            return True
        except Exception:
            return False
