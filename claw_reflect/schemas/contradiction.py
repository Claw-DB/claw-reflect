"""Pydantic v2 schemas for contradiction detection and resolution API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class ContradictionOut(BaseModel):
    """Detected contradiction between two memory records as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    agent_id: str
    memory_id_a: str
    memory_id_b: str
    field: str
    value_a: Any
    value_b: Any
    detected_at: datetime
    resolved: bool


class ResolveContradictionRequest(BaseModel):
    """Request body for resolving a detected contradiction."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    contradiction_id: str
    strategy: Literal["keep_a", "keep_b", "merge", "discard_both"]
    merged_value: Any | None = None
