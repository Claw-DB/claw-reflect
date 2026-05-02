"""Reflection API endpoints — ingest memory batches and trigger reflection jobs."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from claw_reflect.config import settings
from claw_reflect.db.session import get_session
from claw_reflect.db.session import session_factory
from claw_reflect.decay.engine import DecayEngine
from claw_reflect.decay.policy import DecayPolicyRegistry
from claw_reflect.llm.anthropic import AnthropicAdapter
from claw_reflect.llm.ollama import OllamaAdapter
from claw_reflect.llm.openai import OpenAIAdapter
from claw_reflect.models.memory import MemoryRecord
from claw_reflect.models.reflection import ReflectionJob
from claw_reflect.pipelines.base import PipelineContext
from claw_reflect.pipelines.full_reflection import FullReflectionPipeline
from claw_reflect.scoring.composite import CompositeScorer
from claw_reflect.scoring.confidence import ConfidenceScorer
from claw_reflect.scoring.importance import ImportanceScorer
from claw_reflect.scoring.recency import RecencyScorer
from claw_reflect.llm.prompts import PromptLibrary
from claw_reflect.schemas.jobs import JobStatusResponse, JobTriggerRequest
from claw_reflect.schemas.memory import MemoryBatch
from claw_reflect.schemas.reflection import ReflectionJobOut
from claw_reflect.workers.tasks.reflect import reflect_agent_task

router = APIRouter()


def _new_id() -> str:
    return uuid.uuid4().hex[:26]


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


def _request_error(request: Request, status_code: int, message: str) -> HTTPException:
    request_id = getattr(request.state, "request_id", "")
    return HTTPException(status_code=status_code, detail={"message": message, "request_id": request_id})


@router.post("/trigger", response_model=JobStatusResponse, summary="Trigger a reflection job")
async def trigger_reflection(
    body: JobTriggerRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> JobStatusResponse:
    """Enqueue reflection task and persist a pending job row."""
    try:
        job = ReflectionJob(
            id=_new_id(),
            agent_id=body.agent_id,
            status="pending",
            job_type=body.job_type,
            metadata_={"options": body.options},
        )
        session.add(job)
        await session.commit()

        task = reflect_agent_task.delay(body.agent_id, body.job_type, body.options)
        job.metadata_["celery_task_id"] = task.id
        await session.commit()
        return JobStatusResponse(
            job_id=job.id,
            status="queued",
            progress_pct=0.0,
            message="Reflection job queued",
        )
    except Exception as exc:
        raise _request_error(request, 500, f"Failed to queue reflection: {exc}") from exc


@router.post("/trigger/dry-run", summary="Preview full reflection impact")
async def trigger_reflection_dry_run(
    body: JobTriggerRequest,
    request: Request,
) -> dict[str, int]:
    try:
        llm = _build_llm_adapter()
        pipeline = FullReflectionPipeline(session_factory, llm, settings)
        ctx = PipelineContext(
            agent_id=body.agent_id,
            job_id="dry-run",
            batch_size=int(body.options.get("batch_size", settings.reflection_batch_size)),
            dry_run=True,
            options={**body.options, "dry_run": True},
        )
        return await pipeline.preview(ctx)
    except Exception as exc:
        raise _request_error(request, 500, f"Dry-run failed: {exc}") from exc


@router.post("/memories", summary="Upsert memory batch for reflection")
async def ingest_memories(
    body: MemoryBatch,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, int]:
    try:
        upserted = 0
        for item in body.memories:
            existing = await session.get(MemoryRecord, item.id)
            if existing is None:
                session.add(
                    MemoryRecord(
                        id=item.id,
                        agent_id=item.agent_id,
                        content=item.content,
                        memory_type=item.memory_type,
                        metadata_=item.metadata,
                        tags=item.tags,
                        created_at=item.created_at,
                        updated_at=item.updated_at,
                    )
                )
            else:
                existing.content = item.content
                existing.memory_type = item.memory_type
                existing.metadata_ = item.metadata
                existing.tags = item.tags
                existing.updated_at = item.updated_at
            upserted += 1
        await session.commit()
        return {"upserted": upserted}
    except Exception as exc:
        raise _request_error(request, 500, f"Memory upsert failed: {exc}") from exc


@router.post("/score/{agent_id}", summary="Trigger immediate scoring for an agent")
async def score_agent(agent_id: str, request: Request, session: AsyncSession = Depends(get_session)) -> dict:
    try:
        result = await session.execute(
            select(MemoryRecord).where(
                MemoryRecord.agent_id == agent_id,
                MemoryRecord.reflection_status != "archived",
            )
        )
        memories = list(result.scalars().all())
        llm = _build_llm_adapter()
        scorer = CompositeScorer(
            ImportanceScorer(llm, PromptLibrary()),
            RecencyScorer(),
            ConfidenceScorer(),
            importance_w=settings.importance_weight,
            recency_w=settings.recency_weight,
            confidence_w=settings.confidence_weight,
        )
        scores = await scorer.score_batch(memories, session=session, concurrency=10)
        await session.commit()
        return {"agent_id": agent_id, "scored": len(scores)}
    except Exception as exc:
        raise _request_error(request, 500, f"Scoring failed: {exc}") from exc


@router.post("/decay/{agent_id}", summary="Run immediate decay cycle for agent")
async def decay_agent(agent_id: str, request: Request) -> dict:
    try:
        engine = DecayEngine(session_factory, settings, DecayPolicyRegistry())
        result = await engine.run_decay_cycle(agent_id=agent_id)
        return {
            "agent_id": result.agent_id,
            "processed": result.processed,
            "decayed": result.decayed,
            "archived": result.archived,
            "skipped_promoted": result.skipped_promoted,
        }
    except Exception as exc:
        raise _request_error(request, 500, f"Decay failed: {exc}") from exc


@router.get("/preview/{agent_id}", summary="Preview reflection effects without writing")
async def preview_reflection(agent_id: str, request: Request) -> dict[str, int]:
    try:
        llm = _build_llm_adapter()
        pipeline = FullReflectionPipeline(session_factory, llm, settings)
        return await pipeline.preview(
            PipelineContext(
                agent_id=agent_id,
                job_id="preview",
                batch_size=settings.reflection_batch_size,
                dry_run=True,
                options={"dry_run": True},
            )
        )
    except Exception as exc:
        raise _request_error(request, 500, f"Preview failed: {exc}") from exc
