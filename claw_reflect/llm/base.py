"""BaseLLMAdapter — abstract interface that all LLM provider adapters must implement."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseLLMAdapter(ABC):
    """Abstract adapter that normalises LLM provider APIs to a common interface."""

    @abstractmethod
    async def complete(self, system: str, user: str, **kwargs: object) -> str:
        """Send *system* + *user* prompt to the LLM and return the text completion."""
