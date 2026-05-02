"""Celery tasks for applying decay to stale memories and archiving expired records."""

from __future__ import annotations

from claw_reflect.workers.celery_app import celery_app


@celery_app.task(name="claw_reflect.workers.tasks.decay.decay_stale_task")
def decay_stale_task() -> dict[str, object]:
    """Apply the configured decay policy to all memory records due for decay."""
    raise NotImplementedError


@celery_app.task(name="claw_reflect.workers.tasks.decay.archive_expired_task")
def archive_expired_task() -> dict[str, object]:
    """Archive memory records whose composite score has fallen below the archive threshold."""
    raise NotImplementedError
