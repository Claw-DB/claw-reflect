"""Jobs API endpoints — trigger background jobs and query their current status."""

from __future__ import annotations

from fastapi import APIRouter

from claw_reflect.schemas.jobs import JobStatusResponse, JobTriggerRequest

router = APIRouter()


@router.post("/trigger", response_model=JobStatusResponse, summary="Trigger a background job")
async def trigger_job(body: JobTriggerRequest) -> JobStatusResponse:
    """Manually trigger a background job for the specified agent and job type."""
    raise NotImplementedError


@router.get("/{job_id}", response_model=JobStatusResponse, summary="Get job status")
async def get_job_status(job_id: str) -> JobStatusResponse:
    """Return the current status and progress of the specified background job."""
    raise NotImplementedError
