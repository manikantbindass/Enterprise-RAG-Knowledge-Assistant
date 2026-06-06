"""
Structlog configuration for Enterprise RAG Knowledge Assistant.

JSON output in production (machine-parseable for Loki/ELK).
Pretty colored output in development (human-readable).

Every log entry automatically includes:
- timestamp (ISO 8601 UTC)
- log level
- service_name
- request_id (from contextvars)
- org_id (from contextvars)
- user_id (from contextvars)
- event / message
"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import Any

import structlog
from structlog.types import EventDict, Processor

# ---------------------------------------------------------------------------
# Context variables — set per-request in middleware
# ---------------------------------------------------------------------------

_request_id_var: ContextVar[str] = ContextVar("request_id", default="")
_org_id_var: ContextVar[str] = ContextVar("org_id", default="")
_user_id_var: ContextVar[str] = ContextVar("user_id", default="")
_service_name_var: ContextVar[str] = ContextVar("service_name", default="rag-service")


def set_request_context(
    *,
    request_id: str = "",
    org_id: str = "",
    user_id: str = "",
    service_name: str = "",
) -> None:
    """
    Set per-request logging context.

    Call this at the start of each request (e.g., in middleware).
    Values are stored in contextvars — thread/task-safe.
    """
    if request_id:
        _request_id_var.set(request_id)
    if org_id:
        _org_id_var.set(org_id)
    if user_id:
        _user_id_var.set(user_id)
    if service_name:
        _service_name_var.set(service_name)


def clear_request_context() -> None:
    """Clear all per-request context variables."""
    _request_id_var.set("")
    _org_id_var.set("")
    _user_id_var.set("")


# ---------------------------------------------------------------------------
# Custom processors
# ---------------------------------------------------------------------------


def _inject_context(logger: Any, method: str, event_dict: EventDict) -> EventDict:
    """Inject request context into every log entry."""
    request_id = _request_id_var.get()
    org_id = _org_id_var.get()
    user_id = _user_id_var.get()
    service_name = _service_name_var.get()

    if request_id:
        event_dict["request_id"] = request_id
    if org_id:
        event_dict["org_id"] = org_id
    if user_id:
        event_dict["user_id"] = user_id
    if service_name:
        event_dict["service"] = service_name

    return event_dict


def _drop_color_message(logger: Any, method: str, event_dict: EventDict) -> EventDict:
    """Remove uvicorn's 'color_message' duplicate field from JSON output."""
    event_dict.pop("color_message", None)
    return event_dict


def _rename_event_to_message(
    logger: Any, method: str, event_dict: EventDict
) -> EventDict:
    """Rename 'event' → 'message' to match ELK/Loki conventions."""
    if "event" in event_dict:
        event_dict["message"] = event_dict.pop("event")
    return event_dict


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def configure_logging(
    *,
    log_level: str = "INFO",
    service_name: str = "rag-service",
    json_output: bool = True,
) -> None:
    """
    Configure structlog and stdlib logging globally.

    Call once at application startup (lifespan or __main__).

    Args:
        log_level: One of DEBUG / INFO / WARNING / ERROR / CRITICAL.
        service_name: Stamped onto every log entry.
        json_output: True for production JSON, False for dev pretty-print.
    """
    _service_name_var.set(service_name)

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        _inject_context,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        _drop_color_message,
    ]

    if json_output:
        processors: list[Processor] = [
            *shared_processors,
            structlog.processors.format_exc_info,
            _rename_event_to_message,
            structlog.processors.JSONRenderer(),
        ]
    else:
        processors = [
            *shared_processors,
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(log_level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Also configure stdlib logging to flow through structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.getLevelName(log_level.upper()),
    )

    # Quiet down noisy libraries
    for noisy_logger in ("uvicorn.access", "sqlalchemy.engine", "aio_pika", "aiormq"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.BoundLogger:
    """
    Get a structlog BoundLogger.

    Usage:
        logger = get_logger(__name__)
        logger.info("thing_happened", user_id=user.id, count=42)

    Args:
        name: Logger name (typically __name__). Defaults to root logger.

    Returns:
        Configured structlog BoundLogger.
    """
    return structlog.get_logger(name)
