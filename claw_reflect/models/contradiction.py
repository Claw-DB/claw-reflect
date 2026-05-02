"""ContradictionRecord ORM model — tracks detected conflicts between memory records."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from claw_reflect.db.base import Base


class ContradictionRecord(Base):
    """Records a detected contradiction between two memory records for a given field."""

    __tablename__ = "contradiction_records"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
        index=True,
        default=lambda: uuid.UUID("00000000-0000-0000-0000-000000000000"),
    )
    agent_id: Mapped[str] = mapped_column(String(26), nullable=False, index=True)

    memory_id_a: Mapped[str] = mapped_column(String(26), nullable=False)
    memory_id_b: Mapped[str] = mapped_column(String(26), nullable=False)

    field: Mapped[str] = mapped_column(String(128), nullable=False)
    value_a: Mapped[Any] = mapped_column(JSON, nullable=False)
    value_b: Mapped[Any] = mapped_column(JSON, nullable=False)

    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True
    )

    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    resolution_strategy: Mapped[str | None] = mapped_column(String(32), nullable=True)  # keep_a | keep_b | merge | discard_both
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    winner_memory_id: Mapped[str | None] = mapped_column(String(26), nullable=True)

    def __repr__(self) -> str:
        return f"<ContradictionRecord id={self.id!r} agent={self.agent_id!r} field={self.field!r} resolved={self.resolved!r}>"

    def to_dict(self) -> dict[str, Any]:
        """Serialise the model to a plain dictionary."""
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "memory_id_a": self.memory_id_a,
            "memory_id_b": self.memory_id_b,
            "field": self.field,
            "value_a": self.value_a,
            "value_b": self.value_b,
            "detected_at": self.detected_at.isoformat(),
            "resolved": self.resolved,
            "resolution_strategy": self.resolution_strategy,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "winner_memory_id": self.winner_memory_id,
        }
