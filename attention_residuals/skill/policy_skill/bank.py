"""Dual-granularity skill bank · PR-018.

Refined spec: ``skill-research/04-route-policy-skill-couple/PR-018-*``.

The bank holds two kinds of skill:

* :class:`TaskSkill` — slow-loop scope ("hold P99 below target over the
  next hour"). Parametric; evaluated on a long horizon.
* :class:`StepSkill` — fast-loop scope (per-tick combiner adjustments),
  reusing :class:`PatchTarget`.

Both share the namespace but maintain **independent** per-skill
metadata; the granularity is an explicit field rather than encoded in
the id so downstream services can filter cheaply.

Requirements:

* REQ-DAT-* · data-structure invariants
* REQ-RTE-* · retriever / router read through bank
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    Iterable,
    Iterator,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
)

import numpy as np

from attention_residuals.skill.types import (
    Granularity,
    PatchTarget,
    SkillRecord,
)


# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TaskSkill:
    """A long-horizon objective template."""

    skill_id: str
    horizon_ticks: int
    objective_template: str          # e.g. "minimize P99 over horizon"
    params: Mapping[str, float] = field(default_factory=dict)
    tags: frozenset[str] = frozenset()

    def to_dict(self) -> dict:
        return {
            "skill_id": self.skill_id,
            "horizon_ticks": int(self.horizon_ticks),
            "objective_template": self.objective_template,
            "params": dict(self.params),
            "tags": sorted(self.tags),
            "granularity": Granularity.TASK.value,
        }


@dataclass(frozen=True)
class StepSkill:
    """A per-tick combiner adjustment wrapping a :class:`SkillRecord`."""

    skill_id: str
    targets: Tuple[PatchTarget, ...]
    trigger: Mapping[str, float] = field(default_factory=dict)
    tags: frozenset[str] = frozenset()

    def to_dict(self) -> dict:
        return {
            "skill_id": self.skill_id,
            "targets": [t.to_dict() for t in self.targets],
            "trigger": dict(self.trigger),
            "tags": sorted(self.tags),
            "granularity": Granularity.STEP.value,
        }


# ---------------------------------------------------------------------------
# Bank
# ---------------------------------------------------------------------------


class DualGranularitySkillBank:
    """Two-index in-memory store of :class:`TaskSkill` + :class:`StepSkill`.

    The bank is deliberately **pure data + index** — it has no knowledge
    of utility, routing, or lifecycle. Those are the router's / repo's
    responsibilities.

    Thread-safety: single RLock, v1 single-process.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, TaskSkill] = {}
        self._steps: dict[str, StepSkill] = {}
        self._lock = threading.RLock()

    # -------------------------------------------------- mutators

    def put_task(self, skill: TaskSkill) -> None:
        with self._lock:
            self._tasks[skill.skill_id] = skill

    def put_step(self, skill: StepSkill) -> None:
        with self._lock:
            self._steps[skill.skill_id] = skill

    def remove(self, skill_id: str) -> bool:
        with self._lock:
            removed = False
            if skill_id in self._tasks:
                del self._tasks[skill_id]
                removed = True
            if skill_id in self._steps:
                del self._steps[skill_id]
                removed = True
            return removed

    def from_skill_record(self, record: SkillRecord) -> StepSkill:
        """Convenience: wrap a :class:`SkillRecord` into a :class:`StepSkill`."""
        skill = StepSkill(
            skill_id=record.skill_id,
            targets=record.targets,
            trigger={},
            tags=record.tags,
        )
        self.put_step(skill)
        return skill

    # -------------------------------------------------- accessors

    def get_task(self, skill_id: str) -> Optional[TaskSkill]:
        with self._lock:
            return self._tasks.get(skill_id)

    def get_step(self, skill_id: str) -> Optional[StepSkill]:
        with self._lock:
            return self._steps.get(skill_id)

    def task_ids(self) -> List[str]:
        with self._lock:
            return list(self._tasks.keys())

    def step_ids(self) -> List[str]:
        with self._lock:
            return list(self._steps.keys())

    def all_ids(self, granularity: Optional[Granularity] = None) -> List[str]:
        with self._lock:
            if granularity is Granularity.TASK:
                return list(self._tasks)
            if granularity is Granularity.STEP:
                return list(self._steps)
            return list(self._tasks) + [
                sid for sid in self._steps if sid not in self._tasks
            ]

    def query(
        self,
        granularity: Optional[Granularity] = None,
        trigger_match: Optional[Mapping[str, float]] = None,
    ) -> List[Tuple[str, Granularity]]:
        """Return (skill_id, granularity) pairs that match the filter.

        A ``StepSkill`` matches ``trigger_match`` when every key in
        ``trigger_match`` is either absent from the skill's own trigger
        (wildcard) or numerically ``close_enough``. Task skills pass
        through unfiltered unless ``granularity=STEP`` is specified.
        """
        out: List[Tuple[str, Granularity]] = []
        with self._lock:
            if granularity is None or granularity is Granularity.TASK:
                for sid in self._tasks:
                    out.append((sid, Granularity.TASK))
            if granularity is None or granularity is Granularity.STEP:
                for sid, skill in self._steps.items():
                    if self._trigger_matches(skill.trigger, trigger_match):
                        out.append((sid, Granularity.STEP))
        return out

    # -------------------------------------------------- internals

    @staticmethod
    def _trigger_matches(
        own: Mapping[str, float],
        incoming: Optional[Mapping[str, float]],
    ) -> bool:
        if not incoming or not own:
            return True
        for key, value in own.items():
            probe = incoming.get(key)
            if probe is None:
                continue
            if abs(float(probe) - float(value)) > 1e-3:
                return False
        return True

    def __len__(self) -> int:
        with self._lock:
            return len(self._tasks) + len(self._steps)


__all__ = [
    "DualGranularitySkillBank",
    "StepSkill",
    "TaskSkill",
]
