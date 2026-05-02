"""Duplicate detection and collapsing pipeline."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

from pydantic import BaseModel, Field
from sqlalchemy import select

from claw_reflect.llm.prompts import PromptLibrary, parse_json_response
from claw_reflect.models.memory import MemoryRecord
from claw_reflect.models.reflection import ReflectionResult
from claw_reflect.pipelines.base import BasePipeline, PipelineContext, PipelineResult


class DuplicateOutput(BaseModel):
    is_duplicate: bool
    similarity_score: float = Field(ge=0.0, le=1.0)
    keep_which: str
    merged_content: str | None = None


class DuplicateCollapsePipeline(BasePipeline):
    name = "duplicate_collapser"

    async def run(self, ctx: PipelineContext) -> PipelineResult:
        started = time.perf_counter()
        processed = updated = archived = failed = 0
        details: list[dict] = []

        async with self.session_factory() as session:
            result = await session.execute(
                select(MemoryRecord)
                .where(
                    MemoryRecord.agent_id == ctx.agent_id,
                    MemoryRecord.reflection_status != "archived",
                )
                .order_by(MemoryRecord.created_at.desc())
                .limit(500)
            )
            memories = list(result.scalars().all())

            candidates: list[tuple[MemoryRecord, MemoryRecord]] = []
            for i, memory_a in enumerate(memories):
                for memory_b in memories[i + 1 :]:
                    if self.is_candidate_pair(memory_a, memory_b):
                        candidates.append((memory_a, memory_b))
                    if len(candidates) >= 100:
                        break
                if len(candidates) >= 100:
                    break

            semaphore = asyncio.Semaphore(3)
            prompt_library = PromptLibrary()
            reflection_results: list[ReflectionResult] = []

            async def _check_pair(pair: tuple[MemoryRecord, MemoryRecord]) -> tuple[tuple[MemoryRecord, MemoryRecord], DuplicateOutput | None, Exception | None]:
                memory_a, memory_b = pair
                async with semaphore:
                    try:
                        response = await self.llm.complete_with_retry(
                            messages=prompt_library.check_duplicate(memory_a.content, memory_b.content),
                            max_tokens=min(256, self.settings.llm_max_tokens),
                            temperature=0.0,
                        )
                        parsed = parse_json_response(response, DuplicateOutput)
                        return pair, parsed, None
                    except Exception as exc:
                        return pair, None, exc

            checks = await asyncio.gather(*(_check_pair(pair) for pair in candidates))
            for (memory_a, memory_b), parsed, err in checks:
                processed += 1
                if err is not None or parsed is None:
                    failed += 1
                    details.append({"pair": [memory_a.id, memory_b.id], "error": str(err)})
                    continue

                if not parsed.is_duplicate:
                    continue
                if parsed.similarity_score < self.settings.duplicate_similarity_threshold:
                    continue

                updated += 1
                if parsed.keep_which == "a":
                    keeper = memory_a
                    to_archive = [memory_b]
                elif parsed.keep_which == "b":
                    keeper = memory_b
                    to_archive = [memory_a]
                else:
                    keeper = self.choose_keeper(memory_a, memory_b)
                    to_archive = [memory_a, memory_b]

                if not ctx.dry_run:
                    if parsed.keep_which == "merge" and parsed.merged_content:
                        merged = MemoryRecord(
                            id=self.new_id(),
                            agent_id=ctx.agent_id,
                            content=parsed.merged_content,
                            memory_type=keeper.memory_type,
                            metadata_={"merged_from": [memory_a.id, memory_b.id], "pipeline": self.name},
                            tags=list(set((memory_a.tags or []) + (memory_b.tags or []))),
                            reflection_status="reflected",
                            created_at=datetime.now(timezone.utc),
                            updated_at=datetime.now(timezone.utc),
                        )
                        session.add(merged)

                    await self.mark_archived(session, [m.id for m in to_archive])
                    archived += len(to_archive)

                    reflection_results.append(
                        ReflectionResult(
                            id=self.new_id(),
                            job_id=ctx.job_id,
                            memory_id=keeper.id,
                            result_type="duplicate",
                            output={
                                "memory_a": memory_a.id,
                                "memory_b": memory_b.id,
                                "keep_which": parsed.keep_which,
                                "similarity_score": parsed.similarity_score,
                            },
                            confidence=parsed.similarity_score,
                            applied=True,
                        )
                    )

            if not ctx.dry_run:
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

    def jaccard_similarity(self, a: str, b: str) -> float:
        tokens_a = set(a.lower().split())
        tokens_b = set(b.lower().split())
        if not tokens_a and not tokens_b:
            return 1.0
        union = tokens_a | tokens_b
        if not union:
            return 0.0
        return len(tokens_a & tokens_b) / len(union)

    def length_ratio(self, a: str, b: str) -> float:
        la = max(len(a), 1)
        lb = max(len(b), 1)
        return min(la, lb) / max(la, lb)

    def is_candidate_pair(self, a: MemoryRecord, b: MemoryRecord) -> bool:
        if a.agent_id != b.agent_id:
            return False
        if a.memory_type != b.memory_type:
            return False
        if a.reflection_status == "archived" or b.reflection_status == "archived":
            return False
        return self.jaccard_similarity(a.content, b.content) >= 0.5 and self.length_ratio(a.content, b.content) >= 0.6

    def choose_keeper(self, a: MemoryRecord, b: MemoryRecord) -> MemoryRecord:
        if a.composite_score != b.composite_score:
            return a if a.composite_score > b.composite_score else b
        if a.created_at != b.created_at:
            return a if a.created_at > b.created_at else b
        return a if len(a.content) >= len(b.content) else b
