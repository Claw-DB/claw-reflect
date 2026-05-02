"""SQLAlchemy declarative base and async engine/session factory for claw-reflect."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from claw_reflect.config import settings


class Base(DeclarativeBase):
    """Shared declarative base for all claw-reflect ORM models."""


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

_engine_kwargs: dict[str, object] = {
    "pool_pre_ping": True,
    "echo": settings.debug,
}
if not settings.database_url.startswith("sqlite"):
    _engine_kwargs["pool_size"] = settings.database_pool_size
    _engine_kwargs["max_overflow"] = settings.database_max_overflow

engine = create_async_engine(settings.database_url, **_engine_kwargs)

# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
