"""APScheduler-based coordinator for decay and reflection scheduling."""

from __future__ import annotations

from datetime import UTC

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import distinct, select

from claw_reflect.config import Settings
from claw_reflect.decay.engine import DecayEngine
from claw_reflect.logging import get_logger
from claw_reflect.metrics import instruments
from claw_reflect.models.memory import MemoryRecord
from claw_reflect.pipelines.full_reflection import FullReflectionPipeline

logger = get_logger(__name__)


class ReflectScheduler:
    def __init__(
        self,
        settings: Settings,
        decay_engine: DecayEngine,
        reflection_pipeline: FullReflectionPipeline,
    ) -> None:
        self.settings = settings
        self.decay_engine = decay_engine
        self.reflection_pipeline = reflection_pipeline
        self._scheduler = AsyncIOScheduler(timezone=UTC)

    def start(self) -> None:
        self._scheduler.add_job(
            self._run_decay_cycle,
            trigger=CronTrigger(hour=f"*/{self.settings.decay_interval_hours}"),
            id="decay_cycle",
            replace_existing=True,
        )
        self._scheduler.add_job(
            self._run_reflection_all_agents,
            trigger=CronTrigger(minute=f"*/{self.settings.reflection_interval_minutes}"),
            id="reflection_all_agents",
            replace_existing=True,
        )
        self._scheduler.add_job(
            self._run_score_refresh,
            trigger=CronTrigger(hour=f"*/{self.settings.score_refresh_interval_hours}"),
            id="score_refresh",
            replace_existing=True,
        )
        self._scheduler.add_job(
            self._run_profile_update,
            trigger=CronTrigger(hour=2, minute=0),
            id="profile_update",
            replace_existing=True,
        )
        self._scheduler.start()
        logger.info("ReflectScheduler started")

    def stop(self) -> None:
        self._scheduler.shutdown(wait=True)

    async def _run_decay_cycle(self) -> None:
        try:
            result = await self.decay_engine.run_decay_cycle(agent_id=None)
            instruments.archived_memories_total.inc(result.archived)
            logger.info("Decay cycle completed", archived=result.archived, processed=result.processed)
        except Exception as exc:
            logger.exception("decay_cycle job failed", error=str(exc))

    async def _run_reflection_all_agents(self) -> None:
        try:
            from claw_reflect.workers.tasks.reflect import reflect_agent_task

            async with self.decay_engine.session_factory() as session:
                result = await session.execute(
                    select(distinct(MemoryRecord.workspace_id), MemoryRecord.agent_id).where(
                        MemoryRecord.reflection_status == "pending"
                    )
                )
                workspace_agent_pairs = [(str(row[0]), row[1]) for row in result.all()]

            for workspace_id, agent_id in workspace_agent_pairs:
                reflect_agent_task.delay(workspace_id, agent_id)
            logger.info("Reflection enqueue complete", agents=len(workspace_agent_pairs))
        except Exception as exc:
            logger.exception("reflection_all_agents job failed", error=str(exc))

    async def _run_score_refresh(self) -> None:
        try:
            from claw_reflect.workers.tasks.score import rescore_memories_task

            rescore_memories_task.delay()
            logger.info("Score refresh enqueued")
        except Exception as exc:
            logger.exception("score_refresh job failed", error=str(exc))

    async def _run_profile_update(self) -> None:
        try:
            from claw_reflect.workers.tasks.profile import update_profile_task

            async with self.decay_engine.session_factory() as session:
                result = await session.execute(select(distinct(MemoryRecord.workspace_id), MemoryRecord.agent_id))
                workspace_agent_pairs = [(str(row[0]), row[1]) for row in result.all()]

            for workspace_id, agent_id in workspace_agent_pairs:
                update_profile_task.delay(workspace_id, agent_id)
            logger.info("Profile updates enqueued", agents=len(workspace_agent_pairs))
        except Exception as exc:
            logger.exception("profile_update job failed", error=str(exc))

    def get_scheduled_jobs(self) -> list[dict]:
        jobs = []
        for job in self._scheduler.get_jobs():
            jobs.append(
                {
                    "id": job.id,
                    "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                    "trigger": str(job.trigger),
                }
            )
        return jobs
