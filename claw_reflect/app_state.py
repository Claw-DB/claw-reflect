"""Process-level runtime objects shared across API handlers and lifespan hooks."""

from __future__ import annotations

from claw_reflect.decay.scheduler import ReflectScheduler

_scheduler: ReflectScheduler | None = None


def set_scheduler(scheduler: ReflectScheduler) -> None:
    global _scheduler
    _scheduler = scheduler


def get_scheduler() -> ReflectScheduler | None:
    return _scheduler
