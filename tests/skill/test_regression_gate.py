"""Tests for :class:`SkillRegressionGate` (PR-008)."""

from __future__ import annotations

import numpy as np
import pytest

from attention_residuals.skill.verify.regression_gate import (
    GateConfig,
    GateDecision,
    SkillRegressionGate,
)
from attention_residuals.skill.verify.shadow_verifier import (
    CaseResult,
    ReplayCase,
    VerifyResult,
)


def _mk_result(
    train_pass: float = 1.0,
    holdout_pass: float = 1.0,
    avg_div: float = 0.0,
    max_div: float | None = None,
    pass_fail: bool = True,
) -> VerifyResult:
    return VerifyResult(
        variant_id="v1",
        pass_fail=pass_fail,
        findings=(),
        new_tests=(),
        diagnostics={
            "train_pass_rate": train_pass,
            "holdout_pass_rate": holdout_pass,
            "avg_divergence": avg_div,
            "max_divergence": max_div if max_div is not None else avg_div,
        },
        case_results=(),
    )


# -----------------------------------------------------------------------------
# Rule 1 · core 0-regression (REQ-VRF-003, REQ-VRF-004)
# -----------------------------------------------------------------------------


def test_req_vrf_003_admit_happy_path() -> None:
    gate = SkillRegressionGate()
    v = gate.decide(_mk_result(1.0, 1.0, 0.05))
    assert v.decision is GateDecision.ADMIT
    assert v.reasons  # never empty


def test_req_vrf_004_core_regression_rollback() -> None:
    gate = SkillRegressionGate()
    v = gate.decide(_mk_result(train_pass=0.95))
    assert v.decision is GateDecision.ROLLBACK_REQUIRED


def test_divergence_ceiling_rollback() -> None:
    gate = SkillRegressionGate()
    v = gate.decide(_mk_result(avg_div=0.05, max_div=0.4))
    assert v.decision is GateDecision.ROLLBACK_REQUIRED
    assert any("divergence" in r for r in v.reasons)


# -----------------------------------------------------------------------------
# Rule 3 · holdout miss
# -----------------------------------------------------------------------------


def test_holdout_miss_quarantine_by_default() -> None:
    gate = SkillRegressionGate()
    v = gate.decide(_mk_result(1.0, holdout_pass=0.7))
    assert v.decision is GateDecision.QUARANTINE


def test_holdout_miss_hard_rollback_when_configured() -> None:
    gate = SkillRegressionGate(
        GateConfig(quarantine_on_holdout_miss=False)
    )
    v = gate.decide(_mk_result(1.0, holdout_pass=0.7))
    assert v.decision is GateDecision.ROLLBACK_REQUIRED


# -----------------------------------------------------------------------------
# Suite management (REQ-VRF-010)
# -----------------------------------------------------------------------------


def _mk_case(case_id: str) -> ReplayCase:
    return ReplayCase(
        case_id=case_id,
        signals=("a",),
        query=np.array([1.0]),
        values=(np.array([0.0]),),
    )


def test_promote_new_tests_dedupes() -> None:
    gate = SkillRegressionGate()
    added1 = gate.promote_new_tests([_mk_case("t1"), _mk_case("t2")])
    added2 = gate.promote_new_tests([_mk_case("t1"), _mk_case("t3")])
    assert added1 == 2
    assert added2 == 1
    assert gate.holdout_size() == 3
    assert gate.core_size() == 0           # core is untouched


def test_core_vs_holdout_isolation() -> None:
    gate = SkillRegressionGate()
    gate.add_core_case(_mk_case("core1"))
    gate.add_holdout_case(_mk_case("hold1"))
    assert gate.core_size() == 1
    assert gate.holdout_size() == 1


# -----------------------------------------------------------------------------
# Reasons always non-empty
# -----------------------------------------------------------------------------


def test_req_vrf_011_reasons_always_present() -> None:
    gate = SkillRegressionGate()
    for result in [
        _mk_result(1.0, 1.0, 0.05),
        _mk_result(train_pass=0.8),
        _mk_result(avg_div=0.4, max_div=0.4),
        _mk_result(1.0, holdout_pass=0.5),
    ]:
        v = gate.decide(result)
        assert v.reasons
