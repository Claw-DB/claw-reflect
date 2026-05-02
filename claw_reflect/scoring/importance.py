"""LLM-backed and heuristic importance scoring."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from claw_reflect.llm.base import BaseLLMAdapter
from claw_reflect.llm.prompts import PromptLibrary, parse_json_response
from claw_reflect.models.memory import MemoryRecord


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


@dataclass(slots=True)
class ImportanceScore:
    memory_id: str
    score: float
    reasoning: str
    factors: list[str]
    scored_at: datetime
    used_llm: bool


class _ImportanceOutput(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    reasoning: str
    factors: list[str] = Field(default_factory=list)


class ImportanceScorer:
    def __init__(self, llm: BaseLLMAdapter, prompt_library: PromptLibrary) -> None:
        self.llm = llm
        self.prompts = prompt_library

    async def score(self, memory: MemoryRecord) -> ImportanceScore:
        messages = self.prompts.score_importance(
            memory=memory.content,
            context={
                "memory_type": memory.memory_type,
                "tags": memory.tags,
                "reflection_count": memory.reflection_count,
                "is_promoted": memory.is_promoted,
            },
        )
        try:
            response = await self.llm.complete_with_retry(
                messages=messages,
                max_tokens=256,
                temperature=0.1,
            )
            parsed = parse_json_response(response, _ImportanceOutput)
            score = _clamp(parsed.score, 0.0, 1.0)
            memory.importance_score = score
            return ImportanceScore(
                memory_id=memory.id,
                score=score,
                reasoning=parsed.reasoning,
                factors=list(parsed.factors),
                scored_at=datetime.now(UTC),
                used_llm=True,
            )
        except Exception:
            heuristic_score = self.score_heuristic(memory)
            memory.importance_score = heuristic_score
            return ImportanceScore(
                memory_id=memory.id,
                score=heuristic_score,
                reasoning="Heuristic fallback because LLM scoring unavailable",
                factors=["length", "tags", "memory_type", "recency"],
                scored_at=datetime.now(UTC),
                used_llm=False,
            )

    async def score_batch(self, memories: list[MemoryRecord], concurrency: int = 5) -> list[ImportanceScore]:
        semaphore = asyncio.Semaphore(max(1, concurrency))

        async def _score_one(memory: MemoryRecord) -> ImportanceScore:
            async with semaphore:
                return await self.score(memory)

        return list(await asyncio.gather(*(_score_one(memory) for memory in memories)))

    def score_heuristic(self, memory: MemoryRecord) -> float:
        content_len = len(memory.content or "")
        length_bonus = min(content_len / 500.0, 1.0) * 0.3
        tag_bonus = min(len(memory.tags or []) * 0.05, 0.2)
        type_bonus_map = {
            "task": 0.7,
            "reasoning_trace": 0.8,
            "tool_output": 0.5,
            "message": 0.4,
            "context": 0.3,
        }
        type_bonus = type_bonus_map.get(memory.memory_type, 0.4)
        age_days = max(
            0.0,
            (datetime.now(UTC) - memory.created_at).total_seconds() / 86_400,
        )
        recency_component = 1.0 / (1.0 + age_days * 0.01)

        weighted = length_bonus + tag_bonus + (type_bonus * 0.35) + (recency_component * 0.15)
        return _clamp(weighted, 0.0, 1.0)
