"""Base abstractions shared by all reflection pipelines."""

from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, ClassVar

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from claw_reflect.config import Settings
from claw_reflect.logging import get_logger
from claw_reflect.metrics import instruments
from claw_reflect.models.memory import MemoryRecord
from claw_reflect.models.reflection import ReflectionResult

logger = get_logger(__name__)


@dataclass(slots=True)
class PipelineContext:
    agent_id: str
    job_id: str
    batch_size: int
    workspace_id: uuid.UUID = field(default_factory=lambda: uuid.UUID("00000000-0000-0000-0000-000000000000"))
    dry_run: bool = False
    options: dict = field(default_factory=dict)


@dataclass(slots=True)
class PipelineResult:
    pipeline_name: str
    agent_id: str
    job_id: str
    processed: int
    updated: int
    archived: int
    failed: int
    duration_ms: float
    details: list[dict]


class BasePipeline(ABC):
    name: ClassVar[str]

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        llm: Any,
        settings: Settings,
    ) -> None:
        self.session_factory = session_factory
        self.llm = llm
        self.settings = settings

    @abstractmethod
    async def run(self, ctx: PipelineContext) -> PipelineResult: ...

    async def fetch_pending_memories(
        self,
        ctx: PipelineContext,
        session: AsyncSession,
        extra_filters: list[Any] | None = None,
    ) -> list[MemoryRecord]:
        where = [
            MemoryRecord.workspace_id == ctx.workspace_id,
            MemoryRecord.agent_id == ctx.agent_id,
            MemoryRecord.reflection_status == "pending",
        ]
        if extra_filters:
            where.extend(extra_filters)

        result = await session.execute(
            select(MemoryRecord).where(and_(*where)).order_by(MemoryRecord.created_at.asc()).limit(ctx.batch_size)
        )
        return list(result.scalars().all())

    async def mark_reflected(self, session: AsyncSession, memory_ids: list[str]) -> None:
        if not memory_ids:
            return
        await session.execute(
            update(MemoryRecord)
            .where(MemoryRecord.id.in_(memory_ids))
            .values(
                reflection_status="reflected",
                reflection_count=MemoryRecord.reflection_count + 1,
                last_reflected_at=datetime.now(UTC),
            )
        )

    async def mark_archived(self, session: AsyncSession, memory_ids: list[str]) -> None:
        if not memory_ids:
            return
        await session.execute(update(MemoryRecord).where(MemoryRecord.id.in_(memory_ids)).values(reflection_status="archived"))

    def emit_metric(self, name: str, value: float, labels: dict) -> None:
        if name == "reflection_memories_processed_total":
            instruments.reflection_memories_processed_total.labels(**labels).inc(value)
        elif name == "reflection_duration_seconds":
            instruments.reflection_duration_seconds.labels(**labels).observe(value)
        elif name == "archived_memories_total":
            instruments.archived_memories_total.inc(value)

    async def save_results(self, session: AsyncSession, results: list[ReflectionResult]) -> None:
        if not results:
            return
        session.add_all(results)

    @asynccontextmanager
    async def timed_step(self, step_name: str):
        started = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.info("Pipeline step finished", pipeline=self.name, step=step_name, duration_ms=elapsed_ms)

    @staticmethod
    def new_id() -> str:
        return uuid.uuid4().hex[:26]
