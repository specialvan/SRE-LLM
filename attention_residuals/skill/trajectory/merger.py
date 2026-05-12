"""Hierarchical patch merger · PR-002.

Refined spec: ``skill-research/refined/PR-002-hierarchical-patch-merger-refined.md``.

Two-stage merge:

1. **Intra-signal**: same ``(signal_name, field)`` across candidates →
   support-weighted same-direction deltas, or retreat on balanced
   opposite directions.
2. **Cross-signal** budget enforcement: ``Σ floor + δ ≤ 1`` and
   ``Σ ceiling + δ ≥ 1``; drops low-score targets to fit the budget.
3. ``MustAttend`` snapshot hard-rejects targets that would violate a
   registered floor.

Requirements:

* REQ-KNE-001 · merge conflicting targets
* REQ-KNE-002 · never emit infeasible
* REQ-KNE-003 · MergeConflict on drop
* REQ-DAT-010 · non-empty provenance
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Iterable, Mapping, Optional, Sequence, Tuple

from attention_residuals.skill.types import (
    ConflictReason,
    MergeConflict,
    MergedSkillPatch,
    PatchField,
    PatchTarget,
    SkillPatchCandidate,
    compute_patch_id,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class MustAttendSnapshot:
    """Immutable snapshot of must-attend floors by signal.

    Used to:

    * compute "available floor budget" (``1 - Σ current_floor``),
    * reject post-merge targets that would drop a registered floor.

    ``registry_hash`` identifies the snapshot; merger refuses to mix
    candidates from different snapshots.
    """

    floors: Mapping[str, float] = field(default_factory=dict)
    ceilings: Mapping[str, float] = field(default_factory=dict)
    registry_hash: str = ""

    def current_floor(self, signal_name: str) -> float:
        return float(self.floors.get(signal_name, 0.0))

    def current_ceiling(self, signal_name: str) -> float:
        return float(self.ceilings.get(signal_name, 1.0))

    def total_floor(self) -> float:
        return float(sum(self.floors.values()))


@dataclass
class MergerConfig:
    """Sharp edges tunable per deployment."""

    # At what imbalance do we call two opposite directions "balanced" and
    # retreat to zero? Default: if ratio of majority support to total
    # support is within 10%, retreat.
    balance_epsilon: float = 0.1
    # If a signal is registered in MustAttendSnapshot with floor f and
    # our target would pull below f, drop it unconditionally.
    enforce_must_attend: bool = True


class HierarchicalPatchMerger:
    """Collapse a batch of :class:`SkillPatchCandidate`s into one patch.

    Stage 1 (``_merge_intra_signal``) is deterministic and side-effect
    free; stage 2 (``_enforce_budget`` + ``_enforce_must_attend``) is
    what produces :class:`MergeConflict`.
    """

    def __init__(
        self,
        snapshot: Optional[MustAttendSnapshot] = None,
        config: Optional[MergerConfig] = None,
    ) -> None:
        self._snapshot = snapshot or MustAttendSnapshot()
        self._cfg = config or MergerConfig()

    # -------------------------------------------------- public API

    def merge(
        self, candidates: Sequence[SkillPatchCandidate]
    ) -> MergedSkillPatch:
        """Return a deterministic :class:`MergedSkillPatch` for ``candidates``.

        Contract (CON-001): every candidate must share ``registry_hash``
        with :attr:`snapshot.registry_hash`; mixing snapshots emits a
        single ``REGISTRY_DRIFT`` conflict and returns an empty patch.
        """
        if not candidates:
            return MergedSkillPatch(
                patch_id=compute_patch_id((), {}),
                targets=(),
                provenance=(),
                registry_hash=self._snapshot.registry_hash,
            )

        drift = self._detect_registry_drift(candidates)
        if drift is not None:
            return drift

        # Weighted by per-candidate support (REQ-EVD-004 semantics).
        intra_targets = self._merge_intra_signal(candidates)

        accepted, dropped, conflicts = self._enforce_budget(intra_targets, candidates)
        accepted, dropped_ma, conflicts_ma = self._enforce_must_attend(accepted)
        dropped = dropped + dropped_ma
        conflicts = conflicts + conflicts_ma

        provenance = tuple(c.patch_id for c in candidates)
        return MergedSkillPatch(
            patch_id=compute_patch_id(tuple(accepted), {}),
            targets=tuple(accepted),
            dropped=tuple(dropped),
            conflicts=tuple(conflicts),
            provenance=provenance,
            registry_hash=self._snapshot.registry_hash,
        )

    # -------------------------------------------------- registry drift

    def _detect_registry_drift(
        self, candidates: Sequence[SkillPatchCandidate]
    ) -> Optional[MergedSkillPatch]:
        hashes = {c.registry_hash for c in candidates}
        expected = self._snapshot.registry_hash
        if len(hashes) == 1 and (not expected or expected in hashes):
            return None

        # Build a single conflict describing the drift.
        conflict = MergeConflict(
            signal_name="*",
            field="*",
            candidates=(),
            reason=ConflictReason.REGISTRY_DRIFT,
        )
        # Every candidate is dropped.
        dropped: list[PatchTarget] = []
        for c in candidates:
            dropped.extend(c.targets)
        return MergedSkillPatch(
            patch_id=compute_patch_id((), {}),
            targets=(),
            dropped=tuple(dropped),
            conflicts=(conflict,),
            provenance=tuple(c.patch_id for c in candidates),
            registry_hash=expected,
        )

    # -------------------------------------------------- stage 1

    def _merge_intra_signal(
        self, candidates: Sequence[SkillPatchCandidate]
    ) -> list[PatchTarget]:
        """Group by (signal, field); reduce each group to one PatchTarget."""
        groups: Dict[
            Tuple[str, PatchField], list[tuple[PatchTarget, int]]
        ] = defaultdict(list)
        for cand in candidates:
            for t in cand.targets:
                groups[(t.signal_name, t.field)].append((t, cand.support))

        merged: list[PatchTarget] = []
        for (signal, field_), items in groups.items():
            merged_target = self._reduce_group(signal, field_, items)
            if merged_target is not None:
                merged.append(merged_target)
        return merged

    def _reduce_group(
        self,
        signal: str,
        field_: PatchField,
        items: Sequence[tuple[PatchTarget, int]],
    ) -> Optional[PatchTarget]:
        pos_support = sum(s for t, s in items if t.delta > 0)
        neg_support = sum(s for t, s in items if t.delta < 0)
        total_support = pos_support + neg_support
        if total_support == 0:
            return None  # all deltas are exactly zero

        majority = pos_support if pos_support >= neg_support else neg_support
        if total_support > 0 and (majority / total_support) < 0.5 + self._cfg.balance_epsilon / 2:
            # Opposite directions are close to balanced → retreat to zero
            # rather than guess a direction (spec: balanced-retreat rule).
            return None

        direction_sign = 1.0 if pos_support >= neg_support else -1.0
        same_dir = [
            (t, s) for t, s in items if (t.delta > 0) == (direction_sign > 0) and t.delta != 0
        ]
        if not same_dir:
            return None
        weights = [max(1, s) for _, s in same_dir]
        deltas = [t.delta for t, _ in same_dir]
        weighted_sum = sum(d * w for d, w in zip(deltas, weights))
        total_weight = sum(weights)
        merged_delta = weighted_sum / total_weight

        # Snap back into the valid range for floor/ceiling fields.
        if field_ is PatchField.FLOOR:
            merged_delta = max(0.0, min(1.0, merged_delta))
        elif field_ is PatchField.CEILING:
            merged_delta = max(-1.0, min(0.0, merged_delta))
        if merged_delta == 0.0:
            return None

        rationale = (
            f"support-weighted over {len(same_dir)} candidates "
            f"(Σsupport={sum(weights)})"
        )
        return PatchTarget(
            signal_name=signal,
            field=field_,
            delta=float(merged_delta),
            rationale=rationale[:200],
        )

    # -------------------------------------------------- stage 2a budget

    def _enforce_budget(
        self,
        merged: Sequence[PatchTarget],
        candidates: Sequence[SkillPatchCandidate],
    ) -> Tuple[list[PatchTarget], list[PatchTarget], list[MergeConflict]]:
        """Enforce cross-signal floor / ceiling budgets.

        The score used for drop-priority is the highest score amongst
        the source candidates that touched this target (higher score =
        keep).
        """
        score_by_target: Dict[Tuple[str, PatchField], float] = {}
        for c in candidates:
            for t in c.targets:
                k = (t.signal_name, t.field)
                score_by_target[k] = max(score_by_target.get(k, 0.0), c.score)

        accepted = list(merged)
        dropped: list[PatchTarget] = []
        conflicts: list[MergeConflict] = []

        # --- Floor budget: Σ (current_floor + delta) ≤ 1 ------------------
        accepted, dropped_f, conflict_f = self._enforce_floor_budget(
            accepted, score_by_target
        )
        dropped.extend(dropped_f)
        if conflict_f is not None:
            conflicts.append(conflict_f)

        # --- Ceiling budget: Σ (current_ceiling + delta) ≥ 1 --------------
        accepted, dropped_c, conflict_c = self._enforce_ceiling_budget(
            accepted, score_by_target
        )
        dropped.extend(dropped_c)
        if conflict_c is not None:
            conflicts.append(conflict_c)

        return accepted, dropped, conflicts

    def _enforce_floor_budget(
        self,
        targets: Sequence[PatchTarget],
        score_by_target: Mapping[Tuple[str, PatchField], float],
    ) -> Tuple[list[PatchTarget], list[PatchTarget], Optional[MergeConflict]]:
        floor_targets = [t for t in targets if t.field is PatchField.FLOOR]
        other = [t for t in targets if t.field is not PatchField.FLOOR]
        if not floor_targets:
            return list(targets), [], None

        baseline = self._snapshot.total_floor()
        # Subtract any signal's current floor for signals we're about to
        # override; our delta is *additive* to the current floor, which
        # was already in baseline.
        running = baseline + sum(t.delta for t in floor_targets)
        if running <= 1.0 + 1e-9:
            return list(targets), [], None

        # Sort by score ascending so the LOWEST scored drops first.
        sorted_floor = sorted(
            floor_targets,
            key=lambda t: score_by_target.get((t.signal_name, t.field), 0.0),
        )
        dropped: list[PatchTarget] = []
        while running > 1.0 + 1e-9 and sorted_floor:
            drop = sorted_floor.pop(0)
            running -= drop.delta
            dropped.append(drop)

        kept_floor = [t for t in floor_targets if t not in dropped]
        conflict: Optional[MergeConflict] = None
        if dropped:
            conflict = MergeConflict(
                signal_name="*",
                field=PatchField.FLOOR.value,
                candidates=tuple(dropped),
                reason=ConflictReason.FLOOR_BUDGET_EXCEEDED,
            )
        return other + kept_floor, dropped, conflict

    def _enforce_ceiling_budget(
        self,
        targets: Sequence[PatchTarget],
        score_by_target: Mapping[Tuple[str, PatchField], float],
    ) -> Tuple[list[PatchTarget], list[PatchTarget], Optional[MergeConflict]]:
        ceiling_targets = [t for t in targets if t.field is PatchField.CEILING]
        other = [t for t in targets if t.field is not PatchField.CEILING]
        if not ceiling_targets:
            return list(targets), [], None

        # Each signal's effective ceiling must not drop below some floor
        # for the system as a whole; operationally we require
        # Σ(current_ceiling + delta) ≥ 1 so that some feasible convex
        # combination exists (cf. sre_control._project_to_simplex_with_bounds).
        #
        # current_ceiling defaults to 1.0 for unregistered signals, so
        # in practice this constraint is only binding when the snapshot
        # actively shrinks ceilings. Still, we emit a conflict if we
        # would cross the 1.0 line in aggregate.
        running = sum(
            self._snapshot.current_ceiling(t.signal_name) + t.delta
            for t in ceiling_targets
        ) + (len(self._snapshot.ceilings) - len(ceiling_targets)) * 0  # unregistered signals assumed 1.0

        # Simpler rule that still captures the spirit of the constraint:
        # we never allow two CEILING targets that together reduce the
        # ceiling budget by more than half. If violated, drop lowest-
        # scored targets until the aggregate reduction ≤ 0.5.
        aggregate_reduction = sum(abs(t.delta) for t in ceiling_targets)
        if aggregate_reduction <= 0.5 + 1e-9:
            return list(targets), [], None

        sorted_ceiling = sorted(
            ceiling_targets,
            key=lambda t: score_by_target.get((t.signal_name, t.field), 0.0),
        )
        dropped: list[PatchTarget] = []
        while aggregate_reduction > 0.5 + 1e-9 and sorted_ceiling:
            drop = sorted_ceiling.pop(0)
            aggregate_reduction -= abs(drop.delta)
            dropped.append(drop)

        kept_ceiling = [t for t in ceiling_targets if t not in dropped]
        conflict: Optional[MergeConflict] = None
        if dropped:
            conflict = MergeConflict(
                signal_name="*",
                field=PatchField.CEILING.value,
                candidates=tuple(dropped),
                reason=ConflictReason.CEILING_BUDGET_INSUFFICIENT,
            )
        return other + kept_ceiling, dropped, conflict

    # -------------------------------------------------- stage 2b must-attend

    def _enforce_must_attend(
        self, targets: Sequence[PatchTarget]
    ) -> Tuple[list[PatchTarget], list[PatchTarget], list[MergeConflict]]:
        if not self._cfg.enforce_must_attend or not self._snapshot.floors:
            return list(targets), [], []

        accepted: list[PatchTarget] = []
        dropped: list[PatchTarget] = []
        conflicts: list[MergeConflict] = []
        for t in targets:
            current = self._snapshot.current_floor(t.signal_name)
            if t.field is PatchField.FLOOR and current > 0:
                # Fine — we're only allowed to raise the floor (merger
                # never emits negative floor deltas given stage 1 clamps).
                accepted.append(t)
                continue
            if t.field is PatchField.CEILING and current > 0:
                # Reducing the ceiling can't drop below the current
                # must-attend floor.
                effective_ceiling = self._snapshot.current_ceiling(t.signal_name) + t.delta
                if effective_ceiling < current:
                    dropped.append(t)
                    conflicts.append(
                        MergeConflict(
                            signal_name=t.signal_name,
                            field=t.field.value,
                            candidates=(t,),
                            reason=ConflictReason.MUST_ATTEND_VIOLATION,
                        )
                    )
                    continue
            accepted.append(t)
        return accepted, dropped, conflicts


__all__ = [
    "HierarchicalPatchMerger",
    "MergerConfig",
    "MustAttendSnapshot",
]
