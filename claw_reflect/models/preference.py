"""ExtractedPreference ORM model — agent preferences distilled from memory records."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from claw_reflect.db.base import Base


class ExtractedPreference(Base):
    """Stores a single preference key/value pair extracted from an agent's memory corpus."""

    __tablename__ = "extracted_preferences"
    __table_args__ = (
        UniqueConstraint("workspace_id", "agent_id", "category", "key", name="uq_preference_workspace_agent_cat_key"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
        index=True,
        default=lambda: uuid.UUID("00000000-0000-0000-0000-000000000000"),
    )
    agent_id: Mapped[str] = mapped_column(String(26), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[Any] = mapped_column(JSON, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    source_memory_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    last_confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    confirmation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    def __repr__(self) -> str:
        return f"<ExtractedPreference id={self.id!r} agent={self.agent_id!r} key={self.category!r}/{self.key!r}>"

    def to_dict(self) -> dict[str, Any]:
        """Serialise the model to a plain dictionary."""
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "category": self.category,
            "key": self.key,
            "value": self.value,
            "confidence": self.confidence,
            "source_memory_ids": self.source_memory_ids,
            "first_seen_at": self.first_seen_at.isoformat(),
            "last_confirmed_at": self.last_confirmed_at.isoformat(),
            "confirmation_count": self.confirmation_count,
            "is_active": self.is_active,
        }
