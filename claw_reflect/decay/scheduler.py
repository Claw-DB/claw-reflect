"""DecayScheduler — registers and manages APScheduler jobs for periodic memory decay."""

from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from claw_reflect.config import settings
from claw_reflect.logging import get_logger

logger = get_logger(__name__)


class DecayScheduler:
    """Wraps APScheduler to run decay and archival jobs on the configured intervals."""

    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()

    def start(self) -> None:
        """Start the scheduler and register all decay-related jobs."""
        self._scheduler.add_job(
            self._decay_job,
            "interval",
            hours=settings.decay_interval_hours,
            id="decay_stale",
        )
        self._scheduler.start()
        logger.info("DecayScheduler started", interval_hours=settings.decay_interval_hours)

    def stop(self) -> None:
        """Shut down the scheduler gracefully."""
        self._scheduler.shutdown(wait=False)
        logger.info("DecayScheduler stopped")

    async def _decay_job(self) -> None:
        """Placeholder decay job — delegates to DecayEngine."""
        logger.info("Running scheduled decay job")
