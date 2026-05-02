"""Memory promotion pipeline."""

from __future__ import annotations

import time
from datetime import UTC, datetime

from sqlalchemy import or_, select

from claw_reflect.models.contradiction import ContradictionRecord
from claw_reflect.models.memory import MemoryRecord
from claw_reflect.models.reflection import ReflectionResult
from claw_reflect.pipelines.base import BasePipeline, PipelineContext, PipelineResult


class MemoryPromotionPipeline(BasePipeline):
    name = "promoter"
    PROMOTION_THRESHOLD: float = 0.75
    DEMOTION_THRESHOLD: float = 0.40

    async def run(self, ctx: PipelineContext) -> PipelineResult:
        started = time.perf_counter()
        processed = updated = archived = failed = 0
        details: list[dict] = []

        async with self.session_factory() as session:
            result = await session.execute(
                select(MemoryRecord)
                .where(
                    MemoryRecord.workspace_id == ctx.workspace_id,
                    MemoryRecord.agent_id == ctx.agent_id,
                    MemoryRecord.is_promoted.is_(False),
                    MemoryRecord.reflection_status == "reflected",
                    MemoryRecord.composite_score >= self.PROMOTION_THRESHOLD,
                    MemoryRecord.confidence_score >= 0.7,
                    MemoryRecord.reflection_count >= 1,
                )
                .order_by(MemoryRecord.composite_score.desc())
                .limit(ctx.batch_size)
            )
            candidates = list(result.scalars().all())

            reflection_results: list[ReflectionResult] = []
            for memory in candidates:
                processed += 1
                unresolved = await session.scalar(
                    select(ContradictionRecord.id)
                    .where(
                        ContradictionRecord.workspace_id == ctx.workspace_id,
                        ContradictionRecord.resolved.is_(False),
                        or_(
                            ContradictionRecord.memory_id_a == memory.id,
                            ContradictionRecord.memory_id_b == memory.id,
                        ),
                    )
                    .limit(1)
                )
                if unresolved:
                    continue

                if bool(memory.metadata_.get("decay_marked", False)):
                    continue

                if not ctx.dry_run:
                    memory.is_promoted = True
                    memory.promoted_at = datetime.now(UTC)
                    reflection_results.append(
                        ReflectionResult(
                            id=self.new_id(),
                            job_id=ctx.job_id,
                            workspace_id=ctx.workspace_id,
                            memory_id=memory.id,
                            result_type="promotion",
                            output={"promoted": True, "composite_score": memory.composite_score},
                            confidence=memory.confidence_score,
                            applied=True,
                        )
                    )
                updated += 1
                details.append({"memory_id": memory.id, "score": memory.composite_score})

            if not ctx.dry_run:
                await self.demote_stale_promoted(ctx, session)
                await self.save_results(session, reflection_results)
                await session.commit()

        duration_ms = (time.perf_counter() - started) * 1000
        return PipelineResult(
            pipeline_name=self.name,
            agent_id=ctx.agent_id,
            job_id=ctx.job_id,
            processed=processed,
            updated=updated,
            archived=archived,
            failed=failed,
            duration_ms=duration_ms,
            details=details,
        )

    async def demote_stale_promoted(self, ctx: PipelineContext, session) -> None:
        result = await session.execute(
            select(MemoryRecord).where(
                MemoryRecord.workspace_id == ctx.workspace_id,
                MemoryRecord.agent_id == ctx.agent_id,
                MemoryRecord.is_promoted.is_(True),
                MemoryRecord.composite_score < self.DEMOTION_THRESHOLD,
            )
        )
        stale = list(result.scalars().all())
        for memory in stale:
            memory.is_promoted = False
            memory.promoted_at = None
