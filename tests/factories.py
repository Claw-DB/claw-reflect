"""factory-boy factories for generating test fixtures for claw-reflect models."""

from __future__ import annotations

import factory

from claw_reflect.models.memory import MemoryRecord


class MemoryRecordFactory(factory.Factory):
    """Generates MemoryRecord instances with sensible defaults for testing."""

    class Meta:
        model = MemoryRecord

    id = factory.Sequence(lambda n: f"MEM{n:023d}")
    agent_id = factory.Sequence(lambda n: f"AGT{n:023d}")
    content = factory.Faker("paragraph")
    memory_type = "episodic"
    metadata_ = factory.LazyFunction(dict)
    tags = factory.LazyFunction(list)
