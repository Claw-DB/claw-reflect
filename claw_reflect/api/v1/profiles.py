"""Profiles API endpoints — retrieve and manage aggregated agent knowledge profiles."""

from __future__ import annotations

from fastapi import APIRouter

from claw_reflect.schemas.profile import AgentProfileSchema

router = APIRouter()


@router.get("/{agent_id}", response_model=AgentProfileSchema, summary="Get agent profile")
async def get_profile(agent_id: str) -> AgentProfileSchema:
    """Return the current aggregated knowledge profile for the specified agent."""
    raise NotImplementedError
