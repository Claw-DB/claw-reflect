"""Pydantic v2 schemas for ReflectionJob and ReflectionResult API contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ReflectionJobCreate(BaseModel):
    """Request body for creating a new reflection job."""

    model_config = ConfigDict(from_attributes=True)

    agent_id: str
    job_type: str = "full"
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
