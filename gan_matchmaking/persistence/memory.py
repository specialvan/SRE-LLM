"""In-memory implementations of the persistence protocols.

Used in tests and for dry-runs. Thread-safe via a single coarse lock; fine
because these are fallback stores, not hot paths.
"""

from __future__ import annotations

import threading
from collections import defaultdict, deque
from typing import Deque, Dict, Iterable, List, Optional, Tuple

from ..sre.domain import Decision, Service
from .base import (
    Observation,
    ObservationRepository,
    PipelineStore,
    ServiceRepository,
    SynergyRepository,
)


class InMemoryServiceRepository(ServiceRepository):
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._store: Dict[str, Service] = {}

    def get(self, service_id: str) -> Optional[Service]:
        with self._lock:
            svc = self._store.get(service_id)
            if svc is None:
                return None
            # Return a shallow copy to keep callers from mutating under us.
            return Service(**svc.as_dict())

    def save(self, service: Service) -> None:
        with self._lock:
            self._store[service.id] = Service(**service.as_dict())

    def list_ids(self, limit: Optional[int] = None) -> List[str]:
        with self._lock:
            ids = list(self._store.keys())
        return ids if limit is None else ids[:limit]

    def delete(self, service_id: str) -> bool:
        with self._lock:
            return self._store.pop(service_id, None) is not None


class InMemorySynergyRepository(SynergyRepository):
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._games: Dict[Tuple[str, str], int] = defaultdict(int)
        self._wins: Dict[Tuple[str, str], int] = defaultdict(int)

    @staticmethod
    def _key(a: str, b: str) -> Tuple[str, str]:
        return (a, b) if a < b else (b, a)

    def increment(self, a: str, b: str, win: bool) -> None:
        if a == b:
            return
        with self._lock:
            key = self._key(a, b)
            self._games[key] += 1
            if win:
                self._wins[key] += 1

    def stats(self, a: str, b: str) -> Tuple[int, int]:
        with self._lock:
            key = self._key(a, b)
            return self._games.get(key, 0), self._wins.get(key, 0)

    def edges(self, limit: Optional[int] = None) -> Iterable[Tuple[str, str, int, int]]:
        with self._lock:
            items = list(self._games.items())
        if limit is not None:
            items = items[:limit]
        for (a, b), games in items:
            yield a, b, games, self._wins.get((a, b), 0)


class InMemoryObservationRepository(ObservationRepository):
    def __init__(self, max_per_service: int = 1000) -> None:
        self._lock = threading.RLock()
        self._per_service: Dict[str, Deque[Observation]] = defaultdict(
            lambda: deque(maxlen=max_per_service)
        )
        self._decisions: List[Decision] = []
        self._max_per_service = max_per_service

    def record(self, observation: Observation) -> None:
        if observation.service_id == "":
            from ..core.errors import DataError

            raise DataError("observation.service_id must be non-empty")
        with self._lock:
            self._per_service[observation.service_id].append(observation)

    def record_decision(self, decision: Decision) -> None:
        with self._lock:
            self._decisions.append(decision)

    def recent_observations(
        self, service_id: str, limit: int = 200
    ) -> List[Observation]:
        with self._lock:
            dq = self._per_service.get(service_id)
            if not dq:
                return []
            return list(dq)[-limit:]

    def observations(self) -> Iterable[Observation]:
        with self._lock:
            all_items: List[Observation] = []
            for dq in self._per_service.values():
                all_items.extend(dq)
        all_items.sort(key=lambda o: o.timestamp)
        yield from all_items


class InMemoryPipelineStore(PipelineStore):
    def __init__(self) -> None:
        self.services = InMemoryServiceRepository()
        self.synergy = InMemorySynergyRepository()
        self.observations = InMemoryObservationRepository()
