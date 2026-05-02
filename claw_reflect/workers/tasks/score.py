"""Celery task for refreshing composite scores across all memory records."""

from __future__ import annotations

from claw_reflect.workers.celery_app import celery_app


@celery_app.task(name="claw_reflect.workers.tasks.score.rescore_memories_task")
def rescore_memories_task() -> dict[str, object]:
    """Recompute composite scores for all memory records and persist the results."""
    raise NotImplementedError
