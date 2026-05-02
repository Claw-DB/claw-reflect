"""Recency-based memory scoring using exponential decay."""

from __future__ import annotations

import math
from datetime import datetime, timezone

from claw_reflect.models.memory import MemoryRecord


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


class RecencyScorer:
    def __init__(self, half_life_days: float = 30.0) -> None:
        self._default_half_life_days = half_life_days

    def score(self, memory: MemoryRecord, now: datetime | None = None) -> float:
        now_ts = now or datetime.now(timezone.utc)
        created_at = memory.created_at if memory.created_at.tzinfo else memory.created_at.replace(tzinfo=timezone.utc)
        age_days = max(0.0, (now_ts - created_at).total_seconds() / 86_400)
        if age_days < 1.0:
            return 1.0

        half_life_days = self.half_life_for_type(memory.memory_type)
        decay_lambda = math.log(2.0) / half_life_days
        score = math.exp(-decay_lambda * age_days)
        return _clamp(score, 0.0, 1.0)

    def half_life_for_type(self, memory_type: str) -> float:
        lookup = {
            "task": 7,
            "tool_output": 3,
            "context": 1,
            "message": 14,
            "reasoning_trace": 21,
            "session": 30,
        }
        return float(lookup.get(memory_type, self._default_half_life_days))

    def days_since_created(self, memory: MemoryRecord) -> float:
        return max(
            0.0,
            (datetime.now(timezone.utc) - (memory.created_at if memory.created_at.tzinfo else memory.created_at.replace(tzinfo=timezone.utc))).total_seconds() / 86_400,
        )
