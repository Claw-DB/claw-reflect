"""Retry and fallback policies for LLM calls."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_random_exponential

from claw_reflect.llm.base import BaseLLMAdapter, LLMMessage, LLMResponse
from claw_reflect.logging import get_logger

logger = get_logger(__name__)


def _retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
        return exc.response.status_code in (429, 503)
    return False


@dataclass(slots=True)
class LLMRetryPolicy:
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0

    def get_tenacity_retry(self) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        return retry(
            stop=stop_after_attempt(self.max_attempts),
            wait=wait_random_exponential(multiplier=self.base_delay, max=self.max_delay),
            retry=retry_if_exception(_retryable),
            reraise=True,
        )

    async def with_fallback(
        self,
        primary: BaseLLMAdapter,
        fallback: BaseLLMAdapter,
        messages: list[LLMMessage],
        max_tokens: int,
    ) -> LLMResponse:
        try:

            @self.get_tenacity_retry()
            async def _call_primary() -> LLMResponse:
                return await primary.complete(messages=messages, max_tokens=max_tokens)

            return cast(LLMResponse, await _call_primary())
        except Exception as exc:
            logger.warning(
                "Primary LLM failed; activating fallback",
                primary_provider=primary.provider,
                fallback_provider=fallback.provider,
                error=str(exc),
            )
            return await fallback.complete(messages=messages, max_tokens=max_tokens)
