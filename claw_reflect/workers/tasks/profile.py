"""Celery task for rebuilding the aggregated AgentProfile from reflected memories."""

from __future__ import annotations

from claw_reflect.workers.celery_app import celery_app


@celery_app.task(name="claw_reflect.workers.tasks.profile.update_profile_task")
def update_profile_task(agent_id: str) -> dict[str, object]:
    """Rebuild and persist the AgentProfile for *agent_id* from current memory data."""
    raise NotImplementedError
