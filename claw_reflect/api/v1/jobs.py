"""Jobs API endpoints — trigger background jobs and query their current status."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from claw_reflect.app_state import get_scheduler
from claw_reflect.db.session import get_session
from claw_reflect.models.reflection import ReflectionJob, ReflectionResult
from fastapi import APIRouter

from claw_reflect.schemas.jobs import JobStatusResponse
from claw_reflect.schemas.reflection import ReflectionJobOut, ReflectionResultOut
from claw_reflect.workers.celery_app import celery_app

router = APIRouter()


def _error(request: Request, status_code: int, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"message": message, "request_id": getattr(request.state, "request_id", "")},
    )


@router.get("/scheduled", summary="List APScheduler jobs")
async def scheduled_jobs() -> list[dict]:
    scheduler = get_scheduler()
    if scheduler is None:
        return []
    return scheduler.get_scheduled_jobs()


@router.get("", summary="List reflection jobs")
async def list_jobs(
    request: Request,
    agent_id: str | None = None,
    status: str | None = None,
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[ReflectionJobOut]:
    stmt = select(ReflectionJob).order_by(ReflectionJob.started_at.desc()).limit(limit).offset(offset)
    if agent_id:
        stmt = stmt.where(ReflectionJob.agent_id == agent_id)
    if status:
        stmt = stmt.where(ReflectionJob.status == status)
    rows = await session.execute(stmt)
    return [ReflectionJobOut.model_validate(job) for job in rows.scalars().all()]


@router.delete("/{job_id}", response_model=JobStatusResponse, summary="Cancel a pending/running job")
async def cancel_job(
    job_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> JobStatusResponse:
    job = await session.get(ReflectionJob, job_id)
    if job is None:
        raise _error(request, 404, "Job not found")
    if job.status not in {"pending", "running"}:
        raise _error(request, 409, "Only pending/running jobs can be canceled")

    task_id = str(job.metadata_.get("celery_task_id", ""))
    if task_id:
        celery_app.control.revoke(task_id, terminate=True)

    job.status = "failed"
    job.error_message = "Canceled by user"
    await session.commit()
    return JobStatusResponse(job_id=job_id, status="canceled", progress_pct=0.0, message="Job canceled")


@router.get("/{job_id}", summary="Get a reflection job and its result rows")
async def get_job_status(
    job_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    job = await session.get(ReflectionJob, job_id)
    if job is None:
        raise _error(request, 404, "Job not found")

    result_rows = await session.execute(select(ReflectionResult).where(ReflectionResult.job_id == job_id))
    results = list(result_rows.scalars().all())
    return {
        "job": ReflectionJobOut.model_validate(job),
        "results": [ReflectionResultOut.model_validate(result) for result in results],
    }
