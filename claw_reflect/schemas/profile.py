"""Pydantic v2 schemas for agent profile API responses."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AgentProfileSchema(BaseModel):
    """Consolidated long-term agent profile as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    agent_id: str
    preferences: dict[str, Any]
    facts: dict[str, Any]
    behaviour_patterns: dict[str, Any]
    last_updated_at: datetime
    memory_count: int
    profile_version: int
