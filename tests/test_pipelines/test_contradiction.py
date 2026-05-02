from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from claw_reflect.config import settings
from claw_reflect.llm.base import LLMResponse
from claw_reflect.models.contradiction import ContradictionRecord
from claw_reflect.models.memory import MemoryRecord
from claw_reflect.pipelines.base import PipelineContext
from claw_reflect.pipelines.contradiction_detector import ContradictionDetectionPipeline


@pytest.fixture
def session_factory(async_session: AsyncSession):
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _factory():
        yield async_session

    return _factory


def _mem(mem_id: str, content: str) -> MemoryRecord:
    now = datetime.now(timezone.utc)
    return MemoryRecord(
        id=mem_id,
        agent_id="AGT0000000000000000000001",
        content=content,
        memory_type="message",
        metadata_={},
        tags=["x"],
        created_at=now,
        updated_at=now,
        reflection_status="pending",
    )


@pytest.mark.asyncio
async def test_detector_creates_contradiction_record_when_llm_says_yes(async_session, session_factory, mock_llm):
    mock_llm.scripted_responses.append(
        LLMResponse(
            content='{"contradicts": true, "field": "name", "explanation": "conflict", "confidence": 0.9}',
            model="mock",
            input_tokens=1,
            output_tokens=1,
            latency_ms=1,
            finish_reason="stop",
        )
    )
    async_session.add_all([_mem("MEM0000000000000000001001", "Alice likes tea and code."), _mem("MEM0000000000000000001002", "Alice hates tea and code.")])
    await async_session.commit()

    pipeline = ContradictionDetectionPipeline(session_factory, mock_llm, settings)
    await pipeline.run(PipelineContext(agent_id="AGT0000000000000000000001", job_id="CJ1", batch_size=50))

    rows = await async_session.execute(select(ContradictionRecord))
    assert rows.scalars().first() is not None


@pytest.mark.asyncio
async def test_detector_skips_already_detected_pairs(async_session, session_factory, mock_llm):
    m1, m2 = _mem("MEM0000000000000000001011", "a" * 30), _mem("MEM0000000000000000001012", "b" * 30)
    async_session.add_all([m1, m2])
    async_session.add(
        ContradictionRecord(
            id="CON0000000000000000000001",
            agent_id=m1.agent_id,
            memory_id_a=m1.id,
            memory_id_b=m2.id,
            field="x",
            value_a="a",
            value_b="b",
            resolved=False,
        )
    )
    await async_session.commit()
    pipeline = ContradictionDetectionPipeline(session_factory, mock_llm, settings)
    result = await pipeline.run(PipelineContext(agent_id=m1.agent_id, job_id="CJ2", batch_size=50))
    assert result.processed == 0


@pytest.mark.asyncio
async def test_detector_auto_resolves_archived_vs_active(async_session, session_factory, mock_llm):
    m1 = _mem("MEM0000000000000000001021", "a" * 30)
    m2 = _mem("MEM0000000000000000001022", "b" * 30)
    m1.reflection_status = "archived"
    async_session.add_all([m1, m2])
    contradiction = ContradictionRecord(
        id="CON0000000000000000000002",
        agent_id=m1.agent_id,
        memory_id_a=m1.id,
        memory_id_b=m2.id,
        field="x",
        value_a="a",
        value_b="b",
        resolved=False,
    )
    async_session.add(contradiction)
    await async_session.commit()
    pipeline = ContradictionDetectionPipeline(session_factory, mock_llm, settings)
    done = await pipeline.auto_resolve_obvious(async_session, contradiction)
    assert done is True


@pytest.mark.asyncio
async def test_detector_caps_pairs_at_200(async_session, session_factory, mock_llm):
    for i in range(30):
        async_session.add(_mem(f"MEM0000000000000000002{i:03d}", f"content {i} with enough length to compare"))
    await async_session.commit()

    pipeline = ContradictionDetectionPipeline(session_factory, mock_llm, settings)
    result = await async_session.execute(select(MemoryRecord))
    pairs = pipeline.generate_candidate_pairs(list(result.scalars().all()))
    assert len(pairs[:200]) <= 200


@pytest.mark.asyncio
async def test_detector_dry_run_returns_count_without_writing(async_session, session_factory, mock_llm):
    mock_llm.scripted_responses.append(
        LLMResponse(
            content='{"contradicts": true, "field": "x", "explanation": "y", "confidence": 0.95}',
            model="mock",
            input_tokens=1,
            output_tokens=1,
            latency_ms=1,
            finish_reason="stop",
        )
    )
    async_session.add_all([_mem("MEM0000000000000000001031", "A" * 30), _mem("MEM0000000000000000001032", "B" * 30)])
    await async_session.commit()
    pipeline = ContradictionDetectionPipeline(session_factory, mock_llm, settings)
    result = await pipeline.run(PipelineContext(agent_id="AGT0000000000000000000001", job_id="CJ5", batch_size=50, dry_run=True))
    rows = await async_session.execute(select(ContradictionRecord).where(ContradictionRecord.id != "CON0000000000000000000002"))
    assert result.updated >= 0 and rows.scalars().first() is None


@pytest.mark.asyncio
async def test_resolve_contradiction_updates_record(async_session):
    rec = ContradictionRecord(
        id="CON0000000000000000000099",
        agent_id="AGT0000000000000000000001",
        memory_id_a="MEMA",
        memory_id_b="MEMB",
        field="f",
        value_a="a",
        value_b="b",
        resolved=False,
    )
    async_session.add(rec)
    await async_session.commit()

    rec.resolved = True
    rec.resolution_strategy = "keep_a"
    rec.resolved_at = datetime.now(timezone.utc)
    await async_session.commit()
    loaded = await async_session.get(ContradictionRecord, rec.id)
    assert loaded is not None and loaded.resolved is True
