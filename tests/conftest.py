"""Shared pytest fixtures for claw-reflect test suite."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import pytest
import pytest_asyncio
from blake3 import blake3
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("REFLECT_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REFLECT_LLM_API_KEY", "test-key")
os.environ.setdefault("REFLECT_RATE_LIMIT_STORAGE_URL", "memory://")

from claw_reflect.config import Settings, settings
from claw_reflect.db.base import Base
from claw_reflect.db.session import get_session
from claw_reflect.llm.base import BaseLLMAdapter, LLMMessage, LLMResponse
from claw_reflect.main import app
from claw_reflect.models.api_key import ApiKey
from tests.factories import MemoryRecordFactory


@dataclass
class MockLLMAdapter(BaseLLMAdapter):
    scripted_responses: list[LLMResponse] = field(default_factory=list)
    calls: list[dict] = field(default_factory=list)

    @property
    def model_name(self) -> str:
        return "mock-model"

    @property
    def provider(self) -> str:
        return "mock"

    async def complete(
        self,
        messages: list[LLMMessage],
        max_tokens: int,
        temperature: float = 0.2,
    ) -> LLMResponse:
        self.calls.append({"messages": messages, "max_tokens": max_tokens, "temperature": temperature})
        if self.scripted_responses:
            return self.scripted_responses.pop(0)
        return LLMResponse(
            content='{"score": 0.5, "reasoning": "mock", "factors": ["default"]}',
            model=self.model_name,
            input_tokens=10,
            output_tokens=10,
            latency_ms=1.0,
            finish_reason="stop",
        )

    async def health_check(self) -> bool:
        return True


@pytest.fixture
def test_settings(monkeypatch) -> Settings:
    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(settings, "database_url", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setattr(settings, "redis_url", "redis://localhost:6379/0")
    return settings


@pytest_asyncio.fixture
async def async_engine(test_settings):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        import claw_reflect.models.api_key  # noqa: F401
        import claw_reflect.models.contradiction  # noqa: F401
        import claw_reflect.models.decay  # noqa: F401
        import claw_reflect.models.memory  # noqa: F401
        import claw_reflect.models.preference  # noqa: F401
        import claw_reflect.models.profile  # noqa: F401
        import claw_reflect.models.reflection  # noqa: F401

        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def async_session(async_engine):
    factory = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(async_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    from claw_reflect import auth

    async def _override_get_session():
        yield async_session

    factory = async_sessionmaker(async_session.bind, expire_on_commit=False, class_=AsyncSession)

    class _CM:
        async def __aenter__(self):
            self._session = factory()
            return self._session

        async def __aexit__(self, exc_type, exc, tb):
            await self._session.close()
            return False

    auth.session_factory = lambda: _CM()

    raw_key = "test-key"
    workspace_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
    async_session.add(
        ApiKey(
            key_hash=blake3(raw_key.encode("utf-8")).hexdigest(),
            workspace_id=workspace_id,
            label="pytest",
            revoked=False,
        )
    )
    await async_session.commit()

    app.dependency_overrides[get_session] = _override_get_session
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
        headers={"X-Claw-Api-Key": raw_key},
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def mock_llm() -> MockLLMAdapter:
    return MockLLMAdapter()


@pytest.fixture
def memory_factory(async_session: AsyncSession):
    MemoryRecordFactory._meta.sqlalchemy_session = async_session
    return MemoryRecordFactory
