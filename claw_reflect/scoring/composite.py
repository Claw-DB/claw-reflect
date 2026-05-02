"""CompositeScorer — combines importance, recency, and confidence into a single score."""

from __future__ import annotations

from claw_reflect.config import settings
from claw_reflect.models.memory import MemoryRecord
from claw_reflect.scoring.confidence import ConfidenceScorer
from claw_reflect.scoring.importance import ImportanceScorer
from claw_reflect.scoring.recency import RecencyScorer


class CompositeScorer:
    """Computes a weighted composite score from the three individual scorers."""

    def __init__(self) -> None:
        self._importance = ImportanceScorer()
        self._recency = RecencyScorer()
        self._confidence = ConfidenceScorer()

    def score(self, record: MemoryRecord) -> float:
        """Return the weighted composite score in [0, 1] for *record*."""
        i = self._importance.score(record)
        r = self._recency.score(record)
        c = self._confidence.score(record)
        return (
            settings.importance_weight * i
            + settings.recency_weight * r
            + settings.confidence_weight * c
        )
