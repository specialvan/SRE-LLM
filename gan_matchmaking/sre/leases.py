"""Lease primitives for process-level writer ownership.

``PerServiceLock`` protects threads inside one process. A service that uses a
single SQLite state file also needs a process-level guard so two HTTP servers do
not write the same store at once. This module provides a small local file lease
for single-node deployments and a narrow interface that can later be backed by
Redis, etcd, PostgreSQL advisory locks, or a Kubernetes Lease.
"""
from __future__ import annotations

import json
import os
import socket
import threading
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..core.errors import DataError, GanError


class LeaseNotAcquiredError(GanError):
    """Raised when another owner already holds the process lease."""

    code = "gan.lease.not_acquired"


@dataclass(frozen=True)
class LeaseSnapshot:
    owner: str
    token: str
    pid: int
    acquired_at: float
    expires_at: float

    @property
    def expired(self) -> bool:
        return self.expires_at <= time.time()

    def as_dict(self) -> dict[str, object]:
        return {
            "owner": self.owner,
            "token": self.token,
            "pid": self.pid,
            "acquired_at": self.acquired_at,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> "LeaseSnapshot":
        try:
            return cls(
                owner=str(raw["owner"]),
                token=str(raw["token"]),
                pid=int(raw.get("pid", 0)),
                acquired_at=float(raw["acquired_at"]),
                expires_at=float(raw["expires_at"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise DataError("invalid lease file payload", details={"raw": dict(raw)}) from exc


@dataclass
class FileLease:
    """Local atomic lock-file lease with stale-owner takeover.

    This is intended for a single host or one ReadWriteOnce PVC. It is not a
    distributed consensus primitive.
    """

    path: str | Path
    owner: str = field(default_factory=lambda: f"{socket.gethostname()}:{os.getpid()}")
    ttl_seconds: float = 60.0
    now: Callable[[], float] = time.time
    _token: Optional[str] = field(default=None, init=False, repr=False)

    @property
    def held(self) -> bool:
        return self._token is not None

    def read(self) -> Optional[LeaseSnapshot]:
        path = Path(self.path)
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except json.JSONDecodeError as exc:
            raise DataError("invalid lease file JSON", details={"path": str(path)}) from exc
        if not isinstance(raw, Mapping):
            raise DataError("lease file must contain a JSON object", details={"path": str(path)})
        return LeaseSnapshot.from_mapping(raw)

    def acquire(self) -> "FileLease":
        if self.ttl_seconds <= 0:
            raise DataError("ttl_seconds must be > 0", details={"ttl_seconds": self.ttl_seconds})
        if self.held:
            return self

        path = Path(self.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        token = uuid.uuid4().hex

        while True:
            started = float(self.now())
            payload = LeaseSnapshot(
                owner=self.owner,
                token=token,
                pid=os.getpid(),
                acquired_at=started,
                expires_at=started + float(self.ttl_seconds),
            )
            try:
                fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                current = self.read()
                if current is None:
                    continue
                if current is not None and current.expires_at <= float(self.now()):
                    try:
                        path.unlink()
                    except FileNotFoundError:
                        pass
                    continue
                raise LeaseNotAcquiredError(
                    "lease already held",
                    details={
                        "path": str(path),
                        "owner": None if current is None else current.owner,
                        "expires_at": None if current is None else current.expires_at,
                    },
                )

            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(payload.as_dict(), fh, ensure_ascii=False, sort_keys=True)
                self._token = token
                return self
            except Exception:
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
                raise

    def refresh(self) -> LeaseSnapshot:
        if not self.held or self._token is None:
            raise DataError("cannot refresh a lease that is not held")
        path = Path(self.path)
        current = self.read()
        if current is None or current.token != self._token:
            raise LeaseNotAcquiredError(
                "lease ownership was lost",
                details={"path": str(path), "owner": None if current is None else current.owner},
            )
        refreshed = LeaseSnapshot(
            owner=current.owner,
            token=current.token,
            pid=current.pid,
            acquired_at=current.acquired_at,
            expires_at=float(self.now()) + float(self.ttl_seconds),
        )
        tmp = path.with_name(f".{path.name}.{self._token}.tmp")
        tmp.write_text(
            json.dumps(refreshed.as_dict(), ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        tmp.replace(path)
        return refreshed

    def release(self) -> None:
        path = Path(self.path)
        try:
            current = self.read()
        except DataError:
            current = None
        if current is not None and current.token == self._token:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        self._token = None

    def __enter__(self) -> "FileLease":
        return self.acquire()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


class LeaseRefreshLoop:
    """Context manager that keeps a lease fresh while a server runs."""

    def __init__(
        self,
        lease: FileLease,
        *,
        interval_seconds: Optional[float] = None,
    ) -> None:
        self.lease = lease
        self.interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.error: Optional[BaseException] = None

    def __enter__(self) -> "LeaseRefreshLoop":
        self.lease.acquire()
        interval = self.interval_seconds
        if interval is None:
            interval = max(1.0, min(self.lease.ttl_seconds / 3.0, 30.0))
        self._thread = threading.Thread(
            target=self._run,
            args=(float(interval),),
            name="gan-lease-refresh",
            daemon=True,
        )
        self._thread.start()
        return self

    def _run(self, interval: float) -> None:
        while not self._stop.wait(interval):
            try:
                self.lease.refresh()
            except BaseException as exc:  # pragma: no cover - surfaced by ``error``.
                self.error = exc
                self._stop.set()
                return

    def __exit__(self, exc_type, exc, tb) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self.lease.release()
