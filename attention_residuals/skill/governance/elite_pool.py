"""Fixed-capacity admission pool · PR-015.

Refined spec: ``skill-research/refined/PR-015-elite-pool-refined.md``.

Three-state machine per member:

.. code-block::

                  admit                probation_done
    ┌─────┐ ────────────▶ ┌──────────┐ ───────────▶ ┌──────┐
    │ OUT │               │PROBATION │              │ ELITE│
    └─────┘               └──────────┘              └──────┘
       ▲                       │                         │
       │ reject                │ probation_fail          │ evicted by stronger candidate
       │                       ▼                         ▼
       │                  ┌─────────┐                ┌─────────┐
       └──────────────────│ RETIRED │◀───────────────│ RETIRED │
                          └─────────┘                └─────────┘

Invariants:

* ``|members| ≤ capacity``
* ``|elite| + |probation| = |members|``
* A member is evicted by a stronger candidate *only* from ELITE state.
* EvictionEvent is always emitted when a member leaves the pool.

Requirements:

* REQ-VRF-005 · capacity bound
* REQ-VRF-006 · eviction event on evict
* REQ-VRF-007 · probation protection
"""

from __future__ import annotations

import random
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Mapping, Optional, Sequence


class MemberState(str, Enum):
    PROBATION = "probation"
    ELITE = "elite"


@dataclass(frozen=True)
class Elite:
    """Pool membership card."""

    variant_id: str
    score: float
    uncertainty: float = 0.0
    provenance: str = ""


@dataclass(frozen=True)
class EvictionEvent:
    evicted_id: str
    replaced_by_id: Optional[str]    # None on probation_fail
    score_delta: float
    reason: str = "admit"


@dataclass
class ElitePoolConfig:
    """See ADR-005: defaults are safe-first."""

    capacity: int = 32
    epsilon_uncertainty: float = 0.02
    min_probation_steps: int = 50
    probation_survival_min: float = 0.0
    explore_prob: float = 0.1


@dataclass
class _Member:
    card: Elite
    state: MemberState
    admitted_at_step: int
    probation_ends_at: int


