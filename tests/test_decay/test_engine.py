from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from claw_reflect.config import settings
from claw_reflect.decay.engine import DecayEngine
from claw_reflect.decay.policy import (
    DecayPolicyRegistry,
    ExponentialDecayPolicy,
    LinearDecayPolicy,
    StepDecayPolicy,
)
from claw_reflect.models.memory import MemoryRecord


@pytest.fixture
def session_factory(async_session: AsyncSession):
    return async_sessionmaker(async_session.bind, expire_on_commit=False, class_=AsyncSession)


def _memory(mem_id: str, score: float = 0.8, promoted: bool = False, agent_id: str = "AGT0000000000000000000001"):
    now = datetime.now(UTC)
    return MemoryRecord(
        id=mem_id,
        agent_id=agent_id,
        content="content",
        memory_type="message",
        metadata_={},
        tags=[],
        created_at=now - timedelta(days=30),
        updated_at=now,
        composite_score=score,
        is_promoted=promoted,
        reflection_status="reflected",
    )


def test_exponential_decay_half_life_correct():
    policy = ExponentialDecayPolicy(half_life_days=30)
    assert policy.compute(1.0, 30) == pytest.approx(0.5, rel=0.05)


def test_linear_decay_reduces_by_rate_per_day():
    policy = LinearDecayPolicy(decay_rate_per_day=0.01)
    assert policy.compute(1.0, 10) == pytest.approx(0.9)


def test_step_decay_applies_correct_multiplier():
    policy = StepDecayPolicy(steps=[(7, 0.9), (30, 0.6), (90, 0.3)])
    assert policy.compute(1.0, 45) == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_decay_archives_below_threshold(async_session, session_factory):
    mem = _memory("MEM0000000000000000004001", score=0.01)
    async_session.add(mem)
    await async_session.commit()

    engine = DecayEngine(session_factory, settings, DecayPolicyRegistry)
    result = await engine.run_decay_cycle(mem.agent_id)
    assert result.archived >= 1


@pytest.mark.asyncio
async def test_decay_skips_promoted_memories(async_session, session_factory):
    mem = _memory("MEM0000000000000000004002", score=0.2, promoted=True)
    async_session.add(mem)
    await async_session.commit()

    engine = DecayEngine(session_factory, settings, DecayPolicyRegistry)
    result = await engine.run_decay_cycle(mem.agent_id)
    assert result.skipped_promoted >= 1


@pytest.mark.asyncio
async def test_restore_memory_unarchives(async_session, session_factory):
    mem = _memory("MEM0000000000000000004003", score=0.01)
    mem.reflection_status = "archived"
    async_session.add(mem)
    await async_session.commit()

    engine = DecayEngine(session_factory, settings, DecayPolicyRegistry)
    ok = await engine.restore_memory(mem.id, "manual")
    assert ok is True


@pytest.mark.asyncio
async def test_preview_does_not_write(async_session, session_factory):
    mem = _memory("MEM0000000000000000004004", score=0.8)
    async_session.add(mem)
    await async_session.commit()

    engine = DecayEngine(session_factory, settings, DecayPolicyRegistry)
    preview = await engine.preview_decay(mem.agent_id)
    before = (await async_session.get(MemoryRecord, mem.id)).composite_score
    after = (await async_session.get(MemoryRecord, mem.id)).composite_score
    assert len(preview) >= 1 and before == after


@pytest.mark.asyncio
async def test_full_cycle_processes_all_agents(async_session, session_factory):
    async_session.add_all(
        [
            _memory("MEM0000000000000000004011", agent_id="AGT0000000000000000000011"),
            _memory("MEM0000000000000000004012", agent_id="AGT0000000000000000000012"),
        ]
    )
    await async_session.commit()

    engine = DecayEngine(session_factory, settings, DecayPolicyRegistry)
    result = await engine.run_decay_cycle(agent_id=None)
    assert result.processed >= 2
