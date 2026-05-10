"""Persistence layer for the SRE self-iteration pipeline.

Stateful components — service ratings, dependency synergy graphs, release
observation history — need a store that survives process restarts. This
package defines:

- :class:`ServiceRepository`    — load / save Gaussian reliability ratings.
- :class:`SynergyRepository`    — co-release graph counters.
- :class:`ObservationRepository`— append-only audit log (used for Cox / EOMM
  training) and decision trace log.
- :class:`PipelineStore`        — a façade that bundles the three repositories
  and provides atomic "load → mutate → save" helpers.

Each repository has two implementations:

- ``InMemory<Name>Repository`` — zero-dep, used by tests and dry-runs.
- ``SQLite<Name>Repository``   — production-grade, backed by a single
  SQLite file so operators can inspect the store with any SQL client.
"""

from .base import (
    Observation,
    ObservationRepository,
    PipelineStore,
    ServiceRepository,
    SynergyRepository,
)
from .memory import (
    InMemoryObservationRepository,
    InMemoryPipelineStore,
    InMemoryServiceRepository,
    InMemorySynergyRepository,
)
from .sqlite import (
    SQLiteObservationRepository,
    SQLitePipelineStore,
    SQLiteServiceRepository,
    SQLiteSynergyRepository,
)

__all__ = [
    "Observation",
    "ObservationRepository",
    "PipelineStore",
    "ServiceRepository",
    "SynergyRepository",
    "InMemoryObservationRepository",
    "InMemoryPipelineStore",
    "InMemoryServiceRepository",
    "InMemorySynergyRepository",
    "SQLiteObservationRepository",
    "SQLitePipelineStore",
    "SQLiteServiceRepository",
    "SQLiteSynergyRepository",
]
