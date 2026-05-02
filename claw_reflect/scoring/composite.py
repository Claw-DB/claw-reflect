"""Weighted composite scoring across importance, recency and confidence."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from claw_reflect.models.memory import MemoryRecord
from claw_reflect.scoring.confidence import ConfidenceScorer
from claw_reflect.scoring.importance import ImportanceScorer
from claw_reflect.scoring.recency import RecencyScorer


@dataclass(slots=True)
class CompositeScore:
    memory_id: str
    composite: float
    importance: float
    recency: float
    confidence: float
    scored_at: datetime


class CompositeScorer:
    def __init__(
        self,
        importance_scorer: ImportanceScorer,
        recency_scorer: RecencyScorer,
        confidence_scorer: ConfidenceScorer,
        importance_w: float = 0.4,
        recency_w: float = 0.35,
        confidence_w: float = 0.25,
    ) -> None:
        self.importance_scorer = importance_scorer
        self.recency_scorer = recency_scorer
        self.confidence_scorer = confidence_scorer
        self.importance_w = importance_w
        self.recency_w = recency_w
        self.confidence_w = confidence_w

    async def score(self, memory: MemoryRecord, session: AsyncSession) -> CompositeScore:
        importance_result = await self.importance_scorer.score(memory)
        recency = self.recency_scorer.score(memory)
        confidence = await self.confidence_scorer.score_with_contradiction_check(memory, session)

        composite = self.importance_w * importance_result.score + self.recency_w * recency + self.confidence_w * confidence
        composite = max(0.0, min(1.0, composite))

        memory.importance_score = importance_result.score
        memory.recency_score = recency
        memory.confidence_score = confidence
        memory.composite_score = composite

        return CompositeScore(
            memory_id=memory.id,
            composite=composite,
            importance=importance_result.score,
            recency=recency,
            confidence=confidence,
            scored_at=datetime.now(UTC),
        )

    async def score_batch(
        self,
        memories: list[MemoryRecord],
        session: AsyncSession,
        concurrency: int = 10,
    ) -> list[CompositeScore]:
        semaphore = asyncio.Semaphore(max(1, concurrency))

        async def _score_one(memory: MemoryRecord) -> CompositeScore:
            async with semaphore:
                return await self.score(memory, session)

        return list(await asyncio.gather(*(_score_one(memory) for memory in memories)))
