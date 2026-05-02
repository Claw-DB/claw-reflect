"""Request-body size limiting middleware."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject request bodies over configured limit."""

    def __init__(self, app, max_bytes: int) -> None:
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next):
        content_len = request.headers.get("content-length")
        if content_len is not None:
            try:
                if int(content_len) > self.max_bytes:
                    return JSONResponse(status_code=413, content={"error": "payload_too_large"})
            except ValueError:
                return JSONResponse(status_code=413, content={"error": "payload_too_large"})
        else:
            body = await request.body()
            if len(body) > self.max_bytes:
                return JSONResponse(status_code=413, content={"error": "payload_too_large"})
            request._body = body

        return await call_next(request)
