"""ContextWindowManager — counts tokens and truncates prompts to fit the LLM context window."""

from __future__ import annotations

import tiktoken

from claw_reflect.config import settings


class ContextWindowManager:
    """Manages token budgets and truncates text to stay within the LLM context window."""

    def __init__(self, model: str | None = None, max_tokens: int | None = None) -> None:
        self._max_tokens = max_tokens or settings.llm_max_tokens
        try:
            self._enc = tiktoken.encoding_for_model(model or settings.llm_model)
        except KeyError:
            self._enc = tiktoken.get_encoding("cl100k_base")

    def count_tokens(self, text: str) -> int:
        """Return the number of tokens in *text*."""
        return len(self._enc.encode(text))

    def truncate(self, text: str, budget: int | None = None) -> str:
        """Truncate *text* to *budget* tokens (defaults to ``max_tokens``)."""
        limit = budget or self._max_tokens
        tokens = self._enc.encode(text)
        if len(tokens) <= limit:
            return text
        return self._enc.decode(tokens[:limit])
