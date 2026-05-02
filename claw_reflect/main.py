"""FastAPI application factory with lifespan management and router registration."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from alembic.config import Config
from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from alembic import command
from claw_reflect.api.v1.router import v1_router
from claw_reflect.app_state import set_scheduler
from claw_reflect.config import settings
from claw_reflect.db.base import engine
from claw_reflect.db.session import session_factory
from claw_reflect.decay.engine import DecayEngine
from claw_reflect.decay.policy import DecayPolicyRegistry
from claw_reflect.decay.scheduler import ReflectScheduler
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
from claw_reflect.middleware.body_size import BodySizeLimitMiddleware
from claw_reflect.middleware.logging import RequestLoggingMiddleware
from claw_reflect.middleware.security_headers import SecurityHeadersMiddleware
from claw_reflect.pipelines.full_reflection import FullReflectionPipeline
from claw_reflect.rate_limit import limiter, rate_limit_exceeded_handler

logger = get_logger(__name__)
scheduler: ReflectScheduler | None = None


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


def _configure_tracing() -> None:
    """Configure OpenTelemetry exporter when endpoint is provided."""
    if not settings.otel_endpoint:
        return

    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": "claw-reflect",
                "service.version": "0.1.0",
            }
        )
    )
    exporter = OTLPSpanExporter(endpoint=settings.otel_endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)


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
    if settings.debug and settings.env.lower() == "production":
        raise RuntimeError("REFLECT_DEBUG=true is not allowed when REFLECT_ENV=production")

    _configure_tracing()
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
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_size_bytes)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(PrometheusMiddleware)

    if settings.otel_endpoint:
        FastAPIInstrumentor.instrument_app(app)
        SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
        RedisInstrumentor().instrument()

    app.include_router(v1_router, prefix="/api/v1")
    return app


app = create_app()


def main() -> None:
    """Entry-point used by console script."""
    import uvicorn

    uvicorn.run(
        "claw_reflect.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )
