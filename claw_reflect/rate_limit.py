"""Shared rate-limiting components and handlers."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from limits import parse as parse_limit
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from claw_reflect.config import settings


def api_key_func(request: Request) -> str:
    """Return a stable rate-limit key derived from API key header."""
    raw = request.headers.get("X-Claw-Api-Key", "")
    if raw:
        return raw
    return f"anon:{get_remote_address(request)}"


limiter = Limiter(
    key_func=api_key_func,
    storage_uri=settings.effective_rate_limit_storage_url,
    enabled=settings.rate_limit_enabled,
)


def parse_retry_after(limit: str) -> int:
    """Return retry-after in seconds for a limit string (e.g. 10/minute)."""
    try:
        item = parse_limit(limit)
        return int(item.get_expiry())
    except Exception:
        return 60


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Return API-specific payload for rate-limit overflow."""
    retry_after = parse_retry_after(str(getattr(exc, "limit", "10/minute")))
    return JSONResponse(
        status_code=429,
        content={"error": "rate_limit_exceeded", "retry_after_seconds": retry_after},
    )
