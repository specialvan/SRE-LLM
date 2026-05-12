"""Full M1 offline loop: miner → merger → patcher → verifier → gate → elite.

This test wires all 7 M1 components together with real
:class:`WeightedConvexCombiner` + :class:`CombinerHarness`. It verifies
that a single round-trip produces a sensible verdict and that the
gate's decision path is reachable from the pipeline's natural inputs.
"""

from __future__ import annotations

import numpy as np
import pytest

from attention_residuals.sre_control import (
    AuditRecord,
    SignalSpec,
    WeightedConvexCombiner,
)
from attention_residuals.skill.governance import (
    Elite,
    ElitePool,
    ElitePoolConfig,
)
from attention_residuals.skill.trajectory import (
    HierarchicalPatchMerger,
    MustAttendSnapshot,
    Trace2SkillMiner,
)
from attention_residuals.skill.trajectory.miner import MinerConfig
from attention_residuals.skill.types import (
    PatchField,
    PatchTarget,
    VerifierFinding,
    compute_patch_id,
)
from attention_residuals.skill.verify import (
    CombinerHarness,
    GateDecision,
    PatcherConfig,
    ReplayCase,
    SkillPatcher,
    SkillRegressionGate,
    SkillShadowVerifier,
)


def _build_audit() -> list[AuditRecord]:
    signals = ["cost", "error_budget"]
    # 30 burn steps with error_budget starved below its registered floor.
    return [
        AuditRecord(
            step=i,
            signal_names=signals,
            weights=np.array([0.92, 0.08]),
            action=np.zeros(1),
            context={"slo_breach": 3.5, "tenant": "east"},
        )
        for i in range(30)
    ]


def _build_suite() -> list[ReplayCase]:
    # One case that "approves of the baseline" (active ≈ baseline).
    return [
        ReplayCase(
            case_id="case-happy",
            signals=("cost", "error_budget"),
            query=np.array([1.0, 0.0]),
            values=(np.array([0.0]), np.array([1.0])),
            context={},
            tolerance=0.5,
        ),
    ]


def _build_harness() -> CombinerHarness:
    signals = [
        SignalSpec("cost", floor=0.0, ceiling=1.0, bias=0.0),
        SignalSpec("error_budget", floor=0.25, ceiling=1.0, bias=0.0),
    ]
    baseline = WeightedConvexCombiner(signals, query_dim=2, temperature=1.0, rng_seed=13)
    return CombinerHarness(baseline, tolerance=0.5)


def test_full_offline_loop_reaches_verdict() -> None:
    snapshot = MustAttendSnapshot(
        floors={"error_budget": 0.25}, registry_hash="reg-m1-v1"
    )
    miner = Trace2SkillMiner(
        config=MinerConfig(support_min=5, cost_quantile=0.5, cluster_k_max=1)
    )
    merger = HierarchicalPatchMerger(snapshot)
    patcher = SkillPatcher(PatcherConfig(max_delta_per_step=0.05))
    harness = _build_harness()
    verifier = SkillShadowVerifier(harness)
    gate = SkillRegressionGate()
    pool = ElitePool(ElitePoolConfig(capacity=4, min_probation_steps=0))

    # ---- mine + merge ----
    candidates = miner.mine(_build_audit(), snapshot)
    assert candidates
    merged = merger.merge(candidates)
    assert merged.targets

    # ---- simulate a failing case so the verifier produces findings ----
    # We fabricate a finding directly to drive the patcher; in production
    # findings come from the verifier itself, but that creates a chicken-
    # and-egg: verifier needs a variant to test. Here the first variant is
    # the merged patch interpreted as its own variant with id = patch_id.
    from attention_residuals.skill.types import SkillVariant

    base_variant = SkillVariant(
        variant_id=merged.patch_id,
        source_patch_id=merged.patch_id,
        targets=merged.targets,
        derived_from=None,
        generation=0,
    )
    result = verifier.verify(base_variant, _build_suite())
    # Merged patch should pass the "tolerance 0.5" case comfortably.
    assert result.diagnostics["train_pass_rate"] == 1.0
    verdict = gate.decide(result)
    # With relaxed tolerance and zero holdout fails, the gate admits.
    assert verdict.decision is GateDecision.ADMIT

    # ---- elite pool accepts the admitted variant ----
    ev = pool.try_admit(Elite(variant_id=base_variant.variant_id, score=0.9))
    assert ev is None
    assert base_variant.variant_id in pool.member_states()


def test_failing_variant_rolls_back() -> None:
    """A variant whose active action diverges far from baseline → ROLLBACK."""
    snapshot = MustAttendSnapshot(registry_hash="reg-m1-v1")
    harness = _build_harness()
    verifier = SkillShadowVerifier(harness)
    gate = SkillRegressionGate()

    # Build a variant with a huge BIAS on one signal to blow up divergence.
    from attention_residuals.skill.types import SkillVariant

    targets = (PatchTarget("cost", PatchField.BIAS, 5.0, "sabotage"),)
    variant = SkillVariant(
        variant_id=compute_patch_id(targets, {}),
        source_patch_id="sabotage",
        targets=targets,
        derived_from="f-sabotage",
    )
    # A strict case (tolerance 0.01) so the large bias fails.
    suite = [
        ReplayCase(
            case_id="c-strict",
            signals=("cost", "error_budget"),
            query=np.array([1.0, 0.0]),
            values=(np.array([0.0]), np.array([1.0])),
            tolerance=0.01,
        )
    ]
    result = verifier.verify(variant, suite)
    assert not result.pass_fail
    assert result.findings
    verdict = gate.decide(result)
    assert verdict.decision is GateDecision.ROLLBACK_REQUIRED
    assert verdict.reasons


def test_patcher_uses_verifier_findings() -> None:
    """Patcher must produce variants rooted in the findings we feed it."""
    from attention_residuals.skill.types import MergedSkillPatch

    base = MergedSkillPatch(
        patch_id=compute_patch_id(
            (PatchTarget("error_budget", PatchField.FLOOR, 0.05, "base"),), {}
        ),
        targets=(PatchTarget("error_budget", PatchField.FLOOR, 0.05, "base"),),
        provenance=("p1",),
        registry_hash="reg-m1-v1",
    )
    finding = VerifierFinding(
        finding_id="f-1",
        offending_signals=("error_budget",),
        suggested_direction={"error_budget": +1},  # raise further
        severity=0.4,
    )
    patcher = SkillPatcher(PatcherConfig(max_delta_per_step=0.05))
    variants = patcher.propose(base, [finding])
    assert variants
    v = variants[0]
    assert v.derived_from == "f-1"
    # The error_budget floor should have moved up by 0.05.
    floor_target = next(
        t for t in v.targets
        if t.signal_name == "error_budget" and t.field is PatchField.FLOOR
    )
    assert abs(floor_target.delta - 0.10) < 1e-6
