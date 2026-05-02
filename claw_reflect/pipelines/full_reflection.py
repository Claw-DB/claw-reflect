"""FullReflectionPipeline — orchestrates all sub-pipelines in the correct order."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from claw_reflect.pipelines.base import BasePipeline
from claw_reflect.pipelines.contradiction_detector import ContradictionDetectionPipeline
from claw_reflect.pipelines.duplicate_collapser import DuplicateCollapsePipeline
from claw_reflect.pipelines.preference_extractor import PreferenceExtractionPipeline
from claw_reflect.pipelines.promoter import MemoryPromotionPipeline
from claw_reflect.pipelines.summariser import SummarisationPipeline


class FullReflectionPipeline(BasePipeline):
    """Runs all distillation sub-pipelines sequentially for a complete reflection cycle."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._pipelines: list[BasePipeline] = [
            SummarisationPipeline(session),
            PreferenceExtractionPipeline(session),
            ContradictionDetectionPipeline(session),
            DuplicateCollapsePipeline(session),
            MemoryPromotionPipeline(session),
        ]

    async def run(self, agent_id: str, **kwargs: Any) -> dict[str, Any]:
        """Execute every sub-pipeline for *agent_id* and aggregate the results."""
        results: dict[str, Any] = {}
        for pipeline in self._pipelines:
            name = type(pipeline).__name__
            results[name] = await pipeline.run(agent_id, **kwargs)
        return results
