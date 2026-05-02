"""AgentProfile ORM model — aggregated long-term knowledge profile for an agent."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from claw_reflect.db.base import Base


class AgentProfile(Base):
    """Consolidated long-term knowledge profile built from an agent's reflected memory corpus."""

    __tablename__ = "agent_profiles"

    agent_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    preferences: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    facts: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    behaviour_patterns: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    memory_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    def __repr__(self) -> str:
        return f"<AgentProfile agent={self.agent_id!r} version={self.profile_version!r}>"

    def to_dict(self) -> dict[str, Any]:
        """Serialise the model to a plain dictionary."""
        return {
            "agent_id": self.agent_id,
            "preferences": self.preferences,
            "facts": self.facts,
            "behaviour_patterns": self.behaviour_patterns,
            "last_updated_at": self.last_updated_at.isoformat(),
            "memory_count": self.memory_count,
            "profile_version": self.profile_version,
        }
