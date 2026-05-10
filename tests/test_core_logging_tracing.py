"""Tests for :mod:`gan_matchmaking.core.logging` and :mod:`gan_matchmaking.core.tracing`."""
from __future__ import annotations

import io
import json
import logging

import pytest

from gan_matchmaking.core.logging import JsonLineFormatter, JsonLineLogger, get_logger
from gan_matchmaking.core.tracing import (
    current_correlation_id,
    span,
    with_correlation_id,
)


def _parse_json_lines(stream: io.StringIO):
    stream.seek(0)
    return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]


def _logger_to_buffer(name: str):
    """Build a JsonLineLogger that writes to an in-memory buffer."""
    logger = logging.getLogger(name)
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JsonLineFormatter())
    logger.addHandler(handler)
    return JsonLineLogger.__new__(JsonLineLogger), logger, buf


def _wrap_logger(logger):
    jll = JsonLineLogger.__new__(JsonLineLogger)
    jll._logger = logger  # type: ignore[attr-defined]
    return jll


def test_json_line_formatter_emits_event():
    _, raw, buf = _logger_to_buffer("t1")
    jll = _wrap_logger(raw)
    jll.info("thing.happened", foo=1, bar="x")
    lines = _parse_json_lines(buf)
    assert len(lines) == 1
    line = lines[0]
    assert line["event"] == "thing.happened"
    assert line["payload"]["foo"] == 1
    assert line["payload"]["bar"] == "x"
    assert line["level"] == "INFO"


def test_correlation_id_propagates_across_scopes():
    _, raw, buf = _logger_to_buffer("t2")
    jll = _wrap_logger(raw)
    with with_correlation_id("outer-id") as cid:
        assert cid == "outer-id"
        assert current_correlation_id() == "outer-id"
        jll.info("first")
        with with_correlation_id("inner-id"):
            assert current_correlation_id() == "inner-id"
            jll.info("second")
        jll.info("third")
    assert current_correlation_id() is None

    lines = _parse_json_lines(buf)
    assert [l["correlation_id"] for l in lines] == ["outer-id", "inner-id", "outer-id"]


def test_span_emits_start_and_finish():
    _, raw, buf = _logger_to_buffer("t3")
    jll = _wrap_logger(raw)
    with span(jll, "work", role="test"):
        pass
    events = [l["event"] for l in _parse_json_lines(buf)]
    assert "span.started" in events
    assert "span.finished" in events


def test_span_emits_failure_on_exception():
    _, raw, buf = _logger_to_buffer("t4")
    jll = _wrap_logger(raw)
    with pytest.raises(RuntimeError):
        with span(jll, "work"):
            raise RuntimeError("boom")
    lines = _parse_json_lines(buf)
    assert any(l["event"] == "span.failed" for l in lines)
    failed = next(l for l in lines if l["event"] == "span.failed")
    assert failed["payload"]["error_type"] == "RuntimeError"
    assert failed["payload"]["ok"] is False


def test_get_logger_is_cached():
    a = get_logger("same.name")
    b = get_logger("same.name")
    assert a is b
