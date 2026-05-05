"""Preference extraction pipeline."""

from __future__ import annotations

import enum
import time
import uuid
from collections import defaultdict
from datetime import UTC, datetime

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from claw_reflect.llm.prompts import PromptLibrary, parse_json_response
from claw_reflect.models.memory import MemoryRecord
from claw_reflect.models.preference import ExtractedPreference
from claw_reflect.models.profile import AgentProfile
from claw_reflect.models.reflection import ReflectionResult
from claw_reflect.pipelines.base import BasePipeline, PipelineContext, PipelineResult


class PreferenceCategory(enum.StrEnum):
    TOOL_USAGE = "tool_usage"
    COMMUNICATION_STYLE = "communication_style"
    SCHEDULING = "scheduling"
    TECHNICAL = "technical"
    DOMAIN_KNOWLEDGE = "domain_knowledge"
    PERSONAL = "personal"


class PreferenceOutput(BaseModel):
    category: str
    key: str
    value: object
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str


class PreferenceExtractionOutput(BaseModel):
    preferences: list[PreferenceOutput] = Field(default_factory=list)


class PreferenceExtractionPipeline(BasePipeline):
    name = "preference_extractor"

    async def run(self, ctx: PipelineContext) -> PipelineResult:
        started = time.perf_counter()
        processed = updated = archived = failed = 0
        details: list[dict[str, object]] = []

        async with self.session_factory() as session:
            memories = await self.fetch_pending_memories(
                ctx,
                session,
                extra_filters=[MemoryRecord.memory_type != "summary"],
            )

            existing_result = await session.execute(
                select(ExtractedPreference).where(
                    ExtractedPreference.workspace_id == ctx.workspace_id,
                    ExtractedPreference.agent_id == ctx.agent_id,
                    ExtractedPreference.is_active.is_(True),
                )
            )
            existing_prefs = list(existing_result.scalars().all())

            grouped_existing: dict[str, dict[str, object]] = defaultdict(dict)
            for pref in existing_prefs:
                grouped_existing[pref.category][pref.key] = pref.value

            prompt_library = PromptLibrary()
            reflection_results: list[ReflectionResult] = []

            for start_idx in range(0, len(memories), ctx.batch_size):
                chunk = memories[start_idx : start_idx + ctx.batch_size]
                chunk_text = [
                    f"{memory.created_at.isoformat()} [{memory.memory_type}] {self._sanitize_for_prompt(memory.content)}"
                    for memory in chunk
                ]

                try:
                    response = await self.llm.complete_with_retry(
                        messages=prompt_library.extract_preferences(chunk_text, dict(grouped_existing)),
                        max_tokens=min(1024, self.settings.llm_max_tokens),
                        temperature=0.2,
                    )
                    parsed = parse_json_response(response, PreferenceExtractionOutput)
                except Exception as exc:
                    failed += len(chunk)
                    details.append({"chunk": start_idx, "error": str(exc)})
                    continue

                for extracted in parsed.preferences:
                    category = extracted.category.lower()
                    key = extracted.key.strip()

                    existing = await session.scalar(
                        select(ExtractedPreference).where(
                            ExtractedPreference.agent_id == ctx.agent_id,
                            ExtractedPreference.workspace_id == ctx.workspace_id,
                            ExtractedPreference.category == category,
                            ExtractedPreference.key == key,
                            ExtractedPreference.is_active.is_(True),
                        )
                    )

                    now = datetime.now(UTC)
                    if existing is not None:
                        if existing.value == extracted.value:
                            existing.confirmation_count += 1
                            existing.last_confirmed_at = now
                            existing.confidence = max(existing.confidence, extracted.confidence)
                            updated += 1
                            pref_id = existing.id
                        else:
                            existing.is_active = False
                            replacement = ExtractedPreference(
                                id=self.new_id(),
                                workspace_id=ctx.workspace_id,
                                agent_id=ctx.agent_id,
                                category=category,
                                key=key,
                                value=extracted.value,
                                confidence=extracted.confidence,
                                source_memory_ids=[m.id for m in chunk],
                                first_seen_at=now,
                                last_confirmed_at=now,
                                confirmation_count=1,
                                is_active=True,
                            )
                            session.add(replacement)
                            updated += 2
                            pref_id = replacement.id
                    else:
                        created = ExtractedPreference(
                            id=self.new_id(),
                            workspace_id=ctx.workspace_id,
                            agent_id=ctx.agent_id,
                            category=category,
                            key=key,
                            value=extracted.value,
                            confidence=extracted.confidence,
                            source_memory_ids=[m.id for m in chunk],
                            first_seen_at=now,
                            last_confirmed_at=now,
                            confirmation_count=1,
                            is_active=True,
                        )
                        session.add(created)
                        updated += 1
                        pref_id = created.id

                    reflection_results.append(
                        ReflectionResult(
                            id=self.new_id(),
                            job_id=ctx.job_id,
                            workspace_id=ctx.workspace_id,
                            memory_id=chunk[0].id,
                            result_type="preference",
                            output={
                                "preference_id": pref_id,
                                "category": category,
                                "key": key,
                                "value": extracted.value,
                                "reasoning": extracted.reasoning,
                            },
                            confidence=extracted.confidence,
                            applied=not ctx.dry_run,
                        )
                    )

                if not ctx.dry_run:
                    await self.mark_reflected(session, ctx.workspace_id, [m.id for m in chunk])
                processed += len(chunk)

            if not ctx.dry_run:
                await self.save_results(session, reflection_results)
                await self.update_agent_profile(session, ctx.workspace_id, ctx.agent_id)
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

    async def update_agent_profile(self, session: AsyncSession, workspace_id: uuid.UUID, agent_id: str) -> None:
        pref_rows = await session.execute(
            select(ExtractedPreference).where(
                ExtractedPreference.workspace_id == workspace_id,
                ExtractedPreference.agent_id == agent_id,
                ExtractedPreference.is_active.is_(True),
            )
        )
        prefs = list(pref_rows.scalars().all())
        aggregate: dict[str, dict[str, object]] = defaultdict(dict)
        for pref in prefs:
            aggregate[pref.category][pref.key] = pref.value

        profile_row = await session.execute(
            select(AgentProfile).where(
                AgentProfile.workspace_id == workspace_id,
                AgentProfile.agent_id == agent_id,
            )
        )
        profile = profile_row.scalar_one_or_none()
        now = datetime.now(UTC)
        if profile is None:
            profile = AgentProfile(
                workspace_id=workspace_id,
                agent_id=agent_id,
                preferences=dict(aggregate),
                facts={},
                behaviour_patterns={},
                memory_count=len(prefs),
                profile_version=1,
                last_updated_at=now,
            )
            session.add(profile)
            return

        profile.preferences = dict(aggregate)
        profile.profile_version += 1
        profile.memory_count = len(prefs)
        profile.last_updated_at = now

    def _sanitize_for_prompt(self, content: str) -> str:
        """Remove sensitive markers/null bytes and clamp prompt payload length."""
        scrubbed = content.replace("\x00", "")
        lowered = scrubbed.lower()
        for marker in ("x-claw-api-key", "reflect_database_url", "postgresql://", "redis://", "api_key"):
            if marker in lowered:
                scrubbed = scrubbed.replace(marker, "[redacted]")
        return scrubbed[:8192]
