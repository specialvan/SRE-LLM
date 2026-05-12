"""Tests for :class:`SkillShadowVerifier` (PR-007) and :class:`CombinerHarness`."""

from __future__ import annotations

from typing import Mapping, Optional, Sequence, Tuple

import numpy as np
import pytest

from attention_residuals.sre_control import SignalSpec, WeightedConvexCombiner
from attention_residuals.skill.verify.shadow_verifier import (
    CaseResult,
    CombinerHarness,
    ReplayCase,
    SkillShadowVerifier,
    VerificationHarness,
    VerifierConfig,
)
from attention_residuals.skill.types import (
    PatchField,
    PatchTarget,
    SkillVariant,
    compute_patch_id,
)


# -----------------------------------------------------------------------------
# A tiny stub harness that we can steer from each test
# -----------------------------------------------------------------------------


class _StubHarness:
    """Harness returning deterministic, caller-controlled :class:`CaseResult`."""

    def __init__(
        self,
        outcomes: Mapping[str, bool],
        divergences: Optional[Mapping[str, float]] = None,
        counterfactuals_by_case: Optional[Mapping[str, Sequence[Tuple[int, np.ndarray]]]] = None,
    ) -> None:
        self._outcomes = dict(outcomes)
        self._divergences = dict(divergences or {})
        self._cf = dict(counterfactuals_by_case or {})

    def evaluate(self, case: ReplayCase, variant: SkillVariant) -> CaseResult:
        passed = self._outcomes.get(case.case_id, True)
        divergence = self._divergences.get(case.case_id, 0.0 if passed else 0.3)
        zero = np.zeros(case.values[0].shape if case.values else (1,))
        return CaseResult(
            case_id=case.case_id,
            baseline_action=zero,
            active_action=zero + (0.0 if passed else 0.3),
            baseline_weights=np.zeros(len(case.signals)),
            active_weights=np.zeros(len(case.signals)),
            divergence=divergence,
            passed=passed,
            context=case.context,
        )

    def counterfactuals(
        self,
        case: ReplayCase,
        variant: SkillVariant,
    ) -> Optional[Sequence[Tuple[int, np.ndarray]]]:
        return self._cf.get(case.case_id)


def _mk_case(case_id: str, signals: Tuple[str, ...] = ("a", "b")) -> ReplayCase:
    return ReplayCase(
        case_id=case_id,
        signals=signals,
        query=np.array([1.0, 0.0]),
        values=(np.array([1.0]), np.array([-1.0])),
        context={"tenant": "east"},
    )


def _mk_variant(targets: Tuple[PatchTarget, ...] = ()) -> SkillVariant:
    if not targets:
        targets = (PatchTarget("a", PatchField.BIAS, 0.1, "up"),)
    return SkillVariant(
        variant_id=compute_patch_id(targets, {}),
        source_patch_id="src",
        targets=targets,
        derived_from="find-1",
        generation=0,
    )


# -----------------------------------------------------------------------------
# REQ-VRF-001 : pass ⇔ every case passes
# -----------------------------------------------------------------------------


def test_req_vrf_001_all_pass_means_pass_fail_true() -> None:
    harness = _StubHarness(outcomes={"c1": True, "c2": True})
    verifier = SkillShadowVerifier(harness)
    result = verifier.verify(
        _mk_variant(), [_mk_case("c1"), _mk_case("c2")]
    )
    assert result.pass_fail is True
    assert result.findings == ()
    assert result.diagnostics["train_pass_rate"] == 1.0


def test_req_vrf_001_single_fail_means_pass_fail_false() -> None:
    harness = _StubHarness(outcomes={"c1": True, "c2": False})
    verifier = SkillShadowVerifier(harness)
    result = verifier.verify(
        _mk_variant(), [_mk_case("c1"), _mk_case("c2")]
    )
    assert result.pass_fail is False
    assert result.diagnostics["train_pass_rate"] == 0.5


# -----------------------------------------------------------------------------
# REQ-VRF-002 : findings non-empty on fail
# -----------------------------------------------------------------------------


def test_req_vrf_002_findings_non_empty_on_fail() -> None:
    harness = _StubHarness(outcomes={"c1": False})
    verifier = SkillShadowVerifier(harness)
    result = verifier.verify(_mk_variant(), [_mk_case("c1")])
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.offending_signals
    assert finding.severity > 0


