"""Base LLM abstractions and shared retry handling."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

import httpx
from tenacity import AsyncRetrying, RetryCallState, retry_if_exception, stop_after_attempt
from tenacity import wait_random_exponential

from claw_reflect.logging import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class LLMMessage:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(slots=True)
class LLMResponse:
    content: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    finish_reason: str


def _is_retryable_exception(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
        return exc.response.status_code in (429, 503)
    return False


def _before_sleep_log(state: RetryCallState) -> None:
    exc = state.outcome.exception() if state.outcome else None
    delay_s = state.next_action.sleep if state.next_action else 0
    logger.warning(
        "LLM completion retrying",
        attempt=state.attempt_number,
        max_attempts=getattr(state.retry_object.stop, "max_attempt_number", None),
        delay_seconds=round(delay_s, 3),
        error_type=type(exc).__name__ if exc else None,
        error=str(exc) if exc else None,
    )


class BaseLLMAdapter(ABC):
    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @property
    @abstractmethod
    def provider(self) -> str: ...

    @abstractmethod
    async def complete(
        self,
        messages: list[LLMMessage],
        max_tokens: int,
        temperature: float = 0.2,
    ) -> LLMResponse: ...

    @abstractmethod
    async def health_check(self) -> bool: ...

    async def complete_with_retry(
        self,
        messages: list[LLMMessage],
        max_tokens: int,
        temperature: float = 0.2,
        max_retries: int = 3,
    ) -> LLMResponse:
        retryer = AsyncRetrying(
            stop=stop_after_attempt(max_retries),
            wait=wait_random_exponential(multiplier=1, max=30),
            retry=retry_if_exception(_is_retryable_exception),
            before_sleep=_before_sleep_log,
            reraise=True,
        )
        async for attempt in retryer:
            with attempt:
                logger.info(
                    "LLM completion attempt",
                    provider=self.provider,
                    model=self.model_name,
                    attempt=attempt.retry_state.attempt_number,
                )
                return await self.complete(
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )

        raise RuntimeError("LLM completion failed after retries")
