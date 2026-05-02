"""Celery application factory and beat schedule for claw-reflect background jobs."""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from claw_reflect.config import Settings, settings


def create_celery_app(settings: Settings) -> Celery:
    """Create and configure the Celery application with retry-safe defaults."""
    app = Celery("claw_reflect")
    app.config_from_object(
        {
            "broker_url": settings.redis_url,
            "result_backend": settings.redis_url,
            "task_serializer": "json",
            "result_serializer": "json",
            "accept_content": ["json"],
            "timezone": "UTC",
            "enable_utc": True,
            "task_track_started": True,
            "task_acks_late": True,
            "worker_prefetch_multiplier": 1,
            "task_soft_time_limit": 300,
            "task_time_limit": 360,
            "task_max_retries": 3,
            "task_default_retry_delay": 60,
            "beat_schedule": {
                "decay-cycle": {
                    "task": "claw_reflect.workers.tasks.decay.decay_stale_task",
                    "schedule": crontab(minute=0, hour="*/6"),
                },
                "score-refresh": {
                    "task": "claw_reflect.workers.tasks.score.rescore_memories_task",
                    "schedule": crontab(minute=0, hour="*/12"),
                },
                "profile-update": {
                    "task": "claw_reflect.workers.tasks.profile.update_profile_task",
                    "schedule": crontab(minute=0, hour=2),
                },
            },
        }
    )
    return app


celery_app = create_celery_app(settings)
