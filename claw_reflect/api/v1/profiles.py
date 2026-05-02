"""Profiles API endpoints — retrieve and manage aggregated agent knowledge profiles."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from claw_reflect.db.session import get_session
from claw_reflect.models.contradiction import ContradictionRecord
from claw_reflect.models.memory import MemoryRecord
from claw_reflect.models.preference import ExtractedPreference
from claw_reflect.models.profile import AgentProfile
from claw_reflect.schemas.contradiction import ContradictionOut, ResolveContradictionRequest
from claw_reflect.schemas.memory import MemoryRecordOut
from claw_reflect.schemas.preference import PreferenceBatch, PreferenceOut
from fastapi import APIRouter

from claw_reflect.schemas.profile import AgentProfileSchema

router = APIRouter()


def _error(request: Request, status_code: int, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"message": message, "request_id": getattr(request.state, "request_id", "")},
    )


@router.get("/{agent_id}", response_model=AgentProfileSchema, summary="Get agent profile")
async def get_profile(agent_id: str, request: Request, session: AsyncSession = Depends(get_session)) -> AgentProfileSchema:
    """Return the current aggregated knowledge profile for the specified agent."""
    profile = await session.get(AgentProfile, agent_id)
    if profile is None:
        raise _error(request, 404, "Profile not found")
    return AgentProfileSchema.model_validate(profile)


@router.get("/{agent_id}/preferences", response_model=PreferenceBatch, summary="Get active preferences")
async def get_preferences(
    agent_id: str,
    session: AsyncSession = Depends(get_session),
) -> PreferenceBatch:
    result = await session.execute(
        select(ExtractedPreference).where(
            ExtractedPreference.agent_id == agent_id,
            ExtractedPreference.is_active.is_(True),
        )
    )
    prefs = list(result.scalars().all())
    return PreferenceBatch(agent_id=agent_id, preferences=[PreferenceOut.model_validate(p) for p in prefs])


@router.put("/{agent_id}/preferences/{pref_id}", response_model=PreferenceOut, summary="Update preference value")
async def update_preference(
    agent_id: str,
    pref_id: str,
    body: dict,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> PreferenceOut:
    pref = await session.get(ExtractedPreference, pref_id)
    if pref is None or pref.agent_id != agent_id:
        raise _error(request, 404, "Preference not found")
    pref.value = body.get("value", pref.value)
    pref.last_confirmed_at = datetime.now(timezone.utc)
    await session.commit()
    return PreferenceOut.model_validate(pref)


@router.get("/{agent_id}/contradictions", response_model=list[ContradictionOut], summary="Get unresolved contradictions")
async def get_unresolved_contradictions(
    agent_id: str,
    session: AsyncSession = Depends(get_session),
) -> list[ContradictionOut]:
    result = await session.execute(
        select(ContradictionRecord).where(
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
async def resolve_contradiction(
    agent_id: str,
    contradiction_id: str,
    body: ResolveContradictionRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> ContradictionOut:
    contradiction = await session.get(ContradictionRecord, contradiction_id)
    if contradiction is None or contradiction.agent_id != agent_id:
        raise _error(request, 404, "Contradiction not found")

    contradiction.resolved = True
    contradiction.resolution_strategy = body.strategy
    contradiction.resolved_at = datetime.now(timezone.utc)
    if body.strategy == "keep_a":
        contradiction.winner_memory_id = contradiction.memory_id_a
    elif body.strategy == "keep_b":
        contradiction.winner_memory_id = contradiction.memory_id_b

    await session.commit()
    return ContradictionOut.model_validate(contradiction)


@router.get("/{agent_id}/memories", response_model=list[MemoryRecordOut], summary="List memories with filters")
async def list_memories(
    agent_id: str,
    status: str | None = None,
    type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[MemoryRecordOut]:
    stmt = (
        select(MemoryRecord)
        .where(MemoryRecord.agent_id == agent_id)
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
