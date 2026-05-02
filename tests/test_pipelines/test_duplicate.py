from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from claw_reflect.config import settings
from claw_reflect.llm.base import LLMResponse
from claw_reflect.models.memory import MemoryRecord
from claw_reflect.pipelines.base import PipelineContext
from claw_reflect.pipelines.duplicate_collapser import DuplicateCollapsePipeline


@pytest.fixture
def session_factory(async_session: AsyncSession):
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _factory():
        yield async_session

    return _factory


def _memory(mem_id: str, content: str, status: str = "pending") -> MemoryRecord:
    now = datetime.now(UTC)
    return MemoryRecord(
        id=mem_id,
        agent_id="AGT0000000000000000000001",
        content=content,
        memory_type="message",
        metadata_={},
        tags=[],
        created_at=now,
        updated_at=now,
        reflection_status=status,
    )


@pytest.mark.asyncio
async def test_jaccard_similarity_identical_strings(async_session, session_factory, mock_llm):
    pipeline = DuplicateCollapsePipeline(session_factory, mock_llm, settings)
    assert pipeline.jaccard_similarity("a b c", "a b c") == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_jaccard_similarity_disjoint_strings(async_session, session_factory, mock_llm):
    pipeline = DuplicateCollapsePipeline(session_factory, mock_llm, settings)
    assert pipeline.jaccard_similarity("a b", "x y") == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_collapser_archives_lower_scoring_duplicate(async_session, session_factory, mock_llm):
    mock_llm.scripted_responses.append(
        LLMResponse(
            content='{"is_duplicate": true, "similarity_score": 1.0, "keep_which": "a", "merged_content": null}',
            model="mock",
            input_tokens=1,
            output_tokens=1,
            latency_ms=1,
            finish_reason="stop",
        )
    )
    a = _memory("MEM0000000000000000003001", "same content")
    b = _memory("MEM0000000000000000003002", "same content")
    a.composite_score = 0.9
    b.composite_score = 0.1
    # Ensure 'a' has a later created_at so it is memory_a in the pipeline (DESC order)
    from datetime import timedelta

    a.created_at = a.created_at + timedelta(seconds=1)
    async_session.add_all([a, b])
    await async_session.commit()

    pipeline = DuplicateCollapsePipeline(session_factory, mock_llm, settings)
    await pipeline.run(PipelineContext(agent_id=a.agent_id, job_id="DJ1", batch_size=50))
    await async_session.refresh(b)
    loaded_b = b
    assert loaded_b is not None and loaded_b.reflection_status == "archived"


@pytest.mark.asyncio
async def test_collapser_creates_merged_record(async_session, session_factory, mock_llm):
    mock_llm.scripted_responses.append(
        LLMResponse(
            content='{"is_duplicate": true, "similarity_score": 1.0, "keep_which": "merge", "merged_content": "merged"}',
            model="mock",
            input_tokens=1,
            output_tokens=1,
            latency_ms=1,
            finish_reason="stop",
        )
    )
    async_session.add_all([_memory("MEM0000000000000000003011", "dup text"), _memory("MEM0000000000000000003012", "dup text")])
    await async_session.commit()
    pipeline = DuplicateCollapsePipeline(session_factory, mock_llm, settings)
    await pipeline.run(PipelineContext(agent_id="AGT0000000000000000000001", job_id="DJ2", batch_size=50))

    rows = await async_session.execute(select(MemoryRecord).where(MemoryRecord.content == "merged"))
    assert rows.scalars().first() is not None


@pytest.mark.asyncio
async def test_collapser_dry_run_writes_nothing(async_session, session_factory, mock_llm):
    mock_llm.scripted_responses.append(
        LLMResponse(
            content='{"is_duplicate": true, "similarity_score": 1.0, "keep_which": "a", "merged_content": null}',
            model="mock",
            input_tokens=1,
            output_tokens=1,
            latency_ms=1,
            finish_reason="stop",
        )
    )
    async_session.add_all([_memory("MEM0000000000000000003021", "dup text"), _memory("MEM0000000000000000003022", "dup text")])
    await async_session.commit()
    pipeline = DuplicateCollapsePipeline(session_factory, mock_llm, settings)
    await pipeline.run(PipelineContext(agent_id="AGT0000000000000000000001", job_id="DJ3", batch_size=50, dry_run=True))
    loaded = await async_session.get(MemoryRecord, "MEM0000000000000000003022")
    assert loaded is not None and loaded.reflection_status != "archived"


@pytest.mark.asyncio
async def test_collapser_skips_archived_memories(async_session, session_factory, mock_llm):
    a = _memory("MEM0000000000000000003031", "same", status="archived")
    b = _memory("MEM0000000000000000003032", "same", status="pending")
    async_session.add_all([a, b])
    await async_session.commit()
    pipeline = DuplicateCollapsePipeline(session_factory, mock_llm, settings)
    assert pipeline.is_candidate_pair(a, b) is False
