"""Health, readiness, and Prometheus metrics endpoints for claw-reflect."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import redis
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from claw_reflect.config import settings
from claw_reflect.db.session import get_session

router = APIRouter()


@router.get("/health", summary="Liveness probe")
async def health() -> dict[str, str]:
    """Return service liveness status."""
    return {
        "status": "ok",
        "timestamp": datetime.now(UTC).isoformat(),
        "version": "0.1.0",
    }


@router.get("/ready", summary="Readiness probe")
async def ready(session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    """Return readiness status; fail if DB or Redis is unavailable."""
    try:
        # Safe constant health probe query with no user-controlled interpolation.
        await session.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail={"status": "db_down", "error": str(exc)}) from exc

    try:
        redis_client = redis.Redis.from_url(settings.redis_url)
        await asyncio.to_thread(redis_client.ping)
    except Exception as exc:
        raise HTTPException(status_code=503, detail={"status": "redis_down", "error": str(exc)}) from exc

    return {"status": "ready"}


@router.get("/metrics", summary="Prometheus metrics", response_class=PlainTextResponse)
async def metrics() -> PlainTextResponse:
    """Expose Prometheus metrics in the standard text format."""
    return PlainTextResponse(
        content=generate_latest().decode("utf-8"),
        media_type=CONTENT_TYPE_LATEST,
    )
