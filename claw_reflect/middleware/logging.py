"""Structured request logging middleware."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from claw_reflect.logging import get_logger, request_id_var

logger = get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Emit a completion log event for every request."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        request.state.request_id = request_id
        token = request_id_var.set(request_id)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)

        latency_ms = (time.perf_counter() - start) * 1000
        workspace_id = str(getattr(request.state, "workspace_id", ""))
        api_key_prefix = str(getattr(request.state, "api_key_prefix", ""))[:12]
        logger.info(
            "request_complete",
            ts=datetime.now(UTC).isoformat(),
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            latency_ms=round(latency_ms, 3),
            workspace_id=workspace_id,
            api_key_prefix=api_key_prefix,
            request_id=request_id,
        )
        response.headers["X-Request-Id"] = request_id
        return response
