"""FastAPI application factory with lifespan management and router registration."""

from __future__ import annotations

import asyncio
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from claw_reflect.app_state import set_scheduler
from claw_reflect.api.v1.router import v1_router
from claw_reflect.config import settings
from claw_reflect.db.base import engine
from claw_reflect.decay.engine import DecayEngine
from claw_reflect.decay.policy import DecayPolicyRegistry
from claw_reflect.decay.scheduler import ReflectScheduler
from claw_reflect.db.session import session_factory
from claw_reflect.llm.anthropic import AnthropicAdapter
from claw_reflect.llm.ollama import OllamaAdapter
from claw_reflect.llm.openai import OpenAIAdapter
from claw_reflect.logging import configure_logging, get_logger
from claw_reflect.metrics.instruments import (
    http_request_duration_seconds,
    http_requests_total,
    init_metrics,
    scheduler_jobs_active,
)
from claw_reflect.pipelines.full_reflection import FullReflectionPipeline
from claw_reflect.logging import request_id_var

logger = get_logger(__name__)
scheduler: ReflectScheduler | None = None


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = request_id
        return response


class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start
        route = request.scope.get("route")
        route_path = getattr(route, "path", request.url.path)
        method = request.method
        status_code = str(response.status_code)
        http_requests_total.labels(method=method, route=route_path, status_code=status_code).inc()
        http_request_duration_seconds.labels(method=method, route=route_path).observe(duration)
        return response


def _build_llm_adapter():
    if settings.llm_provider == "anthropic":
        return AnthropicAdapter(
            api_key=settings.llm_api_key.get_secret_value(),
            model=settings.llm_model,
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout_secs,
        )
    if settings.llm_provider == "ollama":
        return OllamaAdapter(
            model=settings.llm_model,
            base_url=settings.llm_base_url or "http://localhost:11434",
            timeout=settings.llm_timeout_secs,
        )
    return OpenAIAdapter(
        api_key=settings.llm_api_key.get_secret_value(),
        model=settings.llm_model,
        base_url=settings.llm_base_url or "https://api.openai.com",
        timeout=settings.llm_timeout_secs,
    )


async def create_db_tables() -> None:
    """Run alembic migrations on startup."""

    def _run_upgrade() -> None:
        cfg = Config("alembic.ini")
        command.upgrade(cfg, "head")

    await asyncio.to_thread(_run_upgrade)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application startup and shutdown lifecycle."""
    global scheduler
    configure_logging(settings.log_level, settings.log_format)
    await create_db_tables()
    init_metrics()

    llm = _build_llm_adapter()
    decay_engine = DecayEngine(session_factory, settings, DecayPolicyRegistry)
    reflection_pipeline = FullReflectionPipeline(session_factory, llm, settings)
    scheduler = ReflectScheduler(settings, decay_engine, reflection_pipeline)
    set_scheduler(scheduler)
    scheduler.start()
    scheduler_jobs_active.set(len(scheduler.get_scheduled_jobs()))

    logger.info("claw-reflect started", version="0.1.0", llm_provider=settings.llm_provider)
    yield
    if scheduler is not None:
        scheduler.stop()
        scheduler_jobs_active.set(0)
    await engine.dispose()
    logger.info("claw-reflect stopped")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    app = FastAPI(
        title="claw-reflect",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
    )
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(PrometheusMiddleware)
    app.include_router(v1_router, prefix="/api/v1")
    return app


app = create_app()
