"""Lease primitive tests."""
from __future__ import annotations

import io
import json
import logging

import pytest

from gan_matchmaking.core import MetricsRegistry
from gan_matchmaking.core.logging import JsonLineFormatter, JsonLineLogger
from gan_matchmaking.service import __main__ as service_main
from gan_matchmaking.service.app import build_app
from gan_matchmaking.sre.leases import (
    FileLease,
    LeaseNotAcquiredError,
    LeaseRefreshLoop,
)


def _parse_json_lines(stream: io.StringIO):
    stream.seek(0)
    return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]


def _logger_to_buffer(name: str = "gan.test.lease"):
    logger = logging.getLogger(name)
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JsonLineFormatter())
    logger.addHandler(handler)
    wrapped = JsonLineLogger.__new__(JsonLineLogger)
    wrapped._logger = logger  # type: ignore[attr-defined]
    return wrapped, buf


def test_file_lease_excludes_second_owner(tmp_path):
    path = tmp_path / "state.lock"
    first = FileLease(path, owner="first", ttl_seconds=60.0)
    first.acquire()
    try:
        second = FileLease(path, owner="second", ttl_seconds=60.0)
        with pytest.raises(LeaseNotAcquiredError):
            second.acquire()
    finally:
        first.release()


def test_file_lease_releases_to_next_owner(tmp_path):
    path = tmp_path / "state.lock"
    with FileLease(path, owner="first", ttl_seconds=60.0):
        assert path.exists()
    assert not path.exists()

    with FileLease(path, owner="second", ttl_seconds=60.0) as lease:
        assert lease.held
        assert lease.read().owner == "second"


def test_file_lease_takes_over_expired_owner(tmp_path):
    path = tmp_path / "state.lock"
    path.write_text(
        json.dumps({
            "owner": "old",
            "token": "old-token",
            "pid": 1,
            "acquired_at": 1.0,
            "expires_at": 2.0,
        }),
        encoding="utf-8",
    )

    now = lambda: 100.0
    lease = FileLease(path, owner="new", ttl_seconds=30.0, now=now)
    lease.acquire()
    try:
        snapshot = lease.read()
        assert snapshot.owner == "new"
        assert snapshot.expires_at == pytest.approx(130.0)
    finally:
        lease.release()


def test_file_lease_refresh_extends_expiry(tmp_path):
    path = tmp_path / "state.lock"
    clock = {"now": 10.0}
    lease = FileLease(path, owner="svc", ttl_seconds=10.0,
                      now=lambda: clock["now"])
    lease.acquire()
    try:
        assert lease.read().expires_at == pytest.approx(20.0)
        clock["now"] = 15.0
        refreshed = lease.refresh()
        assert refreshed.expires_at == pytest.approx(25.0)
        assert lease.read().expires_at == pytest.approx(25.0)
    finally:
        lease.release()


def test_service_main_acquires_and_releases_lease(tmp_path, monkeypatch):
    lease_path = tmp_path / "service.lock"
    db_path = tmp_path / "state.sqlite"
    seen = {}

    def fake_run_wsgi(_app, *, host, port):
        seen["host"] = host
        seen["port"] = port
        seen["leased"] = lease_path.exists()

    monkeypatch.setattr(service_main, "run_wsgi", fake_run_wsgi)
    code = service_main.main([
        "--host", "127.0.0.1",
        "--port", "0",
        "--state-db", str(db_path),
        "--lease-file", str(lease_path),
        "--lease-owner", "test-owner",
        "--lease-ttl-seconds", "30",
    ])

    assert code == 0
    assert seen == {"host": "127.0.0.1", "port": 0, "leased": True}
    assert not lease_path.exists()


def test_refresh_failure_flips_readiness(tmp_path):
    app = build_app(metrics=MetricsRegistry())
    app.bind_lease_metadata(path=str(tmp_path / "state.lock"), owner="test:1")

    app.mark_lease_unhealthy(RuntimeError("boom"))

    code, body = app.handle_ready(None)
    assert code == 503
    assert body["status"] == "not_ready"
    assert body["reason"] == "lease_unhealthy"
    assert body["details"]["reason"] == "RuntimeError"
    health_code, health_body = app.handle_health(None)
    assert health_code == 200
    assert health_body["status"] == "ok"


def test_refresh_failure_increments_metric(tmp_path):
    registry = MetricsRegistry()
    app = build_app(metrics=registry)
    app.bind_lease_metadata(path=str(tmp_path / "state.lock"), owner="test:1")

    app.mark_lease_unhealthy(RuntimeError("boom"))

    metric = registry.get("gan_lease_refresh_failures_total")
    assert metric is not None
    assert metric.value(labels={"reason": "RuntimeError"}) == pytest.approx(1.0)
    text = registry.export_prometheus()
    assert "gan_lease_refresh_failures_total" in text
    assert 'reason="RuntimeError"' in text


def test_refresh_failure_emits_structured_log(tmp_path):
    app = build_app(metrics=MetricsRegistry())
    logger, buf = _logger_to_buffer("gan.test.lease.failure")
    app.pipeline.logger = logger
    app.bind_lease_metadata(path=str(tmp_path / "state.lock"), owner="test:1")

    app.mark_lease_unhealthy(RuntimeError("boom"))

    lines = _parse_json_lines(buf)
    assert len(lines) == 1
    line = lines[0]
    assert line["level"] == "ERROR"
    assert line["event"] == "lease.refresh.failed"
    assert line["payload"]["lease_path"] == str(tmp_path / "state.lock")
    assert line["payload"]["owner"] == "test:1"
    assert line["payload"]["error_type"] == "RuntimeError"


def test_refresh_failure_does_not_spam(tmp_path):
    registry = MetricsRegistry()
    app = build_app(metrics=registry)
    logger, buf = _logger_to_buffer("gan.test.lease.no_spam")
    app.pipeline.logger = logger
    app.bind_lease_metadata(path=str(tmp_path / "state.lock"), owner="test:1")

    app.mark_lease_unhealthy(RuntimeError("a"))
    app.mark_lease_unhealthy(ValueError("b"))
    app.mark_lease_unhealthy(LeaseNotAcquiredError("c"))

    metric = registry.get("gan_lease_refresh_failures_total")
    assert metric is not None
    assert sum(metric.snapshot().values()) == pytest.approx(1.0)
    assert len(_parse_json_lines(buf)) == 1


def test_healthy_app_returns_ready():
    app = build_app(metrics=MetricsRegistry())

    code, body = app.handle_ready(None)

    assert code == 200
    assert body["status"] == "ready"


def test_loop_invokes_callback_on_refresh_failure(tmp_path, monkeypatch):
    lease = FileLease(tmp_path / "state.lock", owner="test", ttl_seconds=10.0)
    lease.acquire()
    calls = []

    def boom():
        raise RuntimeError("refresh exploded")

    monkeypatch.setattr(lease, "refresh", boom)
    loop = LeaseRefreshLoop(
        lease,
        interval_seconds=1.0,
        on_failure=lambda exc: calls.append(type(exc).__name__),
    )
    try:
        loop._run(0.0)  # exercise the failure branch deterministically
        assert loop.error is not None
        assert type(loop.error).__name__ == "RuntimeError"
        assert calls == ["RuntimeError"]
    finally:
        lease.release()
