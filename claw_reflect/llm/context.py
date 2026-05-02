"""Token budgeting and context management for chat prompts."""

from __future__ import annotations

import tiktoken

from claw_reflect.llm.base import LLMMessage


class ContextWindowManager:
    def __init__(
        self,
        model: str,
        max_context_tokens: int = 100_000,
        max_output_tokens: int = 2048,
    ) -> None:
        self.model = model
        self.max_context_tokens = max_context_tokens
        self.max_output_tokens = max_output_tokens

    def count_tokens(self, text: str) -> int:
        if not text:
            return 0
        try:
            enc = tiktoken.encoding_for_model(self.model)
            return len(enc.encode(text))
        except Exception:
            return max(1, len(text) // 4)

    def _message_tokens(self, msg: LLMMessage) -> int:
        return self.count_tokens(msg.content) + 4

    def _total_tokens(self, messages: list[LLMMessage]) -> int:
        return sum(self._message_tokens(msg) for msg in messages)

    def truncate_to_fit(self, messages: list[LLMMessage], reserve_output: int) -> list[LLMMessage]:
        if not messages:
            return []

        budget = self.max_context_tokens - max(0, reserve_output)
        if budget <= 0:
            return messages[-1:]

        if self._total_tokens(messages) <= budget:
            return list(messages)

        system_idx = next((i for i, m in enumerate(messages) if m.role == "system"), None)
        last_user_idx = next(
            (i for i in range(len(messages) - 1, -1, -1) if messages[i].role == "user"),
            None,
        )

        keep_indices: set[int] = set()
        if system_idx is not None:
            keep_indices.add(system_idx)
        if last_user_idx is not None:
            keep_indices.add(last_user_idx)

        remaining_indices = list(range(len(messages)))

        def _can_remove(idx: int) -> bool:
            return idx not in keep_indices and messages[idx].role in {"user", "assistant"}

        while self._total_tokens([messages[i] for i in remaining_indices]) > budget:
            removed = False

            for pos in range(0, len(remaining_indices) - 1):
                i = remaining_indices[pos]
                j = remaining_indices[pos + 1]
                if not _can_remove(i) or not _can_remove(j):
                    continue
                if messages[i].role == "user" and messages[j].role == "assistant":
                    remaining_indices.pop(pos + 1)
                    remaining_indices.pop(pos)
                    removed = True
                    break

            if removed:
                continue

            for pos, idx in enumerate(remaining_indices):
                if _can_remove(idx):
                    remaining_indices.pop(pos)
                    removed = True
                    break

            if not removed:
                break

        truncated = [messages[i] for i in remaining_indices]

        return truncated

    def fits_in_context(self, messages: list[LLMMessage]) -> bool:
        return self._total_tokens(messages) + self.max_output_tokens <= self.max_context_tokens

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        pricing_per_1m: dict[str, tuple[float, float]] = {
            "claude-sonnet-4-20250514": (3.0, 15.0),
            "claude-3-5-sonnet-20241022": (3.0, 15.0),
            "gpt-4o": (5.0, 15.0),
            "gpt-4o-mini": (0.15, 0.60),
            "gpt-4.1": (2.0, 8.0),
            "gpt-4.1-mini": (0.40, 1.60),
        }
        if self.model not in pricing_per_1m:
            return 0.0
        in_price, out_price = pricing_per_1m[self.model]
        return (input_tokens / 1_000_000 * in_price) + (output_tokens / 1_000_000 * out_price)