class ElitePool:
    """Bounded-capacity admission pool with probation protection.

    The pool is a small in-memory state machine; it does not touch the
    :class:`SkillRepository` itself. The orchestrator (pipeline / gate)
    is responsible for mirroring the admit/evict events onto the repo.

    Parameters
    ----------
    config : ElitePoolConfig
    rng : random.Random, optional
        Injected RNG for deterministic tests.
    """

    def __init__(
        self,
        config: Optional[ElitePoolConfig] = None,
        rng: Optional[random.Random] = None,
    ) -> None:
        self._cfg = config or ElitePoolConfig()
        if self._cfg.capacity < 1:
            raise ValueError("capacity must be >= 1")
        self._rng = rng if rng is not None else random.Random(0xE11E)
        self._members: dict[str, _Member] = {}
        self._lock = threading.RLock()

    # -------------------------------------------------- public API

    @property
    def capacity(self) -> int:
        return self._cfg.capacity

    def try_admit(
        self, candidate: Elite, step: int = 0
    ) -> Optional[EvictionEvent]:
        """Attempt to admit ``candidate`` at pipeline ``step``.

        Returns an :class:`EvictionEvent` when admission displaces
        another member; returns ``None`` when the candidate is simply
        admitted into free capacity or is outright rejected.
        """
        with self._lock:
            # 1) Idempotent update — refresh in place.
            if candidate.variant_id in self._members:
                m = self._members[candidate.variant_id]
                self._members[candidate.variant_id] = _Member(
                    card=candidate,
                    state=m.state,
                    admitted_at_step=m.admitted_at_step,
                    probation_ends_at=m.probation_ends_at,
                )
                return None

            # 2) Free seats → admit into probation.
            if len(self._members) < self._cfg.capacity:
                self._add_new(candidate, step, state=MemberState.PROBATION)
                return None

            # 3) Pool full — only ELITE members are candidates for eviction.
            weakest = self._weakest_elite()
            if weakest is None:
                # All members still in probation; reject to preserve
                # the probation window (REQ-VRF-007).
                return None

            margin = candidate.score - weakest.card.score
            uncertainty = max(candidate.uncertainty, weakest.card.uncertainty)

            if margin > self._cfg.epsilon_uncertainty:
                evicted = self._pop(weakest.card.variant_id)
                self._add_new(candidate, step, state=MemberState.PROBATION)
                return EvictionEvent(
                    evicted_id=evicted.card.variant_id,
                    replaced_by_id=candidate.variant_id,
                    score_delta=margin,
                    reason="displaced_by_stronger",
                )

            if margin + uncertainty > 0 and self._rng.random() < self._cfg.explore_prob:
                # Exploratory swap within the uncertainty margin.
                evicted = self._pop(weakest.card.variant_id)
                self._add_new(candidate, step, state=MemberState.PROBATION)
                return EvictionEvent(
                    evicted_id=evicted.card.variant_id,
                    replaced_by_id=candidate.variant_id,
                    score_delta=margin,
                    reason="exploratory_swap",
                )

            # Otherwise reject.
            return None

    def evict_probation_breakers(self, step: int) -> List[EvictionEvent]:
        """Graduate or evict members whose probation window has closed."""
        events: List[EvictionEvent] = []
        with self._lock:
            for vid, m in list(self._members.items()):
                if m.state is not MemberState.PROBATION:
                    continue
                if step < m.probation_ends_at:
                    continue
                if m.card.score < self._cfg.probation_survival_min:
                    self._pop(vid)
                    events.append(
                        EvictionEvent(
                            evicted_id=vid,
                            replaced_by_id=None,
                            score_delta=-m.card.score,
                            reason="probation_fail",
                        )
                    )
                else:
                    self._members[vid] = _Member(
                        card=m.card,
                        state=MemberState.ELITE,
                        admitted_at_step=m.admitted_at_step,
                        probation_ends_at=m.probation_ends_at,
                    )
        return events

    def drop(self, variant_id: str, reason: str = "manual_evict") -> Optional[EvictionEvent]:
        """Force-remove a member (e.g. when redundancy detector flags a duplicate)."""
        with self._lock:
            if variant_id not in self._members:
                return None
            m = self._pop(variant_id)
            return EvictionEvent(
                evicted_id=variant_id,
                replaced_by_id=None,
                score_delta=-m.card.score,
                reason=reason,
            )

    # -------------------------------------------------- inspection

    def members(self) -> List[Elite]:
        with self._lock:
            return [m.card for m in self._members.values()]

    def member_states(self) -> Mapping[str, MemberState]:
        with self._lock:
            return {vid: m.state for vid, m in self._members.items()}

    def elite_ids(self) -> List[str]:
        with self._lock:
            return [
                vid
                for vid, m in self._members.items()
                if m.state is MemberState.ELITE
            ]

    def probation_ids(self) -> List[str]:
        with self._lock:
            return [
                vid
                for vid, m in self._members.items()
                if m.state is MemberState.PROBATION
            ]

    def __len__(self) -> int:
        return len(self._members)

    # -------------------------------------------------- internals

    def _add_new(self, card: Elite, step: int, state: MemberState) -> None:
        self._members[card.variant_id] = _Member(
            card=card,
            state=state,
            admitted_at_step=step,
            probation_ends_at=step + self._cfg.min_probation_steps,
        )

    def _pop(self, variant_id: str) -> _Member:
        return self._members.pop(variant_id)

    def _weakest_elite(self) -> Optional[_Member]:
        elite = [m for m in self._members.values() if m.state is MemberState.ELITE]
        if not elite:
            return None
        return min(elite, key=lambda m: m.card.score)


__all__ = [
    "Elite",
    "ElitePool",
    "ElitePoolConfig",
    "EvictionEvent",
    "MemberState",
]
