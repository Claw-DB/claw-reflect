"""RecencyScorer — scores memory records based on how recently they were created or confirmed."""

from __future__ import annotations

from claw_reflect.models.memory import MemoryRecord


class RecencyScorer:
    """Scores a memory record based on its age relative to the current time."""

    def score(self, record: MemoryRecord) -> float:
        """Return a recency score in [0, 1] for *record* (1.0 = brand new)."""
        raise NotImplementedError
