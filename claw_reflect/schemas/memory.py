"""Pydantic v2 schemas for MemoryRecord ingest and API output."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MemoryRecordIn(BaseModel):
    """Payload used when ingesting a memory record from claw-core."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    agent_id: str
    content: str
    memory_type: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class MemoryRecordOut(MemoryRecordIn):
    """Full memory record as returned by the API, including scoring metadata."""

    importance_score: float = 0.5
    recency_score: float = 1.0
    confidence_score: float = 0.8
    composite_score: float = 0.5
    reflection_status: str = "pending"
    is_promoted: bool = False


class MemoryBatch(BaseModel):
    """A batch of memory records belonging to a single agent."""

    model_config = ConfigDict(from_attributes=True)

    agent_id: str
    memories: list[MemoryRecordIn]
    batch_id: str
