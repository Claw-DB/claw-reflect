"""Orchestrator pipeline that executes all reflection stages in dependency order."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select

from claw_reflect.llm.prompts import PromptLibrary
from claw_reflect.logging import get_logger
from claw_reflect.models.memory import MemoryRecord
from claw_reflect.pipelines.base import BasePipeline, PipelineContext, PipelineResult
from claw_reflect.pipelines.contradiction_detector import ContradictionDetectionPipeline
from claw_reflect.pipelines.duplicate_collapser import DuplicateCollapsePipeline
from claw_reflect.pipelines.preference_extractor import PreferenceExtractionPipeline
from claw_reflect.pipelines.promoter import MemoryPromotionPipeline
from claw_reflect.pipelines.summariser import SummarisationPipeline
from claw_reflect.scoring.composite import CompositeScorer
from claw_reflect.scoring.confidence import ConfidenceScorer
from claw_reflect.scoring.importance import ImportanceScorer
from claw_reflect.scoring.recency import RecencyScorer

logger = get_logger(__name__)


@dataclass(slots=True)
class FullReflectionResult:
    agent_id: str
    job_id: str
    stage_results: dict[str, PipelineResult]
    total_processed: int
    total_updated: int
    total_archived: int
    total_promoted: int
    contradictions_found: int
    duplicates_collapsed: int
    preferences_extracted: int
    duration_ms: float
    completed_at: datetime


class FullReflectionPipeline(BasePipeline):
    name = "full_reflection"

    async def run(self, ctx: PipelineContext) -> FullReflectionResult:
        started = time.perf_counter()
        stage_results: dict[str, PipelineResult] = {}

        # Stage 1: Score pending memories first.
        try:
            async with self.session_factory() as session:
                pending_result = await session.execute(
                    select(MemoryRecord).where(
                        MemoryRecord.workspace_id == ctx.workspace_id,
                        MemoryRecord.agent_id == ctx.agent_id,
                        MemoryRecord.reflection_status == "pending",
                    )
                )
                pending_memories = list(pending_result.scalars().all())

                importance = ImportanceScorer(self.llm, PromptLibrary())
                recency = RecencyScorer()
                confidence = ConfidenceScorer()
                scorer = CompositeScorer(importance, recency, confidence)
                await scorer.score_batch(pending_memories, session=session, concurrency=10)
                if not ctx.dry_run:
                    await session.commit()

            stage_results["composite_scorer"] = PipelineResult(
                pipeline_name="composite_scorer",
                agent_id=ctx.agent_id,
                job_id=ctx.job_id,
                processed=len(pending_memories),
                updated=len(pending_memories),
                archived=0,
                failed=0,
                duration_ms=0.0,
                details=[],
            )
        except Exception as exc:
            logger.exception("Stage failed", stage="composite_scorer", error=str(exc))

        stages: list[BasePipeline] = [
            DuplicateCollapsePipeline(self.session_factory, self.llm, self.settings),
            ContradictionDetectionPipeline(self.session_factory, self.llm, self.settings),
            SummarisationPipeline(self.session_factory, self.llm, self.settings),
            PreferenceExtractionPipeline(self.session_factory, self.llm, self.settings),
            MemoryPromotionPipeline(self.session_factory, self.llm, self.settings),
        ]

        for pipeline in stages:
            try:
                stage_results[pipeline.name] = await pipeline.run(ctx)
            except Exception as exc:
                logger.exception("Stage failed", stage=pipeline.name, error=str(exc))

        # Rebuild profile from latest preferences at end.
        try:
            async with self.session_factory() as session:
                extractor = PreferenceExtractionPipeline(self.session_factory, self.llm, self.settings)
                if not ctx.dry_run:
                    await extractor.update_agent_profile(session, ctx.workspace_id, ctx.agent_id)
                    await session.commit()
        except Exception as exc:
            logger.exception("Profile update failed", error=str(exc))

        duration_ms = (time.perf_counter() - started) * 1000
        total_processed = sum(result.processed for result in stage_results.values())
        total_updated = sum(result.updated for result in stage_results.values())
        total_archived = sum(result.archived for result in stage_results.values())

        promoter_result = stage_results.get("promoter")
        contradiction_result = stage_results.get("contradiction_detector")
        duplicate_result = stage_results.get("duplicate_collapser")
        preference_result = stage_results.get("preference_extractor")

        return FullReflectionResult(
            agent_id=ctx.agent_id,
            job_id=ctx.job_id,
            stage_results=stage_results,
            total_processed=total_processed,
            total_updated=total_updated,
            total_archived=total_archived,
            total_promoted=promoter_result.updated if promoter_result else 0,
            contradictions_found=contradiction_result.updated if contradiction_result else 0,
            duplicates_collapsed=duplicate_result.archived if duplicate_result else 0,
            preferences_extracted=preference_result.updated if preference_result else 0,
            duration_ms=duration_ms,
            completed_at=datetime.now(UTC),
        )

    async def preview(self, ctx: PipelineContext) -> dict[str, int]:
        dry_ctx = PipelineContext(
            workspace_id=ctx.workspace_id,
            agent_id=ctx.agent_id,
            job_id=ctx.job_id,
            batch_size=ctx.batch_size,
            dry_run=True,
            options=dict(ctx.options),
        )
        result = await self.run(dry_ctx)
        return {
            "processed": result.total_processed,
            "updated": result.total_updated,
            "archived": result.total_archived,
            "promoted": result.total_promoted,
            "contradictions": result.contradictions_found,
            "duplicates": result.duplicates_collapsed,
            "preferences": result.preferences_extracted,
        }
