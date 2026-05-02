"""MemoryPromotionPipeline — promotes high-value memories to long-term storage."""

from __future__ import annotations

from typing import Any

from claw_reflect.pipelines.base import BasePipeline


class MemoryPromotionPipeline(BasePipeline):
    """Promotes memory records that exceed the promotion score threshold to long-term storage."""

    async def run(self, agent_id: str, **kwargs: Any) -> dict[str, Any]:
        """Run promotion for *agent_id* and return count of newly promoted memories."""
        raise NotImplementedError
