"""Pydantic v2 schemas for MemoryRecord ingest and API output."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

IdPattern = Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9_-]{1,128}$")]
MemoryContent = Annotated[str, StringConstraints(max_length=65536)]


class MemoryRecordIn(BaseModel):
    """Payload used when ingesting a memory record from claw-core."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: str
    agent_id: IdPattern
    content: MemoryContent
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

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    agent_id: IdPattern
    memories: list[MemoryRecordIn]
    batch_id: IdPattern
