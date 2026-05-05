"""Celery tasks for triggering agent reflection and full reflection pipeline runs."""

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select

from claw_reflect.config import settings
from claw_reflect.db.session import session_factory
from claw_reflect.llm.anthropic import AnthropicAdapter
from claw_reflect.llm.base import BaseLLMAdapter
from claw_reflect.llm.ollama import OllamaAdapter
from claw_reflect.llm.openai import OpenAIAdapter
from claw_reflect.logging import get_logger
from claw_reflect.models.memory import MemoryRecord
from claw_reflect.models.reflection import ReflectionJob
from claw_reflect.pipelines.base import PipelineContext
from claw_reflect.pipelines.full_reflection import FullReflectionPipeline
from claw_reflect.workers.celery_app import celery_app

logger = get_logger(__name__)


def _new_id() -> str:
    return uuid.uuid4().hex[:26]


def _build_llm_adapter() -> BaseLLMAdapter:
    if settings.llm_provider == "anthropic":
        return AnthropicAdapter(
            api_key=settings.llm_api_key.get_secret_value(),
            model=settings.llm_model,
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout_secs,
        )
    if settings.llm_provider == "ollama":
        return OllamaAdapter(
            model=settings.llm_model,
            base_url=settings.llm_base_url or "http://localhost:11434",
            timeout=settings.llm_timeout_secs,
        )
    return OpenAIAdapter(
        api_key=settings.llm_api_key.get_secret_value(),
        model=settings.llm_model,
        base_url=settings.llm_base_url or "https://api.openai.com",
        timeout=settings.llm_timeout_secs,
    )


@celery_app.task(bind=True, max_retries=3, name="claw_reflect.workers.tasks.reflect.reflect_agent_task")
def reflect_agent_task(
    self: Any,
    workspace_id: str,
    agent_id: str,
    job_type: str = "full",
    options: dict[str, object] | None = None,
) -> dict[str, object]:
    """Create a reflection job row, run pipeline, and persist final status."""

    async def _run() -> dict[str, object]:
        workspace_uuid = UUID(workspace_id)
        async with session_factory() as session:
            job = ReflectionJob(
                id=_new_id(),
                workspace_id=workspace_uuid,
                agent_id=agent_id,
                status="running",
                job_type=job_type,
                started_at=datetime.now(UTC),
                metadata_={"celery_task_id": self.request.id, "options": options or {}},
            )
            session.add(job)
            await session.commit()

        try:
            llm = _build_llm_adapter()
            pipeline = FullReflectionPipeline(session_factory, llm, settings)
            batch_size_value = (options or {}).get("batch_size", settings.reflection_batch_size)
            ctx = PipelineContext(
                workspace_id=workspace_uuid,
                agent_id=agent_id,
                job_id=job.id,
                batch_size=(
                    int(batch_size_value) if isinstance(batch_size_value, (int, float, str)) else settings.reflection_batch_size
                ),
                dry_run=bool((options or {}).get("dry_run", False)),
                options=options or {},
            )
            result = await pipeline.run(ctx)

            async with session_factory() as session:
                stored = await session.get(ReflectionJob, job.id)
                if stored is not None:
                    stored.status = "completed"
                    stored.completed_at = datetime.now(UTC)
                    stored.memories_processed = result.total_processed
                    stored.memories_updated = result.total_updated
                    stored.memories_archived = result.total_archived
                await session.commit()
            return {
                "job_id": job.id,
                "status": "completed",
                "processed": result.total_processed,
                "updated": result.total_updated,
                "archived": result.total_archived,
            }
        except Exception as exc:
            async with session_factory() as session:
                stored = await session.get(ReflectionJob, job.id)
                if stored is not None:
                    stored.status = "failed"
                    stored.completed_at = datetime.now(UTC)
                    stored.error_message = str(exc)
                await session.commit()
            raise exc

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.warning("reflect_agent_task failed, retrying", error=str(exc), retries=self.request.retries)
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))


@celery_app.task(name="claw_reflect.workers.tasks.reflect.full_reflection_task")
def full_reflection_task() -> dict[str, object]:
    """Enqueue per-agent reflection task for each agent with pending memories."""

    async def _run() -> dict[str, object]:
        async with session_factory() as session:
            result = await session.execute(
                select(MemoryRecord.workspace_id, MemoryRecord.agent_id)
                .where(MemoryRecord.reflection_status == "pending")
                .distinct()
            )
            work_agents = [(str(row[0]), row[1]) for row in result.all()]

        for workspace, agent_id in work_agents:
            reflect_agent_task.delay(workspace, agent_id)
        return {"enqueued": len(work_agents), "pairs": work_agents}

    return asyncio.run(_run())
