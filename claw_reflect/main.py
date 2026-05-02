"""FastAPI application factory with lifespan management and router registration."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from claw_reflect.api.v1.router import v1_router
from claw_reflect.config import settings
from claw_reflect.logging import configure_logging, get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application startup and shutdown lifecycle."""
    configure_logging(settings.log_level, settings.log_format)
    logger.info("claw-reflect starting", version="0.1.0")
    yield
    logger.info("claw-reflect shutting down")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    app = FastAPI(
        title="claw-reflect",
        description="Autonomous memory distillation engine for ClawDB",
        version="0.1.0",
        lifespan=lifespan,
        debug=settings.debug,
    )
    app.include_router(v1_router, prefix="/api/v1")
    return app


app = create_app()
