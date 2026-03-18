"""Structured JSON logging configuration."""

from __future__ import annotations

import contextvars
import logging
import sys

from pythonjsonlogger.json import JsonFormatter

# Context variable for request ID tracing
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")


class RequestIDFilter(logging.Filter):
    """Attach request_id from contextvars to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get("")  # type: ignore[attr-defined]
        return True


def setup_logging(level: str = "INFO") -> None:
    """Configure structured JSON logging for the application."""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Clear existing handlers
    root_logger.handlers.clear()

    # JSON handler for stdout
    handler = logging.StreamHandler(sys.stdout)
    formatter = JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s",
        rename_fields={"asctime": "timestamp", "levelname": "level", "name": "logger"},
    )
    handler.setFormatter(formatter)
    handler.addFilter(RequestIDFilter())
    root_logger.addHandler(handler)

    # Suppress noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("skyfield.iokit").setLevel(logging.WARNING)
