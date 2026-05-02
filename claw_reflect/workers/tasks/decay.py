"""Celery tasks for applying decay to stale memories and archiving expired records."""

import asyncio
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.exc import DBAPIError, OperationalError

from claw_reflect.config import settings
from claw_reflect.db.session import session_factory
from claw_reflect.decay.engine import DecayEngine
from claw_reflect.decay.policy import DecayPolicyRegistry
from claw_reflect.logging import get_logger
from claw_reflect.metrics.instruments import decay_cycles_total, memories_archived_total
from claw_reflect.models.memory import MemoryRecord
from claw_reflect.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(bind=True, name="claw_reflect.workers.tasks.decay.decay_stale_task")
def decay_stale_task(
    self,
    workspace_id: str | None = None,
    agent_id: str | None = None,
) -> dict[str, object]:
    """Run a decay cycle and retry transient DB failures with exponential backoff."""

    async def _run() -> dict[str, object]:
        engine = DecayEngine(session_factory, settings, DecayPolicyRegistry)
        result = await engine.run_decay_cycle(
            workspace_id=UUID(workspace_id) if workspace_id else None,
            agent_id=agent_id,
        )

        label_agent = result.agent_id or "all"
        decay_cycles_total.labels(agent_id=label_agent).inc()
        memories_archived_total.labels(agent_id=label_agent, reason="decay").inc(result.archived)
        logger.info(
            "decay_stale_task completed",
            agent_id=result.agent_id,
            processed=result.processed,
            decayed=result.decayed,
            archived=result.archived,
            skipped_promoted=result.skipped_promoted,
            duration_ms=result.duration_ms,
        )
        return {
            "workspace_id": str(result.workspace_id) if result.workspace_id else None,
            "agent_id": result.agent_id,
            "processed": result.processed,
            "decayed": result.decayed,
            "archived": result.archived,
            "skipped_promoted": result.skipped_promoted,
        }

    try:
        return asyncio.run(_run())
    except (OperationalError, DBAPIError) as exc:
        countdown = min(300, 2 ** (self.request.retries + 1))
        raise self.retry(exc=exc, countdown=countdown)


@celery_app.task(name="claw_reflect.workers.tasks.decay.archive_expired_task")
def archive_expired_task(agent_id: str) -> dict[str, object]:
    """Archive already-low-scoring memories without applying decay formulas."""

    async def _run() -> dict[str, object]:
        async with session_factory() as session:
            result = await session.execute(
                update(MemoryRecord)
                .where(
                    MemoryRecord.agent_id == agent_id,
                    MemoryRecord.reflection_status != "archived",
                    MemoryRecord.composite_score < settings.min_score_to_keep,
                )
                .values(reflection_status="archived")
            )
            await session.commit()
        archived = int(result.rowcount or 0)
        memories_archived_total.labels(agent_id=agent_id, reason="decay").inc(archived)
        return {"agent_id": agent_id, "archived": archived}

    return asyncio.run(_run())
