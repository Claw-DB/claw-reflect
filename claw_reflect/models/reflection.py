"""ReflectionJob and ReflectionResult ORM models for tracking distillation pipeline runs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from claw_reflect.db.base import Base


class ReflectionJob(Base):
    """Tracks a single reflection pipeline execution for an agent."""

    __tablename__ = "reflection_jobs"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(26), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", index=True
    )  # pending | running | completed | failed
    job_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="full"
    )  # full | summarise | extract | deduplicate | score

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    memories_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    memories_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    memories_archived: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )

    results: Mapped[list[ReflectionResult]] = relationship(
        "ReflectionResult", back_populates="job", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<ReflectionJob id={self.id!r} agent={self.agent_id!r} status={self.status!r}>"
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialise the model to a plain dictionary."""
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "status": self.status,
            "job_type": self.job_type,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "memories_processed": self.memories_processed,
            "memories_updated": self.memories_updated,
            "memories_archived": self.memories_archived,
            "error_message": self.error_message,
            "metadata": self.metadata_,
        }


class ReflectionResult(Base):
    """Stores the output of a single pipeline operation on a memory record."""

    __tablename__ = "reflection_results"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("reflection_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    memory_id: Mapped[str] = mapped_column(String(26), nullable=False, index=True)
    result_type: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True
    )  # summary | preference | contradiction | duplicate
    output: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    applied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    job: Mapped[ReflectionJob] = relationship("ReflectionJob", back_populates="results")

    def __repr__(self) -> str:
        return (
            f"<ReflectionResult id={self.id!r} type={self.result_type!r} applied={self.applied!r}>"
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialise the model to a plain dictionary."""
        return {
            "id": self.id,
            "job_id": self.job_id,
            "memory_id": self.memory_id,
            "result_type": self.result_type,
            "output": self.output,
            "confidence": self.confidence,
            "applied": self.applied,
        }
