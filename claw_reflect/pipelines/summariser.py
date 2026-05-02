"""SummarisationPipeline — condenses raw session memories into compact summary records."""

from __future__ import annotations

from typing import Any

from claw_reflect.pipelines.base import BasePipeline


class SummarisationPipeline(BasePipeline):
    """Summarises a batch of old session memories into a single compact memory record."""

    async def run(self, agent_id: str, **kwargs: Any) -> dict[str, Any]:
        """Run summarisation for *agent_id* and return count of summaries produced."""
        raise NotImplementedError
