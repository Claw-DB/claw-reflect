"""Anthropic adapter using raw HTTP requests."""

from __future__ import annotations

import time

import httpx

from claw_reflect.llm.base import BaseLLMAdapter, LLMMessage, LLMResponse


class AnthropicAdapter(BaseLLMAdapter):
    _ANTHROPIC_VERSION = "2023-06-01"

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        base_url: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = (base_url or "https://api.anthropic.com").rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout)

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def provider(self) -> str:
        return "anthropic"

    async def complete(
        self,
        messages: list[LLMMessage],
        max_tokens: int,
        temperature: float = 0.2,
    ) -> LLMResponse:
        system_prompt = "\n\n".join(msg.content for msg in messages if msg.role == "system").strip()
        payload_messages = [
            {"role": msg.role, "content": msg.content}
            for msg in messages
            if msg.role in {"user", "assistant"}
        ]
        payload: dict[str, object] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": payload_messages,
        }
        if system_prompt:
            payload["system"] = system_prompt

        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": self._ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

        started = time.perf_counter()
        response = await self._client.post(f"{self._base_url}/v1/messages", json=payload, headers=headers)
        response.raise_for_status()
        latency_ms = (time.perf_counter() - started) * 1000
        data = response.json()

        content = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                content = str(block.get("text", ""))
                break

        usage = data.get("usage", {})
        return LLMResponse(
            content=content,
            model=str(data.get("model", self._model)),
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
            latency_ms=latency_ms,
            finish_reason=str(data.get("stop_reason", "unknown")),
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
