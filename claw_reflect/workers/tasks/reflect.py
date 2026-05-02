"""Celery tasks for triggering agent reflection and full reflection pipeline runs."""

from __future__ import annotations

from claw_reflect.workers.celery_app import celery_app


@celery_app.task(name="claw_reflect.workers.tasks.reflect.reflect_agent_task")
def reflect_agent_task(agent_id: str, job_type: str = "full") -> dict[str, object]:
    """Trigger a reflection run for *agent_id* using the specified *job_type*."""
    raise NotImplementedError


@celery_app.task(name="claw_reflect.workers.tasks.reflect.full_reflection_task")
def full_reflection_task() -> dict[str, object]:
    """Trigger a full reflection cycle across all agents with pending memories."""
    raise NotImplementedError
