"""Lease primitive tests."""
from __future__ import annotations

import json

import pytest

from gan_matchmaking.service import __main__ as service_main
from gan_matchmaking.sre.leases import FileLease, LeaseNotAcquiredError


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
