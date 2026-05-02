"""MemoryRecord ORM model — read-only mirror of claw-core memory records ingested via API."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from claw_reflect.db.base import Base


class MemoryRecord(Base):
    """Mirrors a memory record fetched from claw-core, enriched with scoring metadata."""

    __tablename__ = "memory_records"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
        index=True,
        default=lambda: uuid.UUID("00000000-0000-0000-0000-000000000000"),
    )
    agent_id: Mapped[str] = mapped_column(String(26), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    memory_type: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=False, default=dict)
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))

    # Scoring
    importance_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    recency_score: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.8)
    composite_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.5, index=True)

    # Reflection lifecycle
    reflection_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", index=True
    )  # pending | reflected | archived | decayed
    reflection_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_reflected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Promotion
    is_promoted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # TTL
    ttl_override_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:
        return f"<MemoryRecord id={self.id!r} agent={self.agent_id!r} status={self.reflection_status!r}>"

    def to_dict(self) -> dict[str, Any]:
        """Serialise the model to a plain dictionary."""
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "content": self.content,
            "memory_type": self.memory_type,
            "metadata": self.metadata_,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "importance_score": self.importance_score,
            "recency_score": self.recency_score,
            "confidence_score": self.confidence_score,
            "composite_score": self.composite_score,
            "reflection_status": self.reflection_status,
            "reflection_count": self.reflection_count,
            "last_reflected_at": self.last_reflected_at.isoformat() if self.last_reflected_at else None,
            "is_promoted": self.is_promoted,
            "promoted_at": self.promoted_at.isoformat() if self.promoted_at else None,
            "ttl_override_days": self.ttl_override_days,
        }
