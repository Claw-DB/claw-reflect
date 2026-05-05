"""Authentication helpers for API key validation and workspace resolution."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

from blake3 import blake3
from fastapi import HTTPException, Request
from opentelemetry.trace import get_current_span
from sqlalchemy import select

from claw_reflect.db.session import session_factory
from claw_reflect.models.api_key import ApiKey

PROTECTED_API_PREFIX = "/api/v1"
AUTH_EXEMPT_PATHS = frozenset({"/api/v1/health", "/api/v1/ready", "/api/v1/metrics"})


def _unauthorized() -> HTTPException:
    """Return the generic 401 response used for all auth failures."""
    return HTTPException(status_code=401, detail={"error": "unauthorized"})


def is_auth_exempt_path(path: str) -> bool:
    """Return whether a request path should bypass API-key authentication."""
    return not path.startswith(PROTECTED_API_PREFIX) or path in AUTH_EXEMPT_PATHS


async def _touch_last_used(api_key_id: uuid.UUID) -> None:
    """Update API key last-used timestamp asynchronously."""
    async with session_factory() as session:
        row = await session.get(ApiKey, api_key_id)
        if row is None:
            return
        row.last_used_at = datetime.now(UTC)
        await session.commit()


async def _lookup_active_api_key(raw_key: str) -> ApiKey | None:
    digest = blake3(raw_key.encode("utf-8")).hexdigest()

    async with session_factory() as session:
        result = await session.execute(
            select(ApiKey).where(
                ApiKey.key_hash == digest,
                ApiKey.revoked.is_(False),
            )
        )
        return result.scalar_one_or_none()


def _attach_auth_state(request: Request, raw_key: str, row: ApiKey) -> None:
    request.state.workspace_id = row.workspace_id
    request.state.api_key_prefix = raw_key[:12]
    request.state.api_key_id = row.id
    request.state.authenticated_api_key = raw_key

    span = get_current_span()
    if span is not None:
        span.set_attribute("workspace_id", str(row.workspace_id))
        span.set_attribute("api_key_prefix", raw_key[:12])


async def authenticate_request(request: Request) -> str:
    """Validate the request API key and cache the resolved auth context on request.state."""
    cached_key = getattr(request.state, "authenticated_api_key", None)
    if cached_key:
        return str(cached_key)

    raw_key = request.headers.get("X-Claw-Api-Key")
    if not raw_key:
        raise _unauthorized()

    row = await _lookup_active_api_key(raw_key)
    if row is None:
        raise _unauthorized()

    _attach_auth_state(request, raw_key, row)

    # fire-and-forget update; request must not block on telemetry update
    asyncio.create_task(_touch_last_used(row.id))
    return raw_key


async def get_api_key(request: Request) -> str:
    """Validate the request API key and attach workspace context to request.state."""
    return await authenticate_request(request)


def get_workspace_id(request: Request) -> uuid.UUID:
    """Return workspace ID set by API-key authentication dependency."""
    workspace_id = getattr(request.state, "workspace_id", None)
    if workspace_id is None:
        raise _unauthorized()
    if isinstance(workspace_id, uuid.UUID):
        return workspace_id
    return uuid.UUID(str(workspace_id))
