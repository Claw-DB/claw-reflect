"""Confidence scoring based on type priors and contradiction signals."""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from claw_reflect.models.contradiction import ContradictionRecord
from claw_reflect.models.memory import MemoryRecord


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


class ConfidenceScorer:
    def score(self, memory: MemoryRecord) -> float:
        base_by_type = {
            "task": 0.9,
            "tool_output": 0.85,
            "message": 0.7,
            "context": 0.6,
            "reasoning_trace": 0.75,
        }
        score = base_by_type.get(memory.memory_type, 0.65)

        confirmation_count = int(memory.metadata_.get("preference_confirmations", 0) or 0)
        score += 0.1 * confirmation_count

        has_contradiction = bool(memory.metadata_.get("has_active_contradiction", False))
        if has_contradiction:
            score -= 0.15

        if memory.is_promoted:
            score += 0.05

        score -= 0.05 * max(0, int(memory.reflection_count or 0))
        return _clamp(score, 0.1, 1.0)

    async def score_with_contradiction_check(self, memory: MemoryRecord, session: AsyncSession) -> float:
        contradiction_exists = await session.scalar(
            select(ContradictionRecord.id)
            .where(
                ContradictionRecord.resolved.is_(False),
                or_(
                    ContradictionRecord.memory_id_a == memory.id,
                    ContradictionRecord.memory_id_b == memory.id,
                ),
            )
            .limit(1)
        )
        if contradiction_exists:
            memory.metadata_["has_active_contradiction"] = True

        return self.score(memory)
