"""Prometheus counters, histograms, and gauges for claw-reflect observability."""

from __future__ import annotations

import asyncio

import redis
from prometheus_client import Counter, Gauge, Histogram, Summary
from sqlalchemy import func, select

from claw_reflect.config import settings
from claw_reflect.db.session import session_factory
from claw_reflect.models.memory import MemoryRecord
from claw_reflect.models.profile import AgentProfile

# Application-level HTTP metrics
http_requests_total = Counter(
    "http_requests_total",
    "Total number of HTTP requests",
    ["method", "route", "status_code"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency by route",
    ["method", "route"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1, 2, 5, 10),
)

memories_processed_total = Counter(
    "memories_processed_total",
    "Total memories processed by pipeline",
    ["agent_id", "pipeline_name"],
)

memories_archived_total = Counter(
    "memories_archived_total",
    "Total archived memories by reason",
    ["agent_id", "reason"],
)

memories_promoted_total = Counter(
    "memories_promoted_total",
    "Total promoted memories",
    ["agent_id"],
)

contradictions_detected_total = Counter(
    "contradictions_detected_total",
    "Detected contradiction records",
    ["agent_id"],
)

contradictions_resolved_total = Counter(
    "contradictions_resolved_total",
    "Resolved contradiction records",
    ["agent_id", "strategy"],
)

preferences_extracted_total = Counter(
    "preferences_extracted_total",
    "Extracted preferences",
    ["agent_id", "category"],
)

duplicates_collapsed_total = Counter(
    "duplicates_collapsed_total",
    "Collapsed duplicate pairs",
    ["agent_id"],
)

llm_requests_total = Counter(
    "llm_requests_total",
    "LLM request outcomes",
    ["provider", "model", "pipeline", "status"],
)

decay_cycles_total = Counter(
    "decay_cycles_total",
    "Total decay cycles run",
    ["agent_id"],
)

profile_updated_total = Counter(
    "profile_updated_total",
    "Profile update events",
    ["agent_id"],
)

reflection_jobs_total = Counter(
    "reflection_jobs_total",
    "Reflection jobs created",
    ["job_type", "status"],
)

reflect_jobs_total = Counter(
    "reflect_jobs_total",
    "Reflection jobs by terminal status",
    ["status"],
)

reflect_pipeline_duration_seconds = Histogram(
    "reflect_pipeline_duration_seconds",
    "Duration of reflection stages",
    ["stage"],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60, 120),
)

reflect_llm_tokens_total = Counter(
    "reflect_llm_tokens_total",
    "Total LLM tokens consumed by provider",
    ["provider"],
)

reflect_active_workers = Gauge(
    "reflect_active_workers",
    "Approximate active workers",
)

reflect_queue_depth = Gauge(
    "reflect_queue_depth",
    "Approximate celery queue depth from Redis",
)

pipeline_duration_seconds = Histogram(
    "pipeline_duration_seconds",
    "Pipeline run duration in seconds",
    ["pipeline_name", "agent_id"],
    buckets=(0.5, 1, 5, 10, 30, 60, 120, 300),
)

llm_request_duration_seconds = Histogram(
    "llm_request_duration_seconds",
    "LLM latency by provider/model",
    ["provider", "model"],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30),
)

llm_tokens_used = Histogram(
    "llm_tokens_used",
    "Token usage per LLM request",
    ["provider", "model", "direction"],
    buckets=(100, 500, 1000, 2000, 4000),
)

active_memories_total = Gauge(
    "active_memories_total",
    "Current active memories by type",
    ["agent_id", "memory_type"],
)

pending_reflection_total = Gauge(
    "pending_reflection_total",
    "Current pending reflection memory count",
    ["agent_id"],
)

agent_profile_version = Gauge(
    "agent_profile_version",
    "Agent profile version",
    ["agent_id"],
)

scheduler_jobs_active = Gauge(
    "scheduler_jobs_active",
    "Number of active scheduler jobs",
)

task_duration_summary = Summary(
    "task_duration_seconds",
    "Duration summary for celery/background tasks",
    ["task_name"],
)

# Backward-compatible aliases used by already-implemented modules.
reflection_memories_processed_total = memories_processed_total
reflection_duration_seconds = pipeline_duration_seconds
archived_memories_total = memories_archived_total
decay_events_total = decay_cycles_total
llm_tokens_used_total = llm_tokens_used
composite_score_gauge = Gauge(
    "composite_score_gauge",
    "Mean composite score across non-archived memories",
)


async def _load_initial_gauges() -> None:
    async with session_factory() as session:
        result = await session.execute(
            select(
                MemoryRecord.agent_id,
                MemoryRecord.memory_type,
                func.count(MemoryRecord.id),
            )
            .where(MemoryRecord.reflection_status != "archived")
            .group_by(MemoryRecord.agent_id, MemoryRecord.memory_type)
        )
        for agent_id, memory_type, count in result.all():
            active_memories_total.labels(agent_id=agent_id, memory_type=memory_type).set(int(count))

        pending = await session.execute(
            select(MemoryRecord.agent_id, func.count(MemoryRecord.id))
            .where(MemoryRecord.reflection_status == "pending")
            .group_by(MemoryRecord.agent_id)
        )
        for agent_id, count in pending.all():
            pending_reflection_total.labels(agent_id=agent_id).set(int(count))

        profiles = await session.execute(select(AgentProfile.agent_id, AgentProfile.profile_version))
        for agent_id, version in profiles.all():
            agent_profile_version.labels(agent_id=agent_id).set(int(version))

        mean_score = await session.scalar(
            select(func.avg(MemoryRecord.composite_score)).where(MemoryRecord.reflection_status != "archived")
        )
        composite_score_gauge.set(float(mean_score or 0.0))


def init_metrics() -> None:
    """Initialize gauges from DB state without blocking app startup."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_load_initial_gauges())
    except RuntimeError:
        asyncio.run(_load_initial_gauges())

    refresh_queue_depth()


def refresh_queue_depth() -> None:
    """Update queue-depth gauge from Redis LLEN of celery queue."""
    try:
        client = redis.Redis.from_url(settings.redis_url)
        depth = int(client.llen("celery"))
        reflect_queue_depth.set(depth)
    except Exception:
        reflect_queue_depth.set(0)


def observe_llm_call(
    provider: str,
    model: str,
    pipeline: str,
    success: bool,
    duration_s: float,
    input_tokens: int,
    output_tokens: int,
) -> None:
    status = "success" if success else "error"
    llm_requests_total.labels(
        provider=provider,
        model=model,
        pipeline=pipeline,
        status=status,
    ).inc()
    llm_request_duration_seconds.labels(provider=provider, model=model).observe(duration_s)
    llm_tokens_used.labels(provider=provider, model=model, direction="input").observe(input_tokens)
    llm_tokens_used.labels(provider=provider, model=model, direction="output").observe(output_tokens)
    reflect_llm_tokens_total.labels(provider=provider).inc(input_tokens + output_tokens)
