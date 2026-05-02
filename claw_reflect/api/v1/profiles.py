"""Profiles API endpoints — retrieve and manage aggregated agent knowledge profiles."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from claw_reflect.auth import get_workspace_id
from claw_reflect.db.session import get_session
from claw_reflect.models.contradiction import ContradictionRecord
from claw_reflect.models.memory import MemoryRecord
from claw_reflect.models.preference import ExtractedPreference
from claw_reflect.models.profile import AgentProfile
from claw_reflect.rate_limit import limiter
from claw_reflect.schemas.contradiction import ContradictionOut, ResolveContradictionRequest
from claw_reflect.schemas.memory import MemoryRecordOut
from claw_reflect.schemas.preference import PreferenceBatch, PreferenceOut, PreferenceUpdate
from claw_reflect.schemas.profile import AgentProfileSchema

router = APIRouter()


def _error(request: Request, status_code: int, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"message": message, "request_id": getattr(request.state, "request_id", "")},
    )


@router.get("/{agent_id}", response_model=AgentProfileSchema, summary="Get agent profile")
@limiter.limit("60/minute")
async def get_profile(
    request: Request,
    agent_id: str = Path(..., pattern=r"^[a-zA-Z0-9_-]{1,128}$"),
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    session: AsyncSession = Depends(get_session),
) -> AgentProfileSchema:
    """Return the current aggregated knowledge profile for the specified agent."""
    row = await session.execute(
        select(AgentProfile).where(
            AgentProfile.agent_id == agent_id,
            AgentProfile.workspace_id == workspace_id,
        )
    )
    profile = row.scalar_one_or_none()
    if profile is None:
        raise _error(request, 404, "Profile not found")
    return AgentProfileSchema.model_validate(profile)


@router.get("/{agent_id}/preferences", response_model=PreferenceBatch, summary="Get active preferences")
@limiter.limit("60/minute")
async def get_preferences(
    request: Request,
    agent_id: str = Path(..., pattern=r"^[a-zA-Z0-9_-]{1,128}$"),
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    session: AsyncSession = Depends(get_session),
) -> PreferenceBatch:
    result = await session.execute(
        select(ExtractedPreference).where(
            ExtractedPreference.workspace_id == workspace_id,
            ExtractedPreference.agent_id == agent_id,
            ExtractedPreference.is_active.is_(True),
        )
    )
    prefs = list(result.scalars().all())
    return PreferenceBatch(agent_id=agent_id, preferences=[PreferenceOut.model_validate(p) for p in prefs])


@router.put("/{agent_id}/preferences/{pref_id}", response_model=PreferenceOut, summary="Update preference value")
@limiter.limit("60/minute")
async def update_preference(
    request: Request,
    pref_id: str,
    body: PreferenceUpdate,
    agent_id: str = Path(..., pattern=r"^[a-zA-Z0-9_-]{1,128}$"),
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    session: AsyncSession = Depends(get_session),
) -> PreferenceOut:
    pref_row = await session.execute(
        select(ExtractedPreference).where(
            ExtractedPreference.id == pref_id,
            ExtractedPreference.workspace_id == workspace_id,
        )
    )
    pref = pref_row.scalar_one_or_none()
    if pref is None or pref.agent_id != agent_id:
        raise _error(request, 404, "Preference not found")
    pref.value = body.value
    pref.last_confirmed_at = datetime.now(UTC)
    await session.commit()
    return PreferenceOut.model_validate(pref)


@router.get("/{agent_id}/contradictions", response_model=list[ContradictionOut], summary="Get unresolved contradictions")
@limiter.limit("60/minute")
async def get_unresolved_contradictions(
    request: Request,
    agent_id: str = Path(..., pattern=r"^[a-zA-Z0-9_-]{1,128}$"),
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    session: AsyncSession = Depends(get_session),
) -> list[ContradictionOut]:
    result = await session.execute(
        select(ContradictionRecord).where(
            ContradictionRecord.workspace_id == workspace_id,
            ContradictionRecord.agent_id == agent_id,
            ContradictionRecord.resolved.is_(False),
        )
    )
    return [ContradictionOut.model_validate(row) for row in result.scalars().all()]


@router.post(
    "/{agent_id}/contradictions/{contradiction_id}/resolve",
    response_model=ContradictionOut,
    summary="Resolve contradiction",
)
@limiter.limit("60/minute")
async def resolve_contradiction(
    request: Request,
    contradiction_id: str,
    body: ResolveContradictionRequest,
    agent_id: str = Path(..., pattern=r"^[a-zA-Z0-9_-]{1,128}$"),
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    session: AsyncSession = Depends(get_session),
) -> ContradictionOut:
    contradiction_row = await session.execute(
        select(ContradictionRecord).where(
            ContradictionRecord.id == contradiction_id,
            ContradictionRecord.workspace_id == workspace_id,
        )
    )
    contradiction = contradiction_row.scalar_one_or_none()
    if contradiction is None or contradiction.agent_id != agent_id:
        raise _error(request, 404, "Contradiction not found")

    contradiction.resolved = True
    contradiction.resolution_strategy = body.strategy
    contradiction.resolved_at = datetime.now(UTC)
    if body.strategy == "keep_a":
        contradiction.winner_memory_id = contradiction.memory_id_a
    elif body.strategy == "keep_b":
        contradiction.winner_memory_id = contradiction.memory_id_b

    await session.commit()
    return ContradictionOut.model_validate(contradiction)


@router.get("/{agent_id}/memories", response_model=list[MemoryRecordOut], summary="List memories with filters")
@limiter.limit("60/minute")
async def list_memories(
    request: Request,
    agent_id: str = Path(..., pattern=r"^[a-zA-Z0-9_-]{1,128}$"),
    status: str | None = None,
    type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    session: AsyncSession = Depends(get_session),
) -> list[MemoryRecordOut]:
    stmt = (
        select(MemoryRecord)
        .where(
            MemoryRecord.agent_id == agent_id,
            MemoryRecord.workspace_id == workspace_id,
        )
        .order_by(MemoryRecord.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if status:
        stmt = stmt.where(MemoryRecord.reflection_status == status)
    if type:
        stmt = stmt.where(MemoryRecord.memory_type == type)
    result = await session.execute(stmt)
    return [
        MemoryRecordOut.model_validate(
            {
                "id": memory.id,
                "agent_id": memory.agent_id,
                "content": memory.content,
                "memory_type": memory.memory_type,
                "metadata": memory.metadata_,
                "tags": memory.tags,
                "created_at": memory.created_at,
                "updated_at": memory.updated_at,
                "importance_score": memory.importance_score,
                "recency_score": memory.recency_score,
                "confidence_score": memory.confidence_score,
                "composite_score": memory.composite_score,
                "reflection_status": memory.reflection_status,
                "is_promoted": memory.is_promoted,
            }
        )
        for memory in result.scalars().all()
    ]
