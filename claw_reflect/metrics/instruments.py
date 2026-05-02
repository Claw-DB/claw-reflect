"""Prometheus counters, histograms, and gauges for claw-reflect observability."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# ---------------------------------------------------------------------------
# Reflection pipeline metrics
# ---------------------------------------------------------------------------

reflection_jobs_total = Counter(
    "reflect_reflection_jobs_total",
    "Total number of reflection jobs started",
    ["job_type", "status"],
)

reflection_memories_processed_total = Counter(
    "reflect_memories_processed_total",
    "Total number of memories processed by reflection pipelines",
    ["pipeline"],
)

reflection_duration_seconds = Histogram(
    "reflect_reflection_duration_seconds",
    "Duration of reflection pipeline runs in seconds",
    ["pipeline"],
    buckets=(1, 5, 10, 30, 60, 120, 300),
)

# ---------------------------------------------------------------------------
# Decay metrics
# ---------------------------------------------------------------------------

decay_events_total = Counter(
    "reflect_decay_events_total",
    "Total number of decay events applied to memory records",
    ["policy"],
)

archived_memories_total = Counter(
    "reflect_archived_memories_total",
    "Total number of memories archived due to low composite score",
)

# ---------------------------------------------------------------------------
# Scoring metrics
# ---------------------------------------------------------------------------

composite_score_gauge = Gauge(
    "reflect_composite_score",
    "Current mean composite score across all active memory records",
)

# ---------------------------------------------------------------------------
# LLM metrics
# ---------------------------------------------------------------------------

llm_requests_total = Counter(
    "reflect_llm_requests_total",
    "Total number of LLM API requests made",
    ["provider", "status"],
)

llm_tokens_used_total = Counter(
    "reflect_llm_tokens_used_total",
    "Total number of LLM tokens consumed",
    ["provider"],
)

llm_request_duration_seconds = Histogram(
    "reflect_llm_request_duration_seconds",
    "Duration of LLM API calls in seconds",
    ["provider"],
    buckets=(0.5, 1, 2, 5, 10, 30, 60),
)
