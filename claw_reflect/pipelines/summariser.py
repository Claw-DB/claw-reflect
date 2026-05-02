"""Session summarisation pipeline."""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timezone

from pydantic import BaseModel, Field
from sqlalchemy import select

from claw_reflect.llm.context import ContextWindowManager
from claw_reflect.llm.prompts import PromptLibrary, parse_json_response
from claw_reflect.models.memory import MemoryRecord
from claw_reflect.models.reflection import ReflectionResult
from claw_reflect.pipelines.base import BasePipeline, PipelineContext, PipelineResult


class SummaryOutput(BaseModel):
    summary: str
    key_facts: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class SummarisationPipeline(BasePipeline):
    name = "summariser"

    async def run(self, ctx: PipelineContext) -> PipelineResult:
        started = time.perf_counter()
        processed = updated = archived = failed = 0
        details: list[dict] = []

        async with self.session_factory() as session:
            memories = await self.fetch_pending_memories(
                ctx,
                session,
                extra_filters=[MemoryRecord.memory_type.in_(["message", "context", "session"])],
            )

            grouped: dict[str, list[MemoryRecord]] = defaultdict(list)
            for memory in memories:
                session_id = str(memory.metadata_.get("session_id", "default"))
                grouped[session_id].append(memory)

            cwm = ContextWindowManager(
                model=self.llm.model_name,
                max_context_tokens=100_000,
                max_output_tokens=self.settings.llm_max_tokens,
            )
            prompt_lib = PromptLibrary()
            reflection_results: list[ReflectionResult] = []

            for session_id, group in grouped.items():
                batch = sorted(group, key=lambda m: m.created_at)[: ctx.batch_size]
                memories_text = self.format_memories_for_prompt(batch)
                raw_lines = memories_text.splitlines()

                messages = prompt_lib.summarise_session(raw_lines, ctx.agent_id)
                messages = cwm.truncate_to_fit(messages, reserve_output=min(1024, self.settings.llm_max_tokens))

                try:
                    response = await self.llm.complete_with_retry(
                        messages=messages,
                        max_tokens=min(512, self.settings.llm_max_tokens),
                        temperature=0.2,
                    )
                    parsed = parse_json_response(response, SummaryOutput)
                    processed += len(batch)
                    quality = self.estimate_summary_quality(parsed.summary, batch)

                    details.append(
                        {
                            "session_id": session_id,
                            "summary_quality": quality,
                            "summary_confidence": parsed.confidence,
                            "memory_count": len(batch),
                        }
                    )

                    if not ctx.dry_run:
                        summary_memory = MemoryRecord(
                            id=self.new_id(),
                            agent_id=ctx.agent_id,
                            content=parsed.summary,
                            memory_type="summary",
                            metadata_={
                                "source_session_id": session_id,
                                "key_facts": parsed.key_facts,
                                "summary_quality": quality,
                                "pipeline": self.name,
                            },
                            tags=parsed.topics,
                            confidence_score=parsed.confidence,
                            reflection_status="reflected",
                            created_at=datetime.now(timezone.utc),
                            updated_at=datetime.now(timezone.utc),
                        )
                        session.add(summary_memory)

                        archived_ids = [m.id for m in batch]
                        await self.mark_archived(session, archived_ids)
                        archived += len(archived_ids)
                        updated += 1

                        reflection_results.extend(
                            ReflectionResult(
                                id=self.new_id(),
                                job_id=ctx.job_id,
                                memory_id=memory_id,
                                result_type="summary",
                                output={
                                    "summary_memory_id": summary_memory.id,
                                    "topics": parsed.topics,
                                    "confidence": parsed.confidence,
                                },
                                confidence=parsed.confidence,
                                applied=True,
                            )
                            for memory_id in archived_ids
                        )
                except Exception as exc:
                    failed += len(batch)
                    details.append({"session_id": session_id, "error": str(exc)})

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

    def format_memories_for_prompt(self, memories: list[MemoryRecord]) -> str:
        ordered = sorted(memories, key=lambda m: m.created_at)
        lines = [
            f"{m.created_at.isoformat()} [{m.memory_type}]: {m.content.strip()}"
            for m in ordered
        ]
        return "\n".join(lines)

    def estimate_summary_quality(self, summary: str, original_memories: list[MemoryRecord]) -> float:
        original_len = sum(len(m.content) for m in original_memories) or 1
        ratio = len(summary) / original_len
        if 0.1 <= ratio <= 0.3:
            return 1.0
        distance = min(abs(ratio - 0.2), 1.0)
        return max(0.0, 1.0 - distance * 2.5)
