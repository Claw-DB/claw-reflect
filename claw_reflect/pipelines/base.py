"""BasePipeline abstract class defining the interface for all distillation pipelines."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession


class BasePipeline(ABC):
    """Abstract base class that all reflection pipelines must implement."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @abstractmethod
    async def run(self, agent_id: str, **kwargs: Any) -> dict[str, Any]:
        """Execute the pipeline for the given agent and return a result summary."""
