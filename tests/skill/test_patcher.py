"""Tests for :class:`SkillPatcher` (PR-006)."""

from __future__ import annotations

import pytest

from attention_residuals.skill.trajectory.merger import MustAttendSnapshot
from attention_residuals.skill.types import (
    MergedSkillPatch,
    PatchField,
    PatchTarget,
    VerifierFinding,
    compute_patch_id,
)
from attention_residuals.skill.verify.patcher import (
    PatcherConfig,
    SkillPatcher,
)


def _mk_base(targets: tuple[PatchTarget, ...] = (), provenance: tuple[str, ...] = ("p1",)) -> MergedSkillPatch:
    if not targets:
        targets = (
            PatchTarget("error_budget", PatchField.FLOOR, 0.10, "tighten"),
            PatchTarget("cost", PatchField.CEILING, -0.10, "cap cost"),
        )
    return MergedSkillPatch(
        patch_id=compute_patch_id(targets, {}),
        targets=targets,
        provenance=provenance,
        registry_hash="reg-v1",
    )


def _mk_finding(signals=("error_budget",), direction=None, severity=0.5) -> VerifierFinding:
    direction = dict(direction or {"error_budget": -1})
    return VerifierFinding(
        finding_id="f-1",
        offending_signals=tuple(signals),
        suggested_direction=direction,
        severity=severity,
        diagnostics={"divergence": 0.3},
    )


# -----------------------------------------------------------------------------
# REQ-KNE-004 · bound per round
# -----------------------------------------------------------------------------


def test_req_kne_004_variants_bounded() -> None:
    patcher = SkillPatcher(PatcherConfig(max_variants_per_round=2))
    base = _mk_base()
    findings = [
        _mk_finding(("error_budget",), {"error_budget": -1}),
        _mk_finding(("cost",), {"cost": +1}),
        _mk_finding(("error_budget",), {"error_budget": +1}),
    ]
    variants = patcher.propose(base, findings)
    assert len(variants) <= 2


# -----------------------------------------------------------------------------
# REQ-KNE-005 · per-step delta capped
# -----------------------------------------------------------------------------


def test_req_kne_005_step_cap_respected() -> None:
    patcher = SkillPatcher(
        PatcherConfig(
            max_variants_per_round=5,
            max_delta_per_step=0.05,
            respect_conservative=False,  # allow movement in both directions
        )
    )
    base = _mk_base()
    # Direction -1 on error_budget; previous delta was 0.10 → new = 0.05.
    finding = _mk_finding(("error_budget",), {"error_budget": -1})
    variants = patcher.propose(base, [finding])
    assert variants
    new_target = next(
        t for t in variants[0].targets
        if t.signal_name == "error_budget" and t.field is PatchField.FLOOR
    )
    assert abs(new_target.delta - 0.05) < 1e-6


# -----------------------------------------------------------------------------
# REQ-KNE-006 · guard DEFER/DENY → empty
# -----------------------------------------------------------------------------


class _DeferGuard:
    def __init__(self, decision: str):
        self._decision = decision

    def admit(self, patch_id: str) -> str:
        return self._decision


def test_req_kne_006_defer_produces_no_variants() -> None:
    patcher = SkillPatcher(guard=_DeferGuard("defer"))
    variants = patcher.propose(_mk_base(), [_mk_finding()])
    assert variants == []


def test_deny_also_produces_no_variants() -> None:
    patcher = SkillPatcher(guard=_DeferGuard("deny"))
    variants = patcher.propose(_mk_base(), [_mk_finding()])
    assert variants == []


def test_allow_lets_patcher_run() -> None:
    patcher = SkillPatcher(guard=_DeferGuard("allow"))
    # direction=+1 on FLOOR is conservative-safe (floor increases only).
    variants = patcher.propose(
        _mk_base(), [_mk_finding(("error_budget",), {"error_budget": +1})]
    )
    assert variants   # non-empty


# -----------------------------------------------------------------------------
# REQ-KNE-012 · derived_from non-null
# -----------------------------------------------------------------------------


def test_derived_from_points_at_finding() -> None:
    patcher = SkillPatcher()
    base = _mk_base()
    finding = _mk_finding(("error_budget",), {"error_budget": +1})
    variants = patcher.propose(base, [finding])
    assert all(v.derived_from == finding.finding_id for v in variants)


# -----------------------------------------------------------------------------
# Conservative guardrails (R1, R2) — default respect_conservative=True
# -----------------------------------------------------------------------------


def test_conservative_blocks_floor_decrease() -> None:
    patcher = SkillPatcher(PatcherConfig())  # respect_conservative=True
    base = _mk_base()
    finding = _mk_finding(("error_budget",), {"error_budget": -1})
    variants = patcher.propose(base, [finding])
    # The only target touching error_budget is FLOOR; conservative forbids it.
    assert variants == []


def test_conservative_blocks_ceiling_increase() -> None:
    patcher = SkillPatcher(PatcherConfig())
    base = _mk_base()
    finding = _mk_finding(("cost",), {"cost": +1})
    variants = patcher.propose(base, [finding])
    # cost target is CEILING; +1 direction would loosen → blocked.
    assert variants == []


# -----------------------------------------------------------------------------
# MustAttend feasibility
# -----------------------------------------------------------------------------


def test_must_attend_budget_blocks_over_floor_bump() -> None:
    snapshot = MustAttendSnapshot(
        floors={"error_budget": 0.95},           # only 0.05 headroom
        registry_hash="reg-v1",
    )
    patcher = SkillPatcher(PatcherConfig(max_delta_per_step=0.1))
    base = _mk_base()
    finding = _mk_finding(("error_budget",), {"error_budget": +1})  # want floor++
    variants = patcher.propose(base, [finding], snapshot=snapshot)
    # +0.1 would push Σfloor to 1.05 → patcher drops the variant.
    assert variants == []


# -----------------------------------------------------------------------------
# Idempotence — repeated calls don't spam
# -----------------------------------------------------------------------------


def test_variants_deduplicate_across_rounds() -> None:
    patcher = SkillPatcher(PatcherConfig(max_delta_per_step=0.05))
    base = _mk_base()
    finding = _mk_finding(("error_budget",), {"error_budget": +1})
    first = patcher.propose(base, [finding])
    second = patcher.propose(base, [finding])
    assert first  # got some on first round
    assert second == []   # seen_ids makes second round empty
