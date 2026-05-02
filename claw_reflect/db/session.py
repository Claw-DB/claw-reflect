"""Async SQLAlchemy session dependency for FastAPI request handling."""

from __future__ import annotations

from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from claw_reflect.db.base import AsyncSessionLocal

session_factory = AsyncSessionLocal


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield an :class:`AsyncSession` and guarantee it is closed after the request."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
