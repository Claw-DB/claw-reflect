"""LLM retry and fallback logic using tenacity for resilient LLM calls."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from claw_reflect.config import settings
from claw_reflect.llm.base import BaseLLMAdapter
from claw_reflect.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


def llm_retry(func: Callable[..., Coroutine[Any, Any, T]]) -> Callable[..., Coroutine[Any, Any, T]]:
    """Decorator that adds exponential-backoff retry logic to an async LLM call."""
    return retry(
        stop=stop_after_attempt(settings.llm_max_retries),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        reraise=True,
    )(func)


async def complete_with_fallback(
    primary: BaseLLMAdapter,
    fallback: BaseLLMAdapter,
    system: str,
    user: str,
) -> str:
    """Attempt *primary* adapter; fall back to *fallback* on HTTP error."""
    try:
        return await primary.complete(system, user)
    except httpx.HTTPError as exc:
        logger.warning("Primary LLM failed, trying fallback", error=str(exc))
        return await fallback.complete(system, user)
