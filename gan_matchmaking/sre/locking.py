"""Per-service mutual exclusion.

Two concurrent ``decide(ctx)`` calls for the same service would race on the
reliability rating. We serialise them with a per-service reentrant lock.
For cross-process coordination this is not enough. Use ``sre.leases`` at the
process boundary, and use a distributed lease or external database before
scaling one writable state store past a single instance.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Dict, Iterator


class PerServiceLock:
    """Keyed RLock factory."""

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._locks: Dict[str, threading.RLock] = {}

    def _get(self, key: str) -> threading.RLock:
        with self._guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = threading.RLock()
                self._locks[key] = lock
            return lock

    @contextmanager
    def acquire(self, key: str, timeout: float = 30.0) -> Iterator[None]:
        lock = self._get(key)
        acquired = lock.acquire(timeout=timeout)
        if not acquired:
            raise TimeoutError(f"could not acquire lock for {key!r} in {timeout}s")
        try:
            yield
        finally:
            lock.release()
