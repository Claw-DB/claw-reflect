"""Health, readiness, and Prometheus metrics endpoints for claw-reflect."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

router = APIRouter()


@router.get("/health", summary="Liveness probe")
async def health() -> dict[str, str]:
    """Return service liveness status."""
    return {"status": "ok"}


@router.get("/ready", summary="Readiness probe")
async def ready() -> dict[str, str]:
    """Return service readiness status."""
    return {"status": "ready"}


@router.get("/metrics", summary="Prometheus metrics", response_class=PlainTextResponse)
async def metrics() -> PlainTextResponse:
    """Expose Prometheus metrics in the standard text format."""
    return PlainTextResponse(
        content=generate_latest().decode("utf-8"),
        media_type=CONTENT_TYPE_LATEST,
    )
