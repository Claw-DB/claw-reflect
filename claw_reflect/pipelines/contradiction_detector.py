"""Contradiction detection pipeline."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from claw_reflect.llm.prompts import PromptLibrary, parse_json_response
from claw_reflect.models.contradiction import ContradictionRecord
from claw_reflect.models.memory import MemoryRecord
from claw_reflect.pipelines.base import BasePipeline, PipelineContext, PipelineResult


class ContradictionOutput(BaseModel):
    contradicts: bool
    field: str | None = None
    explanation: str
    confidence: float = Field(ge=0.0, le=1.0)


class ContradictionDetectionPipeline(BasePipeline):
    name = "contradiction_detector"

    async def run(self, ctx: PipelineContext) -> PipelineResult:
        started = time.perf_counter()
        processed = updated = archived = failed = 0
        details: list[dict] = []

        async with self.session_factory() as session:
            since = datetime.now(UTC) - timedelta(days=7)
            result = await session.execute(
                select(MemoryRecord)
                .where(
                    MemoryRecord.workspace_id == ctx.workspace_id,
                    MemoryRecord.agent_id == ctx.agent_id,
                    MemoryRecord.created_at >= since,
                    MemoryRecord.reflection_status.in_(["pending", "reflected"]),
                )
                .order_by(MemoryRecord.created_at.desc())
            )
            memories = list(result.scalars().all())

            pairs = self.generate_candidate_pairs(memories)[:200]
            prompt_library = PromptLibrary()

            for memory_a, memory_b in pairs:
                if len(memory_a.content.strip()) < 20 and len(memory_b.content.strip()) < 20:
                    continue

                existing = await session.scalar(
                    select(ContradictionRecord.id).where(
                        ContradictionRecord.workspace_id == ctx.workspace_id,
                        ContradictionRecord.agent_id == ctx.agent_id,
                        or_(
                            and_(
                                ContradictionRecord.memory_id_a == memory_a.id,
                                ContradictionRecord.memory_id_b == memory_b.id,
                            ),
                            and_(
                                ContradictionRecord.memory_id_a == memory_b.id,
                                ContradictionRecord.memory_id_b == memory_a.id,
                            ),
                        ),
                    )
                )
                if existing:
                    continue

                try:
                    response = await self.llm.complete_with_retry(
                        messages=prompt_library.detect_contradictions(memory_a.content, memory_b.content),
                        max_tokens=min(256, self.settings.llm_max_tokens),
                        temperature=0.0,
                    )
                    parsed = parse_json_response(response, ContradictionOutput)
                except Exception as exc:
                    failed += 1
                    details.append({"pair": [memory_a.id, memory_b.id], "error": str(exc)})
                    continue

                processed += 1
                if parsed.contradicts and parsed.confidence >= 0.7:
                    updated += 1
                    details.append(
                        {
                            "memory_a": memory_a.id,
                            "memory_b": memory_b.id,
                            "field": parsed.field,
                            "confidence": parsed.confidence,
                        }
                    )
                    if not ctx.dry_run:
                        contradiction = ContradictionRecord(
                            id=self.new_id(),
                            workspace_id=ctx.workspace_id,
                            agent_id=ctx.agent_id,
                            memory_id_a=memory_a.id,
                            memory_id_b=memory_b.id,
                            field=parsed.field or "general",
                            value_a=memory_a.content,
                            value_b=memory_b.content,
                            resolved=False,
                        )
                        session.add(contradiction)
                        self.emit_metric("contradiction_detected", 1, {"pipeline": self.name})

            if not ctx.dry_run:
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

    def generate_candidate_pairs(self, memories: list[MemoryRecord]) -> list[tuple[MemoryRecord, MemoryRecord]]:
        by_type: dict[str, list[MemoryRecord]] = {}
        for memory in memories:
            by_type.setdefault(memory.memory_type, []).append(memory)

        pairs: list[tuple[MemoryRecord, MemoryRecord]] = []
        seen: set[frozenset[str]] = set()
        for grouped in by_type.values():
            for idx, memory_a in enumerate(grouped):
                for memory_b in grouped[idx + 1 :]:
                    key = frozenset({memory_a.id, memory_b.id})
                    if key in seen:
                        continue
                    seen.add(key)
                    pairs.append((memory_a, memory_b))
        return pairs

    async def auto_resolve_obvious(self, session: AsyncSession, contradiction: ContradictionRecord) -> bool:
        memory_a = await session.get(MemoryRecord, contradiction.memory_id_a)
        memory_b = await session.get(MemoryRecord, contradiction.memory_id_b)
        if memory_a is None or memory_b is None:
            return False

        if memory_a.reflection_status == "archived" and memory_b.reflection_status != "archived":
            contradiction.resolved = True
            contradiction.resolution_strategy = "keep_b"
            contradiction.resolved_at = datetime.now(UTC)
            contradiction.winner_memory_id = memory_b.id
            return True

        if memory_b.reflection_status == "archived" and memory_a.reflection_status != "archived":
            contradiction.resolved = True
            contradiction.resolution_strategy = "keep_a"
            contradiction.resolved_at = datetime.now(UTC)
            contradiction.winner_memory_id = memory_a.id
            return True

        return False
