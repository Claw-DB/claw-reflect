"""Pydantic v2 schemas for ReflectionJob and ReflectionResult API contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

IdPattern = Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9_-]{1,128}$")]
JobType = Literal["full", "summarise", "extract", "deduplicate", "score"]


class ReflectionJobCreate(BaseModel):
    """Request body for creating a new reflection job."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    agent_id: IdPattern
    job_type: JobType = "full"
    memory_ids: list[str] | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class ReflectionJobOut(BaseModel):
    """Reflection job as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    agent_id: str
    status: str
    job_type: str
    started_at: datetime | None
    completed_at: datetime | None
    memories_processed: int
    memories_updated: int
    memories_archived: int
    error_message: str | None


class ReflectionResultOut(BaseModel):
    """Single pipeline result record as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    job_id: str
    memory_id: str
    result_type: str
    output: dict[str, Any]
    confidence: float
    applied: bool
