"""Pydantic v2 schemas for background job trigger and status API endpoints."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

IdPattern = Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9_-]{1,128}$")]
JobType = Literal["full", "summarise", "extract", "deduplicate", "score"]


class JobTriggerRequest(BaseModel):
    """Request body for manually triggering a background reflection job."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    agent_id: IdPattern
    job_type: JobType
    options: dict[str, Any] = Field(default_factory=dict)


class JobStatusResponse(BaseModel):
    """Current status of a background job, including progress percentage."""

    model_config = ConfigDict(from_attributes=True)

    job_id: str
    status: str
    progress_pct: float
    message: str
