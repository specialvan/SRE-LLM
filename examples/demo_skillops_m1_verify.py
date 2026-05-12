"""M1 · Verify + Gate + ElitePool demo.

Extends ``demo_skillops_m1.py`` with the verify/gate triad (PR-006/007/008).
Pipeline:

    audit → miner → merger
            └──▶ base variant
                    └──▶ verifier (shadow) ──▶ gate ──▶ admit/rollback
                                                     └──▶ elite pool

Three scenarios are executed:

1. **happy path**: merged variant passes a tolerant suite → ``ADMIT``
2. **sabotaged variant**: large bias → divergence blows past ceiling → ``ROLLBACK``
3. **patcher proposal**: finding from scenario 2 drives a refinement round

Run::

    python -m examples.demo_skillops_m1_verify
"""

from __future__ import annotations

import numpy as np

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
    MergedSkillPatch,
    PatchField,
    PatchTarget,
    SkillVariant,
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


def _build_audit(n: int = 30) -> list[AuditRecord]:
    signals = ["cost", "error_budget"]
    return [
        AuditRecord(
            step=i,
            signal_names=signals,
            weights=np.array([0.92, 0.08]),
            action=np.zeros(1),
            context={"slo_breach": 3.5},
        )
        for i in range(n)
    ]


def _build_harness() -> CombinerHarness:
    signals = [
        SignalSpec("cost", floor=0.0, ceiling=1.0, bias=0.0),
        SignalSpec("error_budget", floor=0.25, ceiling=1.0, bias=0.0),
    ]
    baseline = WeightedConvexCombiner(signals, query_dim=2, temperature=1.0, rng_seed=13)
    return CombinerHarness(baseline, tolerance=0.3)


def _base_suite() -> list[ReplayCase]:
    return [
        ReplayCase(
            case_id="balanced",
            signals=("cost", "error_budget"),
            query=np.array([1.0, 0.0]),
            values=(np.array([0.0]), np.array([1.0])),
            tolerance=0.3,
        ),
        ReplayCase(
            case_id="cost-heavy",
            signals=("cost", "error_budget"),
            query=np.array([0.0, 1.0]),
            values=(np.array([2.0]), np.array([-1.0])),
            tolerance=0.4,
        ),
    ]


def _print_verdict(scenario: str, variant_id: str, result, verdict) -> None:
    print(
        f"[{scenario}] variant={variant_id[:8]} "
        f"pass={result.pass_fail} "
        f"core={result.diagnostics['train_pass_rate']:.0%} "
        f"max_div={result.diagnostics['max_divergence']:.3f} "
        f"→ {verdict.decision.value}"
    )
    for reason in verdict.reasons:
        print(f"    reason: {reason}")


def main() -> None:
    snapshot = MustAttendSnapshot(
        floors={"error_budget": 0.25}, registry_hash="reg-m1-v1"
    )

    # 1) mine + merge
    records = _build_audit()
    miner = Trace2SkillMiner(
        MinerConfig(support_min=5, cost_quantile=0.5, cluster_k_max=1)
    )
    merger = HierarchicalPatchMerger(snapshot)
    candidates = miner.mine(records, snapshot)
    merged = merger.merge(candidates)
    print(
        f"[mine+merge] {len(candidates)} candidate(s) → "
        f"{len(merged.targets)} merged target(s)"
    )

    harness = _build_harness()
    verifier = SkillShadowVerifier(harness)
    gate = SkillRegressionGate()
    pool = ElitePool(ElitePoolConfig(capacity=4, min_probation_steps=0))
    patcher = SkillPatcher(PatcherConfig(max_delta_per_step=0.05))

    # ---- scenario 1: happy path (merged patch as its own variant) ----
    base_variant = SkillVariant(
        variant_id=merged.patch_id,
        source_patch_id=merged.patch_id,
        targets=merged.targets,
        derived_from=None,
    )
    result1 = verifier.verify(base_variant, _base_suite())
    verdict1 = gate.decide(result1)
    _print_verdict("happy", base_variant.variant_id, result1, verdict1)
    if verdict1.decision is GateDecision.ADMIT:
        ev = pool.try_admit(Elite(base_variant.variant_id, score=0.9))
        print(
            f"[happy] elite pool → size={len(pool)}, "
            f"event={'evict' if ev else 'admit-fresh'}"
        )

    # ---- scenario 2: sabotaged variant ----
    sabotage_targets = (PatchTarget("cost", PatchField.BIAS, 5.0, "sabotage demo"),)
    sabotage = SkillVariant(
        variant_id=compute_patch_id(sabotage_targets, {}),
        source_patch_id="sabotage",
        targets=sabotage_targets,
        derived_from="demo-fail",
    )
    strict_suite = [
        ReplayCase(
            case_id="strict",
            signals=("cost", "error_budget"),
            query=np.array([1.0, 0.0]),
            values=(np.array([0.0]), np.array([1.0])),
            tolerance=0.01,
        )
    ]
    result2 = verifier.verify(sabotage, strict_suite)
    verdict2 = gate.decide(result2)
    _print_verdict("sabotage", sabotage.variant_id, result2, verdict2)
    if verdict2.decision is GateDecision.ROLLBACK_REQUIRED:
        print(
            f"[sabotage] findings={len(result2.findings)} "
            f"offending={[f.offending_signals for f in result2.findings]}"
        )

    # ---- scenario 3: patcher consumes finding ----
    if result2.findings:
        proposals = patcher.propose(
            MergedSkillPatch(
                patch_id=merged.patch_id,
                targets=merged.targets,
                provenance=merged.provenance,
                registry_hash=merged.registry_hash,
            ),
            list(result2.findings),
            snapshot=snapshot,
        )
        print(f"[patcher] {len(proposals)} proposal(s) derived from failure")
        for p in proposals:
            directions = ",".join(f"{t.signal_name}.{t.field.value}:{t.delta:+.3f}" for t in p.targets)
            print(f"    variant {p.variant_id[:8]} · {directions}")

    # Final gate / pool snapshot
    pool.evict_probation_breakers(step=1)
    print(
        f"[final] pool size={len(pool)} elite={pool.elite_ids()} "
        f"gate core={gate.core_size()} holdout={gate.holdout_size()}"
    )


if __name__ == "__main__":
    main()
