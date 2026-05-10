"""Circuit breaker for the decision pipeline itself.

If ``decide`` keeps throwing (e.g. the underlying store is down, or a
numerical routine keeps failing), we shouldn't keep retrying — that
amplifies the incident. The breaker trips after ``failure_threshold``
consecutive failures; while it's open, the pipeline short-circuits to
``ESCALATE`` so a human takes over.

After ``recovery_seconds`` the breaker moves to half-open: the next decide
is allowed through, and success/failure chooses whether to close or reopen.
"""
from __future__ import annotations

import enum
import threading
import time
from dataclasses import dataclass, field


class BreakerState(str, enum.Enum):
    CLOSED = "closed"          # normal
    OPEN = "open"              # short-circuiting
    HALF_OPEN = "half_open"    # one test call allowed


@dataclass
class CircuitBreaker:
    failure_threshold: int = 5
    recovery_seconds: float = 30.0

    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _state: BreakerState = field(default=BreakerState.CLOSED, init=False, repr=False)
    _failures: int = field(default=0, init=False, repr=False)
    _opened_at: float = field(default=0.0, init=False, repr=False)

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------
    @property
    def state(self) -> BreakerState:
        with self._lock:
            if self._state == BreakerState.OPEN and \
               time.monotonic() - self._opened_at >= self.recovery_seconds:
                self._state = BreakerState.HALF_OPEN
            return self._state

    def allow(self) -> bool:
        """Return True if the breaker lets the call through."""
        return self.state in (BreakerState.CLOSED, BreakerState.HALF_OPEN)

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._state = BreakerState.CLOSED

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self.failure_threshold:
                self._state = BreakerState.OPEN
                self._opened_at = time.monotonic()

    # Convenience introspection used by metrics / logs.
    def snapshot(self) -> dict:
        with self._lock:
            return {
                "state": self._state.value,
                "failures": self._failures,
                "opened_at": self._opened_at,
            }
