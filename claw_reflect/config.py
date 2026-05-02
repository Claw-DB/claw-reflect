"""Application settings for claw-reflect, loaded from environment variables via pydantic-settings."""

from __future__ import annotations

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All claw-reflect configuration, sourced from env vars with prefix ``REFLECT_``."""

    model_config = SettingsConfigDict(env_prefix="REFLECT_", env_file=".env", extra="ignore")

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------
    database_url: str  # REFLECT_DATABASE_URL — asyncpg DSN
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # ------------------------------------------------------------------
    # Redis / Celery
    # ------------------------------------------------------------------
    redis_url: str = "redis://localhost:6379/0"  # REFLECT_REDIS_URL
    celery_concurrency: int = 4

    # ------------------------------------------------------------------
    # LLM
    # ------------------------------------------------------------------
    llm_provider: str = "anthropic"  # anthropic | openai | ollama
    llm_model: str = "claude-sonnet-4-20250514"
    llm_api_key: SecretStr  # REFLECT_LLM_API_KEY
    llm_base_url: str | None = None  # for Ollama or custom endpoints
    llm_max_tokens: int = 2048
    llm_timeout_secs: float = 30.0
    llm_max_retries: int = 3

    # ------------------------------------------------------------------
    # Reflection job settings
    # ------------------------------------------------------------------
    reflection_batch_size: int = 50  # memories per reflection run
    reflection_interval_minutes: int = 30
    decay_interval_hours: int = 6
    score_refresh_interval_hours: int = 12

    # ------------------------------------------------------------------
    # Scoring weights
    # ------------------------------------------------------------------
    importance_weight: float = 0.4
    recency_weight: float = 0.35
    confidence_weight: float = 0.25

    # ------------------------------------------------------------------
    # Decay
    # ------------------------------------------------------------------
    default_decay_policy: str = "exponential"
    decay_half_life_days: float = 30.0
    archive_threshold_score: float = 0.05
    min_score_to_keep: float = 0.02

    # ------------------------------------------------------------------
    # Duplication
    # ------------------------------------------------------------------
    duplicate_similarity_threshold: float = 0.92

    # ------------------------------------------------------------------
    # Service
    # ------------------------------------------------------------------
    api_host: str = "0.0.0.0"
    api_port: int = 8090
    debug: bool = False
    log_level: str = "INFO"
    log_format: str = "json"  # json | console


settings = Settings()  # type: ignore[call-arg]
