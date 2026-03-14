# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""
Structured JSON logger with correlation ID support.

Outputs one JSON object per log line, compatible with:
- Grafana Loki (label extraction from JSON fields)
- Scaleway Cockpit (structured log ingestion)
- ELK/OpenSearch (JSON parsing)
- CloudWatch Logs Insights (JSON queries)

Each log entry contains:
    timestamp, level, logger, message, correlation_id, service,
    and any additional context fields passed via `extra`.
"""

import json
import logging
import os
import time
import uuid
from collections import deque
from contextvars import ContextVar
from threading import Lock
from typing import Any

# Context variable for correlation ID propagation across async tasks
_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)

# In-memory ring buffer for recent logs (queryable via admin API)
_LOG_BUFFER_SIZE = int(os.getenv("OBSERVABILITY_LOG_BUFFER_SIZE", "5000"))
_log_buffer: deque[dict] = deque(maxlen=_LOG_BUFFER_SIZE)
_log_buffer_lock = Lock()

SERVICE_NAME = os.getenv("SERVICE_NAME", "chatvote-backend")
ENV = os.getenv("ENV", "local")


def set_correlation_id(cid: str | None = None) -> str:
    """Set (or generate) a correlation ID for the current async context."""
    if cid is None:
        cid = uuid.uuid4().hex[:16]
    _correlation_id.set(cid)
    return cid


def get_correlation_id() -> str | None:
    """Get the correlation ID for the current async context."""
    return _correlation_id.get()


def get_log_buffer(
    limit: int = 200,
    level: str | None = None,
    logger_name: str | None = None,
    search: str | None = None,
    correlation_id: str | None = None,
    since: float | None = None,
) -> list[dict]:
    """Query the in-memory log buffer with optional filters."""
    with _log_buffer_lock:
        entries = list(_log_buffer)

    # Apply filters
    if since is not None:
        entries = [e for e in entries if e.get("timestamp", 0) >= since]
    if level:
        level_upper = level.upper()
        entries = [e for e in entries if e.get("level") == level_upper]
    if logger_name:
        entries = [e for e in entries if logger_name in e.get("logger", "")]
    if correlation_id:
        entries = [e for e in entries if e.get("correlation_id") == correlation_id]
    if search:
        search_lower = search.lower()
        entries = [
            e
            for e in entries
            if search_lower in json.dumps(e, default=str).lower()
        ]

    # Return most recent first, limited
    return list(reversed(entries[-limit:]))


class StructuredJsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": record.created,
            "time": time.strftime(
                "%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)
            )
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": SERVICE_NAME,
            "env": ENV,
        }

        # Add correlation ID if available
        cid = _correlation_id.get()
        if cid:
            entry["correlation_id"] = cid

        # Add source location
        entry["source"] = {
            "file": record.filename,
            "line": record.lineno,
            "function": record.funcName,
        }

        # Merge extra fields (from logger.info("msg", extra={...}))
        for key in ("extra", "data", "labels", "sid", "stage", "elapsed_s",
                     "party", "model", "error_type", "trace_id"):
            val = getattr(record, key, None)
            if val is not None:
                entry[key] = val

        # If there's exception info, include it
        if record.exc_info and record.exc_info[0]:
            entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": self.formatException(record.exc_info),
            }

        # Store in ring buffer
        with _log_buffer_lock:
            _log_buffer.append(entry)

        return json.dumps(entry, default=str, ensure_ascii=False)


class StructuredLogger:
    """Wrapper that provides structured logging with context enrichment."""

    def __init__(self, name: str):
        self._logger = logging.getLogger(name)
        self.name = name

    def _log(self, level: int, msg: str, **kwargs: Any) -> None:
        extra_data = {}
        for key in list(kwargs.keys()):
            if key not in ("exc_info", "stack_info", "stacklevel"):
                extra_data[key] = kwargs.pop(key)
        if extra_data:
            kwargs["extra"] = {**kwargs.get("extra", {}), "data": extra_data}
        self._logger.log(level, msg, **kwargs)

    def debug(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.DEBUG, msg, **kwargs)

    def info(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.INFO, msg, **kwargs)

    def warning(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.WARNING, msg, **kwargs)

    def error(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.ERROR, msg, **kwargs)

    def critical(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.CRITICAL, msg, **kwargs)

    def exception(self, msg: str, **kwargs: Any) -> None:
        kwargs["exc_info"] = True
        self._log(logging.ERROR, msg, **kwargs)


def get_logger(name: str) -> StructuredLogger:
    """Get a structured logger instance."""
    return StructuredLogger(name)


def install_structured_logging(level: int = logging.INFO) -> None:
    """Install the structured JSON formatter on the root logger.

    Call this once at application startup (in aiohttp_app.py).
    After this, all loggers (including third-party) will emit JSON.
    """
    root = logging.getLogger()
    root.setLevel(level)

    # Replace all handlers with a single structured handler
    handler = logging.StreamHandler()
    handler.setFormatter(StructuredJsonFormatter())

    root.handlers.clear()
    root.addHandler(handler)
