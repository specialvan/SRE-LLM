"""Lightweight correlation-id / span tracing.

The SRE pipeline often calls 7+ modules per decision. Without a
correlation-id in every log line it's impossible to reconstruct a single
decision chain. We expose two primitives:

- :func:`with_correlation_id`   — context manager that sets the id for all
  logs emitted in its scope (propagated via :class:`contextvars.ContextVar`).
- :func:`span`                  — context manager that times a block and emits
  a ``span.started`` / ``span.finished`` structured log event.

Both are safe under ``asyncio`` and threads because they use ``contextvars``.
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator, Optional


_CORRELATION_ID: ContextVar[Optional[str]] = ContextVar("gan.correlation_id", default=None)


def current_correlation_id() -> Optional[str]:
    """Return the correlation id for the current logical thread of execution."""
    return _CORRELATION_ID.get()


@contextmanager
def with_correlation_id(correlation_id: Optional[str] = None) -> Iterator[str]:
    """Bind a correlation id for the duration of the ``with`` block.

    If the caller does not provide one, a new hex id is generated.
    """
    cid = correlation_id or uuid.uuid4().hex[:16]
    token = _CORRELATION_ID.set(cid)
    try:
        yield cid
    finally:
        _CORRELATION_ID.reset(token)


class Span:
    """A timing span that emits structured log events on enter / exit."""

    def __init__(self, logger, name: str, **fields: Any):
        self._logger = logger
        self._name = name
        self._fields = dict(fields)
        self._started: Optional[float] = None
        self._error: Optional[BaseException] = None

    def __enter__(self) -> "Span":
        self._started = time.monotonic()
        self._emit("span.started")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        elapsed_ms = 0.0 if self._started is None else (time.monotonic() - self._started) * 1000.0
        self._error = exc
        if exc is None:
            self._emit("span.finished", elapsed_ms=elapsed_ms, ok=True)
        else:
            self._emit(
                "span.failed",
                level="ERROR",
                elapsed_ms=elapsed_ms,
                ok=False,
                error_type=exc_type.__name__ if exc_type else "unknown",
                error_message=str(exc),
            )
        return None  # do not suppress

    def _emit(self, event: str, *, level: str = "INFO", **extra: Any) -> None:
        payload = {**self._fields, **extra, "span": self._name,
                   "pid": os.getpid()}
        # Back-compat with either JsonLineLogger or plain logging.Logger.
        if hasattr(self._logger, "event"):
            self._logger.event(event, level=level, **payload)
        else:
            numeric = getattr(logging, level.upper(), logging.INFO)
            self._logger.log(numeric, event, extra={"event": event, **payload})


def span(logger, name: str, **fields: Any) -> Span:
    """Return a ready-to-use :class:`Span`. Sugar for ``Span(logger, name)``."""
    return Span(logger, name, **fields)
