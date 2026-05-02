"""Structured logging configuration for claw-reflect using structlog."""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar

import structlog
from structlog.types import FilteringBoundLogger

# Context variable so request_id can be injected per-request
request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def _add_request_id(
    logger: logging.Logger,  # noqa: ARG001
    method: str,  # noqa: ARG001
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    """Inject the current request_id from context into every log record."""
    rid = request_id_var.get("")
    if rid:
        event_dict["request_id"] = rid
    return event_dict


def configure_logging(level: str = "INFO", fmt: str = "json") -> None:
    """Configure structlog with JSON or console renderer and ISO 8601 timestamps.

    Args:
        level: Logging level string (e.g. ``"INFO"``, ``"DEBUG"``).
        fmt:   ``"json"`` for machine-readable output, ``"console"`` for human-readable.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        _add_request_id,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]

    if fmt == "json":
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)


def get_logger(name: str) -> FilteringBoundLogger:
    """Return a structlog bound logger for *name*.

    Args:
        name: Logger name, typically ``__name__`` of the calling module.

    Returns:
        A :class:`structlog.types.FilteringBoundLogger` pre-bound with *name*.
    """
    return structlog.get_logger(name)
