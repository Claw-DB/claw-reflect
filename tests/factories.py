"""factory-boy factories for generating test fixtures for claw-reflect models."""

from __future__ import annotations

from datetime import UTC, datetime

import factory
from factory.alchemy import SQLAlchemyModelFactory

from claw_reflect.models.memory import MemoryRecord


class AsyncSQLAlchemyModelFactory(SQLAlchemyModelFactory):
    """Compatibility wrapper for async SQLAlchemy session-backed factories."""


class MemoryRecordFactory(AsyncSQLAlchemyModelFactory):
    """Generate MemoryRecord rows with realistic fake defaults."""

    class Meta:
        model = MemoryRecord
        sqlalchemy_session_persistence = "flush"

    id = factory.Sequence(lambda n: f"MEM{n:023d}")
    agent_id = factory.Sequence(lambda n: f"AGT{n:023d}"[:26])
    content = factory.Faker("paragraph")
    memory_type = factory.Iterator(["message", "context", "task", "reasoning_trace", "tool_output"])
    metadata_ = factory.LazyFunction(lambda: {"session_id": "test-session"})
    tags = factory.LazyFunction(lambda: ["test"])
    created_at = factory.LazyFunction(lambda: datetime.now(UTC))
    updated_at = factory.LazyFunction(lambda: datetime.now(UTC))
