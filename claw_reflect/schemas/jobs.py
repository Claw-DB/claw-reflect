"""Pydantic v2 schemas for background job trigger and status API endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class JobTriggerRequest(BaseModel):
    """Request body for manually triggering a background reflection job."""

    model_config = ConfigDict(from_attributes=True)

    agent_id: str
    job_type: str
    options: dict[str, Any] = Field(default_factory=dict)


class JobStatusResponse(BaseModel):
    """Current status of a background job, including progress percentage."""

    model_config = ConfigDict(from_attributes=True)

    job_id: str
    status: str
    progress_pct: float
    message: str
