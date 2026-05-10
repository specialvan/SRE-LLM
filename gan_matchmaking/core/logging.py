"""Structured JSON-line logging.

Every log record is a single line of JSON with this shape::

    {
      "ts": "2026-05-10T12:34:56.789Z",
      "level": "INFO",
      "logger": "gan.sre.pipeline",
      "event": "decision.emitted",
      "correlation_id": "abc123",
      "payload": { ... extra fields ... }
    }

Rationale
---------
- Line-delimited JSON is the de-facto SRE format (fluent-bit, loki, stackdriver
  all parse it natively).
- Keeping ``event`` separate from human text lets dashboards group by event
  without regex on free-form messages.
- The formatter stays dependency-free: we only use stdlib ``logging`` +
  ``json``.
"""
from __future__ import annotations

import datetime as _dt
import io
import json
import logging
import sys
import threading
from pathlib import Path
from typing import Any, Mapping, Optional, TextIO

from .tracing import current_correlation_id


_DEFAULT_LEVEL = logging.INFO
_LOCK = threading.Lock()
_CACHE: dict[str, logging.Logger] = {}


class JsonLineFormatter(logging.Formatter):
    """Render a :class:`logging.LogRecord` as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        payload: dict[str, Any] = {}
        # Pull extras (we don't want to leak internal LogRecord fields).
        reserved = set(logging.LogRecord(
            "", 0, "", 0, "", None, None
        ).__dict__.keys()) | {"message", "asctime"}
        for key, value in record.__dict__.items():
            if key in reserved or key.startswith("_"):
                continue
            if key == "event":
                continue
            payload[key] = _safe(value)

        obj = {
            "ts": _dt.datetime.fromtimestamp(record.created, tz=_dt.timezone.utc)
                              .strftime("%Y-%m-%dT%H:%M:%S.") + f"{record.msecs:03.0f}Z",
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event", record.getMessage() or "message"),
            "correlation_id": current_correlation_id(),
            "payload": payload,
        }
        if record.getMessage() and record.getMessage() != obj["event"]:
            obj["message"] = record.getMessage()
        if record.exc_info:
            obj["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(obj, ensure_ascii=False, default=_safe)


def _safe(value: Any) -> Any:
    try:
        json.dumps(value, default=str)
        return value
    except TypeError:
        return repr(value)


def _resolve_stream(sink: str) -> TextIO:
    if sink == "stderr":
        return sys.stderr
    if sink == "stdout":
        return sys.stdout
    path = Path(sink)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Not a context-managed file — the handler owns it for the process lifetime.
    return open(path, "a", encoding="utf-8")


def get_logger(
    name: str,
    level: str | int = _DEFAULT_LEVEL,
    sink: str = "stderr",
) -> logging.Logger:
    """Return a cached logger with the JSON-line formatter attached.

    Subsequent calls with the same ``name`` return the same logger instance;
    the first call's ``level`` / ``sink`` wins unless the caller re-configures
    manually.
    """
    with _LOCK:
        if name in _CACHE:
            return _CACHE[name]
        logger = logging.getLogger(name)
        logger.setLevel(_normalize_level(level))
        logger.propagate = False  # avoid duplicate emission via root.
        # Clear inherited handlers (pytest, root app) to avoid double lines.
        logger.handlers.clear()
        handler = logging.StreamHandler(_resolve_stream(sink))
        handler.setFormatter(JsonLineFormatter())
        logger.addHandler(handler)
        _CACHE[name] = logger
        return logger


def _normalize_level(level: str | int) -> int:
    if isinstance(level, int):
        return level
    mapping = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    return mapping.get(level.upper(), logging.INFO)


class JsonLineLogger:
    """Ergonomic façade: ``log.event("foo", k=v)`` emits a structured record."""

    def __init__(self, name: str, level: str | int = _DEFAULT_LEVEL, sink: str = "stderr"):
        self._logger = get_logger(name, level, sink)

    def event(self, event: str, level: str = "INFO", **fields: Any) -> None:
        numeric = _normalize_level(level)
        if not self._logger.isEnabledFor(numeric):
            return
        self._logger.log(numeric, event, extra={"event": event, **fields})

    def debug(self, event: str, **fields: Any) -> None:
        self.event(event, level="DEBUG", **fields)

    def info(self, event: str, **fields: Any) -> None:
        self.event(event, level="INFO", **fields)

    def warning(self, event: str, **fields: Any) -> None:
        self.event(event, level="WARNING", **fields)

    def error(self, event: str, **fields: Any) -> None:
        self.event(event, level="ERROR", **fields)

    def exception(self, event: str, **fields: Any) -> None:
        self._logger.exception(event, extra={"event": event, **fields})
