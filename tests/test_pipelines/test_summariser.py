from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from claw_reflect.config import settings
from claw_reflect.llm.base import LLMResponse
from claw_reflect.models.memory import MemoryRecord
from claw_reflect.models.reflection import ReflectionResult
from claw_reflect.pipelines.base import PipelineContext
from claw_reflect.pipelines.summariser import SummarisationPipeline


@pytest.fixture
def session_factory(async_session: AsyncSession):
    from contextlib import asynccontextmanager
    
    @asynccontextmanager
    async def _factory():
        yield async_session
    
    return _factory


def _memory(mem_id: str, session_id: str) -> MemoryRecord:
    now = datetime.now(timezone.utc)
    return MemoryRecord(
        id=mem_id,
        agent_id="AGT0000000000000000000001",
        content=f"content for {mem_id}",
        memory_type="message",
        metadata_={"session_id": session_id},
        tags=[],
        created_at=now,
        updated_at=now,
        reflection_status="pending",
    )


@pytest.mark.asyncio
async def test_summariser_archives_original_messages(async_session, session_factory, mock_llm):
    mock_llm.scripted_responses.append(
        LLMResponse(
            content='{"summary":"hello","key_facts":["a"],"topics":["topic"],"confidence":0.9}',
            model="mock",
            input_tokens=10,
            output_tokens=10,
            latency_ms=1,
            finish_reason="stop",
        )
    )
    m1, m2 = _memory("MEM0000000000000000000001", "s1"), _memory("MEM0000000000000000000002", "s1")
    async_session.add_all([m1, m2])
    await async_session.commit()

    pipeline = SummarisationPipeline(session_factory, mock_llm, settings)
    await pipeline.run(PipelineContext(agent_id=m1.agent_id, job_id="J1", batch_size=20, dry_run=False))

    m1_id, m2_id = m1.id, m2.id
    async_session.expire_all()
    rows = await async_session.execute(select(MemoryRecord).where(MemoryRecord.id.in_([m1_id, m2_id])))
    archived = [m for m in rows.scalars().all() if m.reflection_status == "archived"]
    assert len(archived) == 2


@pytest.mark.asyncio
async def test_summariser_creates_summary_memory_record(async_session, session_factory, mock_llm):
    mock_llm.scripted_responses.append(
        LLMResponse(
            content='{"summary":"new summary","key_facts":[],"topics":["x"],"confidence":0.8}',
            model="mock",
            input_tokens=1,
            output_tokens=1,
            latency_ms=1,
            finish_reason="stop",
        )
    )
    async_session.add(_memory("MEM0000000000000000000010", "s10"))
    await async_session.commit()
    pipeline = SummarisationPipeline(session_factory, mock_llm, settings)
    await pipeline.run(PipelineContext(agent_id="AGT0000000000000000000001", job_id="J2", batch_size=20))

    rows = await async_session.execute(select(MemoryRecord).where(MemoryRecord.memory_type == "summary"))
    assert rows.scalars().first() is not None


@pytest.mark.asyncio
async def test_summariser_dry_run_writes_nothing(async_session, session_factory, mock_llm):
    async_session.add(_memory("MEM0000000000000000000020", "s20"))
    await async_session.commit()
    pipeline = SummarisationPipeline(session_factory, mock_llm, settings)
    await pipeline.run(PipelineContext(agent_id="AGT0000000000000000000001", job_id="J3", batch_size=20, dry_run=True))

    rows = await async_session.execute(select(MemoryRecord).where(MemoryRecord.memory_type == "summary"))
    assert rows.scalars().first() is None


@pytest.mark.asyncio
async def test_summariser_handles_empty_batch(async_session, session_factory, mock_llm):
    pipeline = SummarisationPipeline(session_factory, mock_llm, settings)
    result = await pipeline.run(PipelineContext(agent_id="missing", job_id="J4", batch_size=20))
    assert result.processed == 0


@pytest.mark.asyncio
async def test_summariser_truncates_context_to_fit_window(async_session, session_factory, mock_llm):
    mock_llm.scripted_responses.append(
        LLMResponse(
            content='{"summary":"ok","key_facts":[],"topics":[],"confidence":0.8}',
            model="mock",
            input_tokens=1,
            output_tokens=1,
            latency_ms=1,
            finish_reason="stop",
        )
    )
    async_session.add(
        MemoryRecord(
            id="MEM0000000000000000000030",
            agent_id="AGT0000000000000000000001",
            content="x" * 200000,
            memory_type="message",
            metadata_={"session_id": "s30"},
            tags=[],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            reflection_status="pending",
        )
    )
    await async_session.commit()
    pipeline = SummarisationPipeline(session_factory, mock_llm, settings)
    result = await pipeline.run(PipelineContext(agent_id="AGT0000000000000000000001", job_id="J5", batch_size=20))
    assert result.failed == 0


@pytest.mark.asyncio
async def test_summariser_groups_by_session_id(async_session, session_factory, mock_llm):
    for idx, sid in enumerate(["a", "b"], start=40):
        mock_llm.scripted_responses.append(
            LLMResponse(
                content='{"summary":"s","key_facts":[],"topics":[],"confidence":0.8}',
                model="mock",
                input_tokens=1,
                output_tokens=1,
                latency_ms=1,
                finish_reason="stop",
            )
        )
        async_session.add(_memory(f"MEM00000000000000000000{idx}", sid))
    await async_session.commit()
    pipeline = SummarisationPipeline(session_factory, mock_llm, settings)
    result = await pipeline.run(PipelineContext(agent_id="AGT0000000000000000000001", job_id="J6", batch_size=20))
    assert len(result.details) >= 2


@pytest.mark.asyncio
async def test_summariser_sets_reflection_status_archived(async_session, session_factory, mock_llm):
    mock_llm.scripted_responses.append(
        LLMResponse(
            content='{"summary":"s","key_facts":[],"topics":[],"confidence":0.8}',
            model="mock",
            input_tokens=1,
            output_tokens=1,
            latency_ms=1,
            finish_reason="stop",
        )
    )
    memory = _memory("MEM0000000000000000000050", "s50")
    async_session.add(memory)
    await async_session.commit()
    pipeline = SummarisationPipeline(session_factory, mock_llm, settings)
    await pipeline.run(PipelineContext(agent_id=memory.agent_id, job_id="J7", batch_size=20))

    memory_id = memory.id
    async_session.expire_all()
    refreshed = await async_session.get(MemoryRecord, memory_id)
    assert refreshed is not None and refreshed.reflection_status == "archived"


@pytest.mark.asyncio
async def test_summariser_saves_reflection_result(async_session, session_factory, mock_llm):
    mock_llm.scripted_responses.append(
        LLMResponse(
            content='{"summary":"s","key_facts":[],"topics":[],"confidence":0.8}',
            model="mock",
            input_tokens=1,
            output_tokens=1,
            latency_ms=1,
            finish_reason="stop",
        )
    )
    async_session.add(_memory("MEM0000000000000000000060", "s60"))
    await async_session.commit()
    pipeline = SummarisationPipeline(session_factory, mock_llm, settings)
    await pipeline.run(PipelineContext(agent_id="AGT0000000000000000000001", job_id="J8", batch_size=20))

    rows = await async_session.execute(select(ReflectionResult).where(ReflectionResult.job_id == "J8"))
    assert rows.scalars().first() is not None
