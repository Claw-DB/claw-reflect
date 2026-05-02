"""Pydantic v2 schemas for agent preference extraction API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class PreferenceOut(BaseModel):
    """Single extracted preference as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    agent_id: str
    category: str
    key: str
    value: Any
    confidence: float
    confirmation_count: int
    is_active: bool
    first_seen_at: datetime


class PreferenceBatch(BaseModel):
    """A collection of preferences for a single agent."""

    model_config = ConfigDict(from_attributes=True)

    agent_id: str
    preferences: list[PreferenceOut]


class PreferenceUpdate(BaseModel):
    """Partial update payload for a preference record."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    key: str
    value: Any
    confidence: float | None = None
