"""ImportanceScorer — estimates how important a memory record is to an agent's knowledge base."""

from __future__ import annotations

from claw_reflect.models.memory import MemoryRecord


class ImportanceScorer:
    """Scores a memory record based on semantic importance signals."""

    def score(self, record: MemoryRecord) -> float:
        """Return an importance score in [0, 1] for *record*."""
        raise NotImplementedError
