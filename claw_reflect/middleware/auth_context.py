"""Authentication middleware that resolves workspace context from API keys."""

from __future__ import annotations

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from claw_reflect.auth import authenticate_request, is_auth_exempt_path


class AuthContextMiddleware(BaseHTTPMiddleware):
    """Authenticate protected API routes and attach workspace context to request.state."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if is_auth_exempt_path(request.url.path):
            return await call_next(request)

        try:
            await authenticate_request(request)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content=exc.detail)

        return await call_next(request)
