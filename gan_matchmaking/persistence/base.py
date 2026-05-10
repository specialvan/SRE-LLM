"""Persistence protocols.

Every implementation must be safe to use from a single process with multiple
threads. Cross-process coordination is an operator concern — use the SQLite
backend with ``locking_mode=EXCLUSIVE`` or front with a Redis lease.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Iterable, List, Mapping, Optional, Tuple

from ..sre.domain import Decision, Service


@dataclass(frozen=True)
class Observation:
    """One release outcome, used for audit and for training the Cox / EOMM
    models.

    Fields are intentionally flat and JSON-friendly so the store can be
    inspected by any SQL client or log tool without the Python runtime.
    """
    service_id: str
    success: bool
    timestamp: float                    # unix seconds.
    duration_seconds: float             # time since previous release.
    features: Optional[Mapping[str, float]] = None
    correlation_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Abstract repositories
# ---------------------------------------------------------------------------
class ServiceRepository(abc.ABC):
    """Persistent storage for :class:`Service` reliability state."""

    @abc.abstractmethod
    def get(self, service_id: str) -> Optional[Service]: ...

    @abc.abstractmethod
    def save(self, service: Service) -> None: ...

    @abc.abstractmethod
    def list_ids(self) -> List[str]: ...

    @abc.abstractmethod
    def delete(self, service_id: str) -> bool: ...


class SynergyRepository(abc.ABC):
    """Persistent storage for the dependency synergy graph."""

    @abc.abstractmethod
    def increment(self, a: str, b: str, win: bool) -> None:
        """Record one co-release of ``(a, b)`` with success / failure."""

    @abc.abstractmethod
    def stats(self, a: str, b: str) -> Tuple[int, int]:
        """Return ``(games_together, wins_together)``."""

    @abc.abstractmethod
    def edges(self) -> Iterable[Tuple[str, str, int, int]]:
        """Yield ``(a, b, games, wins)`` tuples for every known edge."""


class ObservationRepository(abc.ABC):
    """Append-only audit log for observations and decisions."""

    @abc.abstractmethod
    def record(self, observation: Observation) -> None: ...

    @abc.abstractmethod
    def record_decision(self, decision: Decision) -> None: ...

    @abc.abstractmethod
    def recent_observations(self, service_id: str, limit: int = 200
                            ) -> List[Observation]: ...

    @abc.abstractmethod
    def observations(self) -> Iterable[Observation]: ...


class PipelineStore(abc.ABC):
    """Bundle of the three repositories used by the pipeline.

    Implementations are context-managed so resources (SQLite connections,
    file locks) are released deterministically.
    """

    services: ServiceRepository
    synergy: SynergyRepository
    observations: ObservationRepository

    def __enter__(self) -> "PipelineStore":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        """Release any underlying handles. Default: no-op."""