def test_counterfactual_narrows_offending_signal() -> None:
    # CF for signal 1 produces an action close to baseline → blame signal 1 only.
    baseline_like = np.array([0.0])
    cf = {"c1": [(0, np.array([0.3])), (1, baseline_like)]}  # signal 1 explains
    harness = _StubHarness(
        outcomes={"c1": False},
        divergences={"c1": 0.3},
        counterfactuals_by_case=cf,
    )
    verifier = SkillShadowVerifier(harness)
    result = verifier.verify(_mk_variant(), [_mk_case("c1", ("a", "b"))])
    offending = set(result.findings[0].offending_signals)
    assert "b" in offending


# -----------------------------------------------------------------------------
# REQ-VRF-009 : holdout does not feed finding generation
# -----------------------------------------------------------------------------


def test_req_vrf_009_holdout_fail_not_in_findings() -> None:
    harness = _StubHarness(outcomes={"c1": True, "h1": False})
    verifier = SkillShadowVerifier(harness)
    result = verifier.verify(
        _mk_variant(),
        [_mk_case("c1")],
        holdout=[_mk_case("h1")],
    )
    assert result.pass_fail is True           # core suite all pass
    assert result.findings == ()               # holdout failures don't emit findings
    assert result.diagnostics["holdout_pass_rate"] == 0.0


# -----------------------------------------------------------------------------
# Derived new_tests are deduplicated
# -----------------------------------------------------------------------------


def test_new_tests_deduplicate_across_runs() -> None:
    harness = _StubHarness(outcomes={"c1": False})
    verifier = SkillShadowVerifier(harness)
    r1 = verifier.verify(_mk_variant(), [_mk_case("c1")])
    r2 = verifier.verify(_mk_variant(), [_mk_case("c1")])
    assert len(r1.new_tests) == 1
    assert r2.new_tests == ()                  # same test was already derived


# -----------------------------------------------------------------------------
# CombinerHarness against a real WeightedConvexCombiner
# -----------------------------------------------------------------------------


def test_combiner_harness_builds_active_with_variant_targets() -> None:
    signals = [
        SignalSpec(name="a", floor=0.0, ceiling=1.0, bias=0.0),
        SignalSpec(name="b", floor=0.0, ceiling=1.0, bias=0.0),
    ]
    baseline = WeightedConvexCombiner(signals, query_dim=2, temperature=1.0, rng_seed=7)
    harness = CombinerHarness(baseline)
    variant = _mk_variant((PatchTarget("a", PatchField.BIAS, 0.5, "tilt"),))
    case = _mk_case("c1", ("a", "b"))
    result = harness.evaluate(case, variant)
    assert result.baseline_action.shape == (1,)
    assert result.active_action.shape == (1,)
    # active differs from baseline along the tilted direction
    assert result.divergence > 0


def test_combiner_harness_counterfactuals_not_none_when_possible() -> None:
    signals = [
        SignalSpec(name="a"),
        SignalSpec(name="b"),
    ]
    baseline = WeightedConvexCombiner(signals, query_dim=2, temperature=1.0, rng_seed=7)
    harness = CombinerHarness(baseline)
    variant = _mk_variant((PatchTarget("a", PatchField.BIAS, 0.5, "tilt"),))
    case = _mk_case("c1", ("a", "b"))
    cf = harness.counterfactuals(case, variant)
    assert cf is not None
    assert len(cf) == 2


# -----------------------------------------------------------------------------
# Harness exception is absorbed (defensive)
# -----------------------------------------------------------------------------


class _ExplodingHarness:
    def evaluate(self, case, variant):
        raise RuntimeError("boom")

    def counterfactuals(self, case, variant):
        return None


def test_exploding_harness_is_absorbed_and_marks_case_failed() -> None:
    verifier = SkillShadowVerifier(_ExplodingHarness())
    result = verifier.verify(_mk_variant(), [_mk_case("c1")])
    assert result.pass_fail is False
    assert result.case_results[0].context.get("harness_error")


# -----------------------------------------------------------------------------
# Severity threshold filter
# -----------------------------------------------------------------------------


def test_min_severity_filters_tiny_divergences() -> None:
    harness = _StubHarness(
        outcomes={"c1": False},
        divergences={"c1": 0.001},
    )
    verifier = SkillShadowVerifier(
        harness, VerifierConfig(divergence_saturation=1.0, min_severity=0.5)
    )
    result = verifier.verify(_mk_variant(), [_mk_case("c1")])
    assert result.findings == ()
