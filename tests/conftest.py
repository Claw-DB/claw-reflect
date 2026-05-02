"""Shared pytest fixtures for claw-reflect test suite."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from claw_reflect.main import app


@pytest.fixture
async def client() -> AsyncClient:
    """Return an async test client for the FastAPI application."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
