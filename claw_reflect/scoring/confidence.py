"""ConfidenceScorer — scores memory records based on source reliability and confirmation count."""

from __future__ import annotations

from claw_reflect.models.memory import MemoryRecord


class ConfidenceScorer:
    """Scores a memory record based on confirmation history and source reliability."""

    def score(self, record: MemoryRecord) -> float:
        """Return a confidence score in [0, 1] for *record*."""
        raise NotImplementedError
