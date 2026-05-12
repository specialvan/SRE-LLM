"""Tests for :class:`HierarchicalPatchMerger` (PR-002)."""

from __future__ import annotations

import pytest

from attention_residuals.skill.trajectory.merger import (
    HierarchicalPatchMerger,
    MergerConfig,
    MustAttendSnapshot,
)
from attention_residuals.skill.types import (
    ConflictReason,
    PatchField,
    PatchTarget,
    SkillPatchCandidate,
    compute_patch_id,
)


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _mk_candidate(
    targets: tuple[PatchTarget, ...],
    support: int = 10,
    score: float = 5.0,
    registry_hash: str = "reg-v1",
    trigger: dict[str, float] | None = None,
) -> SkillPatchCandidate:
    trigger = trigger or {}
    return SkillPatchCandidate(
        patch_id=compute_patch_id(targets, trigger),
        trigger=trigger,
        targets=targets,
        evidence_steps=tuple(range(support)),
        support=support,
        avg_cost_before=0.5,
        score=score,
        registry_hash=registry_hash,
    )


# -----------------------------------------------------------------------------
# Intra-signal merge (REQ-KNE-001)
# -----------------------------------------------------------------------------


def test_req_kne_001_same_direction_support_weighted() -> None:
    merger = HierarchicalPatchMerger(MustAttendSnapshot(registry_hash="reg-v1"))
    c1 = _mk_candidate(
        (PatchTarget("s", PatchField.BIAS, 0.10),),
        support=10,
    )
    c2 = _mk_candidate(
        (PatchTarget("s", PatchField.BIAS, 0.20),),
        support=30,
    )
    out = merger.merge([c1, c2])
    assert len(out.targets) == 1
    # (10·0.10 + 30·0.20) / 40 = 0.175
    assert abs(out.targets[0].delta - 0.175) < 1e-6


def test_balanced_opposite_deltas_retreat_to_zero() -> None:
    merger = HierarchicalPatchMerger(MustAttendSnapshot(registry_hash="reg-v1"))
    c_plus = _mk_candidate(
        (PatchTarget("s", PatchField.BIAS, 0.10),),
        support=10,
    )
    c_minus = _mk_candidate(
        (PatchTarget("s", PatchField.BIAS, -0.10),),
        support=10,
    )
    out = merger.merge([c_plus, c_minus])
    assert out.targets == ()
    # Balanced retreat means no target *and* no MergeConflict — spec says
    # we silently drop when they retreat.


# -----------------------------------------------------------------------------
# Cross-signal budgets (REQ-KNE-002 / REQ-KNE-003)
# -----------------------------------------------------------------------------


def test_req_kne_002_floor_budget_enforced() -> None:
    # snapshot already uses 0.7 of the floor budget.
    snapshot = MustAttendSnapshot(
        floors={"alpha": 0.4, "beta": 0.3},
        registry_hash="reg-v1",
    )
    merger = HierarchicalPatchMerger(snapshot)
    # Each candidate wants +0.2 floor on a distinct signal; combined
    # they'd push Σfloor to 0.4+0.3+0.2+0.2 = 1.1 > 1.
    c_weak = _mk_candidate(
        (PatchTarget("gamma", PatchField.FLOOR, 0.2),),
        support=5,
        score=1.0,
    )
    c_strong = _mk_candidate(
        (PatchTarget("delta", PatchField.FLOOR, 0.2),),
        support=50,
        score=50.0,
    )
    out = merger.merge([c_weak, c_strong])
    names = {t.signal_name for t in out.targets}
    dropped_names = {t.signal_name for t in out.dropped}
    # Low-score candidate drops first; high-score stays.
    assert "delta" in names
    assert "gamma" in dropped_names
    assert len(out.conflicts) == 1
    assert out.conflicts[0].reason is ConflictReason.FLOOR_BUDGET_EXCEEDED


def test_must_attend_violation_drops_target() -> None:
    snapshot = MustAttendSnapshot(
        floors={"safety": 0.4},
        ceilings={"safety": 0.6},
        registry_hash="reg-v1",
    )
    merger = HierarchicalPatchMerger(snapshot)
    # Reduce ceiling for safety below its registered floor → violation.
    c = _mk_candidate(
        (PatchTarget("safety", PatchField.CEILING, -0.3),),
    )
    out = merger.merge([c])
    assert out.targets == ()
    assert out.dropped and out.dropped[0].signal_name == "safety"
    assert any(
        conflict.reason is ConflictReason.MUST_ATTEND_VIOLATION
        for conflict in out.conflicts
    )


# -----------------------------------------------------------------------------
# Registry drift
# -----------------------------------------------------------------------------


def test_registry_drift_is_reported_and_drops_all() -> None:
    snapshot = MustAttendSnapshot(registry_hash="reg-v1")
    merger = HierarchicalPatchMerger(snapshot)
    c1 = _mk_candidate(
        (PatchTarget("a", PatchField.BIAS, 0.1),),
        registry_hash="reg-v1",
    )
    c2 = _mk_candidate(
        (PatchTarget("b", PatchField.BIAS, 0.2),),
        registry_hash="reg-v2",
    )
    out = merger.merge([c1, c2])
    assert out.targets == ()
    assert any(c.reason is ConflictReason.REGISTRY_DRIFT for c in out.conflicts)
    assert {t.signal_name for t in out.dropped} == {"a", "b"}


# -----------------------------------------------------------------------------
# Empty input & provenance
# -----------------------------------------------------------------------------


def test_empty_input_returns_empty_patch() -> None:
    merger = HierarchicalPatchMerger(MustAttendSnapshot(registry_hash="reg-v1"))
    out = merger.merge([])
    assert out.targets == () and out.dropped == () and out.conflicts == ()


def test_provenance_non_empty(tmp_path) -> None:
    merger = HierarchicalPatchMerger(MustAttendSnapshot(registry_hash="reg-v1"))
    c = _mk_candidate((PatchTarget("a", PatchField.BIAS, 0.1),))
    out = merger.merge([c])
    assert out.provenance == (c.patch_id,)


# -----------------------------------------------------------------------------
# Property: no silent drops (REQ-DAT-011 spirit)
# -----------------------------------------------------------------------------


def test_no_silent_budget_drop() -> None:
    """If a target is dropped by the budget stage, it must appear in either
    `dropped` or `conflicts`; never both lost."""
    snapshot = MustAttendSnapshot(
        floors={"x": 0.5, "y": 0.45},
        registry_hash="reg-v1",
    )
    merger = HierarchicalPatchMerger(snapshot)
    # Σfloor would be 0.95 + 0.1 = 1.05 → the +0.1 target is dropped.
    c = _mk_candidate(
        (PatchTarget("z", PatchField.FLOOR, 0.1),),
        support=2,
        score=1.0,
    )
    out = merger.merge([c])
    assert any(t.signal_name == "z" for t in out.dropped)
    assert any(
        conflict.reason is ConflictReason.FLOOR_BUDGET_EXCEEDED
        for conflict in out.conflicts
    )
