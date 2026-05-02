"""Celery application factory and beat schedule for claw-reflect background jobs."""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from claw_reflect.config import settings


def create_celery_app() -> Celery:
    """Create and configure the Celery application with the beat schedule."""
    app = Celery("claw_reflect", broker=settings.redis_url, backend=settings.redis_url)

    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        worker_concurrency=settings.celery_concurrency,
        beat_schedule={
            "full-reflection-every-interval": {
                "task": "claw_reflect.workers.tasks.reflect.full_reflection_task",
                "schedule": crontab(
                    minute=f"*/{settings.reflection_interval_minutes}"
                ),
            },
            "decay-stale-memories": {
                "task": "claw_reflect.workers.tasks.decay.decay_stale_task",
                "schedule": crontab(minute=0, hour=f"*/{settings.decay_interval_hours}"),
            },
            "rescore-memories": {
                "task": "claw_reflect.workers.tasks.score.rescore_memories_task",
                "schedule": crontab(
                    minute=0, hour=f"*/{settings.score_refresh_interval_hours}"
                ),
            },
        },
    )
    return app


celery_app = create_celery_app()
