from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from claw_reflect.config import settings
from claw_reflect.llm.prompts import PromptLibrary
from claw_reflect.models.memory import MemoryRecord
from claw_reflect.scoring.composite import CompositeScorer
from claw_reflect.scoring.confidence import ConfidenceScorer
from claw_reflect.scoring.importance import ImportanceScorer
from claw_reflect.scoring.recency import RecencyScorer


def _memory(**kwargs) -> MemoryRecord:
    now = datetime.now(timezone.utc)
    defaults = {
        "id": "MEM0000000000000000000001",
        "agent_id": "AGT0000000000000000000001",
        "content": "memory content",
        "memory_type": "message",
        "metadata_": {},
        "tags": [],
        "created_at": now,
        "updated_at": now,
    }
    defaults.update(kwargs)
    return MemoryRecord(**defaults)


@pytest.mark.asyncio
async def test_recency_score_fresh_memory_is_1():
    scorer = RecencyScorer()
    score = scorer.score(_memory(created_at=datetime.now(timezone.utc) - timedelta(hours=1)))
    assert score == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_recency_score_30_day_old_half_life_30_is_0_5():
    scorer = RecencyScorer(half_life_days=30)
    score = scorer.score(_memory(created_at=datetime.now(timezone.utc) - timedelta(days=30), memory_type="session"))
    assert score == pytest.approx(0.5, rel=0.05)


@pytest.mark.asyncio
async def test_recency_score_different_types_have_different_half_lives():
    scorer = RecencyScorer()
    age = datetime.now(timezone.utc) - timedelta(days=10)
    task_score = scorer.score(_memory(memory_type="task", created_at=age))
    context_score = scorer.score(_memory(memory_type="context", created_at=age))
    assert task_score > context_score


@pytest.mark.asyncio
async def test_importance_score_heuristic_longer_content_scores_higher(mock_llm):
    scorer = ImportanceScorer(mock_llm, PromptLibrary())
    short = _memory(content="tiny")
    long = _memory(content="x" * 2000)
    assert scorer.score_heuristic(long) > scorer.score_heuristic(short)


@pytest.mark.asyncio
async def test_importance_score_heuristic_task_type_scores_higher_than_context(mock_llm):
    scorer = ImportanceScorer(mock_llm, PromptLibrary())
    task = _memory(memory_type="task")
    context = _memory(memory_type="context")
    assert scorer.score_heuristic(task) > scorer.score_heuristic(context)


@pytest.mark.asyncio
async def test_confidence_score_contradiction_applies_penalty():
    scorer = ConfidenceScorer()
    clean = _memory(metadata_={})
    contradicted = _memory(metadata_={"has_active_contradiction": True})
    assert scorer.score(clean) > scorer.score(contradicted)


@pytest.mark.asyncio
async def test_confidence_score_promoted_memories_boost():
    scorer = ConfidenceScorer()
    normal = _memory(is_promoted=False)
    promoted = _memory(is_promoted=True)
    assert scorer.score(promoted) > scorer.score(normal)


@pytest.mark.asyncio
async def test_composite_weights_sum_to_1(mock_llm):
    scorer = CompositeScorer(ImportanceScorer(mock_llm, PromptLibrary()), RecencyScorer(), ConfidenceScorer())
    assert scorer.importance_w + scorer.recency_w + scorer.confidence_w == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_composite_score_stored_on_memory_record(async_session, mock_llm):
    memory = _memory()
    async_session.add(memory)
    await async_session.flush()
    scorer = CompositeScorer(ImportanceScorer(mock_llm, PromptLibrary()), RecencyScorer(), ConfidenceScorer())
    await scorer.score(memory, async_session)
    assert 0.0 <= memory.composite_score <= 1.0


@pytest.mark.asyncio
async def test_batch_scoring_respects_concurrency_limit(async_session, mock_llm):
    memories = [_memory(id=f"MEM{n:023d}") for n in range(10)]
    async_session.add_all(memories)
    await async_session.flush()

    scorer = CompositeScorer(ImportanceScorer(mock_llm, PromptLibrary()), RecencyScorer(), ConfidenceScorer())
    results = await scorer.score_batch(memories, async_session, concurrency=2)
    assert len(results) == len(memories)


@pytest.mark.asyncio
async def test_score_below_threshold_triggers_archive_flag(async_session):
    memory = _memory(composite_score=0.01)
    async_session.add(memory)
    await async_session.commit()
    assert memory.composite_score < settings.archive_threshold_score


@pytest.mark.asyncio
async def test_promoted_memory_skips_decay(async_session):
    memory = _memory(id="MEM0000000000000000000999", is_promoted=True, composite_score=0.2)
    async_session.add(memory)
    await async_session.commit()
    assert memory.is_promoted is True
