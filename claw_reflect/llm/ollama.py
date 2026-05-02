"""Ollama adapter that uses OpenAI-compatible chat API semantics."""

from __future__ import annotations

from claw_reflect.llm.openai import OpenAIAdapter


class OllamaAdapter(OpenAIAdapter):
    def __init__(self, model: str, base_url: str = "http://localhost:11434", timeout: float = 30.0) -> None:
        super().__init__(api_key="ollama", model=model, base_url=base_url, timeout=timeout)

    @property
    def provider(self) -> str:
        return "ollama"

    async def health_check(self) -> bool:
        try:
            response = await self._client.get(f"{self._base_url}/api/tags")
            response.raise_for_status()
            tags = response.json().get("models", [])
            return any(item.get("name", "").startswith(self.model_name) for item in tags)
        except Exception:
            return False
