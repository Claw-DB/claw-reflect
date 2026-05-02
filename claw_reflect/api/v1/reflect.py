"""Reflection API endpoints — ingest memory batches and trigger reflection jobs."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from claw_reflect.db.session import get_session
from claw_reflect.schemas.reflection import ReflectionJobCreate, ReflectionJobOut

router = APIRouter()


@router.post("/", response_model=ReflectionJobOut, summary="Trigger a reflection job")
async def trigger_reflection(
    body: ReflectionJobCreate,
    session: AsyncSession = Depends(get_session),
) -> ReflectionJobOut:
    """Accept a reflection job request and enqueue it for background processing."""
    raise NotImplementedError
