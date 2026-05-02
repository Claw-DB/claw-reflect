"""DecayRecord ORM model — audit log of score decay events applied to memory records."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from claw_reflect.db.base import Base


class DecayRecord(Base):
    """Records the before/after scores for a single decay event on a memory record."""

    __tablename__ = "decay_records"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
        index=True,
        default=lambda: uuid.UUID("00000000-0000-0000-0000-000000000000"),
    )
    memory_id: Mapped[str] = mapped_column(String(26), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(String(26), nullable=False)
    decay_policy: Mapped[str] = mapped_column(String(32), nullable=False)
    score_before: Mapped[float] = mapped_column(Float, nullable=False)
    score_after: Mapped[float] = mapped_column(Float, nullable=False)
    decayed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True
    )
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    def __repr__(self) -> str:
        return f"<DecayRecord id={self.id!r} memory={self.memory_id!r} score={self.score_before:.3f}->{self.score_after:.3f}>"

    def to_dict(self) -> dict[str, Any]:
        """Serialise the model to a plain dictionary."""
        return {
            "id": self.id,
            "memory_id": self.memory_id,
            "agent_id": self.agent_id,
            "decay_policy": self.decay_policy,
            "score_before": self.score_before,
            "score_after": self.score_after,
            "decayed_at": self.decayed_at.isoformat(),
            "archived": self.archived,
        }
