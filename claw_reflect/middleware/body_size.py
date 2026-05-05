"""Request-body size limiting middleware."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject request bodies over configured limit."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        content_len = request.headers.get("content-length")
        if content_len is not None:
            try:
                if int(content_len) > self.max_bytes:
                    return JSONResponse(status_code=413, content={"error": "payload_too_large"})
            except ValueError:
                return JSONResponse(status_code=413, content={"error": "payload_too_large"})
        else:
            body = await self._read_body_with_limit(request)
            if body is None:
                return JSONResponse(status_code=413, content={"error": "payload_too_large"})
            request._body = body
            request._receive = self._build_receive(body)

        return await call_next(request)

    async def _read_body_with_limit(self, request: Request) -> bytes | None:
        chunks: list[bytes] = []
        total = 0
        more_body = True

        while more_body:
            message = await request.receive()
            if message["type"] != "http.request":
                continue

            chunk = message.get("body", b"")
            total += len(chunk)
            if total > self.max_bytes:
                return None

            chunks.append(chunk)
            more_body = bool(message.get("more_body", False))

        return b"".join(chunks)

    def _build_receive(self, body: bytes) -> Callable[[], Awaitable[Message]]:
        sent = False

        async def receive() -> Message:
            nonlocal sent
            if sent:
                return {"type": "http.request", "body": b"", "more_body": False}
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}

        return receive
