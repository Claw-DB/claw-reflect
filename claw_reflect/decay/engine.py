"""Decay engine for applying policy-driven score decay."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from claw_reflect.config import Settings
from claw_reflect.decay.policy import DecayPolicyRegistry
from claw_reflect.models.decay import DecayRecord
from claw_reflect.models.memory import MemoryRecord


@dataclass(slots=True)
class DecayPreview:
    memory_id: str
    current_score: float
    projected_score: float
    would_archive: bool
    policy_used: str


@dataclass(slots=True)
class DecayCycleResult:
    agent_id: str | None
    processed: int
    decayed: int
    archived: int
    skipped_promoted: int
    duration_ms: float
    run_at: datetime


class DecayEngine:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        policy_registry: DecayPolicyRegistry,
    ) -> None:
        self.session_factory = session_factory
        self.settings = settings
        self.policy_registry = policy_registry

    async def run_decay_cycle(self, agent_id: str | None = None) -> DecayCycleResult:
        started = time.perf_counter()
        processed = decayed = archived = skipped_promoted = 0
        now = datetime.now(timezone.utc)

        async with self.session_factory() as session:
            offset = 0
            while True:
                query = select(MemoryRecord).where(MemoryRecord.reflection_status != "archived")
                if agent_id:
                    query = query.where(MemoryRecord.agent_id == agent_id)

                page = await session.execute(query.order_by(MemoryRecord.created_at.asc()).offset(offset).limit(500))
                memories = list(page.scalars().all())
                if not memories:
                    break

                for memory in memories:
                    processed += 1
                    if memory.is_promoted:
                        skipped_promoted += 1
                        continue

                    policy_name = str(memory.metadata_.get("decay_policy", self.settings.default_decay_policy))
                    policy = self.policy_registry.get(policy_name)
                    created_at = memory.created_at if memory.created_at.tzinfo else memory.created_at.replace(tzinfo=timezone.utc)
                    age_days = max(0.0, (now - created_at).total_seconds() / 86_400)
                    score_before = memory.composite_score
                    new_score = policy.compute(score_before, age_days)

                    memory.composite_score = new_score
                    decayed += 1

                    became_archived = new_score < self.settings.archive_threshold_score
                    if became_archived:
                        memory.reflection_status = "archived"
                        archived += 1

                    session.add(
                        DecayRecord(
                            id=self._new_id(),
                            memory_id=memory.id,
                            agent_id=memory.agent_id,
                            decay_policy=policy_name,
                            score_before=score_before,
                            score_after=new_score,
                            archived=became_archived,
                        )
                    )

                offset += len(memories)

            await session.commit()

        return DecayCycleResult(
            agent_id=agent_id,
            processed=processed,
            decayed=decayed,
            archived=archived,
            skipped_promoted=skipped_promoted,
            duration_ms=(time.perf_counter() - started) * 1000,
            run_at=now,
        )

    async def preview_decay(self, agent_id: str) -> list[DecayPreview]:
        now = datetime.now(timezone.utc)
        previews: list[DecayPreview] = []
        async with self.session_factory() as session:
            result = await session.execute(
                select(MemoryRecord).where(
                    MemoryRecord.agent_id == agent_id,
                    MemoryRecord.reflection_status != "archived",
                )
            )
            memories = list(result.scalars().all())

            for memory in memories:
                if memory.is_promoted:
                    continue
                policy_name = str(memory.metadata_.get("decay_policy", self.settings.default_decay_policy))
                policy = self.policy_registry.get(policy_name)
                created_at = memory.created_at if memory.created_at.tzinfo else memory.created_at.replace(tzinfo=timezone.utc)
                age_days = max(0.0, (now - created_at).total_seconds() / 86_400)
                projected = policy.compute(memory.composite_score, age_days)
                previews.append(
                    DecayPreview(
                        memory_id=memory.id,
                        current_score=memory.composite_score,
                        projected_score=projected,
                        would_archive=projected < self.settings.archive_threshold_score,
                        policy_used=policy_name,
                    )
                )

        return previews

    async def restore_memory(self, memory_id: str, reason: str) -> bool:
        async with self.session_factory() as session:
            memory = await session.get(MemoryRecord, memory_id)
            if memory is None:
                return False

            previous = float(memory.metadata_.get("previous_composite_score", memory.composite_score))
            memory.reflection_status = "reflected"
            memory.composite_score = max(0.5, previous)
            memory.metadata_["restored_reason"] = reason
            memory.updated_at = datetime.now(timezone.utc)

            await session.commit()
            return True

    @staticmethod
    def _new_id() -> str:
        import uuid

        return uuid.uuid4().hex[:26]
