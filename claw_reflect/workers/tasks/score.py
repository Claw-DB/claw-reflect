"""Celery task for refreshing composite scores across all memory records."""

import asyncio
from uuid import UUID

from sqlalchemy import select

from claw_reflect.config import settings
from claw_reflect.db.session import session_factory
from claw_reflect.llm.anthropic import AnthropicAdapter
from claw_reflect.llm.ollama import OllamaAdapter
from claw_reflect.llm.openai import OpenAIAdapter
from claw_reflect.llm.prompts import PromptLibrary
from claw_reflect.metrics.instruments import memories_processed_total
from claw_reflect.models.memory import MemoryRecord
from claw_reflect.scoring.composite import CompositeScorer
from claw_reflect.scoring.confidence import ConfidenceScorer
from claw_reflect.scoring.importance import ImportanceScorer
from claw_reflect.scoring.recency import RecencyScorer
from claw_reflect.workers.celery_app import celery_app


def _build_llm_adapter():
    if settings.llm_provider == "anthropic":
        return AnthropicAdapter(
            api_key=settings.llm_api_key.get_secret_value(),
            model=settings.llm_model,
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout_secs,
        )
    if settings.llm_provider == "ollama":
        return OllamaAdapter(
            model=settings.llm_model,
            base_url=settings.llm_base_url or "http://localhost:11434",
            timeout=settings.llm_timeout_secs,
        )
    return OpenAIAdapter(
        api_key=settings.llm_api_key.get_secret_value(),
        model=settings.llm_model,
        base_url=settings.llm_base_url or "https://api.openai.com",
        timeout=settings.llm_timeout_secs,
    )


@celery_app.task(bind=True, name="claw_reflect.workers.tasks.score.rescore_memories_task")
def rescore_memories_task(
    self,
    workspace_id: str | None = None,
    agent_id: str | None = None,
) -> dict[str, object]:
    """Recompute composite scores for non-archived memories in pages."""

    async def _run() -> dict[str, object]:
        llm = _build_llm_adapter()
        scorer = CompositeScorer(
            ImportanceScorer(llm, PromptLibrary()),
            RecencyScorer(),
            ConfidenceScorer(),
            importance_w=settings.importance_weight,
            recency_w=settings.recency_weight,
            confidence_w=settings.confidence_weight,
        )

        total_rescored = 0
        offset = 0
        while True:
            async with session_factory() as session:
                stmt = (
                    select(MemoryRecord)
                    .where(MemoryRecord.reflection_status != "archived")
                    .order_by(MemoryRecord.created_at.asc())
                    .limit(200)
                    .offset(offset)
                )
                if agent_id:
                    stmt = stmt.where(MemoryRecord.agent_id == agent_id)
                if workspace_id:
                    stmt = stmt.where(MemoryRecord.workspace_id == UUID(workspace_id))
                result = await session.execute(stmt)
                page = list(result.scalars().all())

                if not page:
                    break

                await scorer.score_batch(page, session=session, concurrency=10)
                await session.commit()
                total_rescored += len(page)
                offset += len(page)

        memories_processed_total.labels(agent_id=agent_id or "all", pipeline_name="rescoring").inc(total_rescored)
        return {"workspace_id": workspace_id, "agent_id": agent_id, "rescored": total_rescored}

    return asyncio.run(_run())
