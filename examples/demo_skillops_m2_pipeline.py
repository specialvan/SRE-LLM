"""M2 · SkillOpsPipeline end-to-end demo.

One tick pushes an audit batch through every phase:

    evidence → mine → merge → propose → verify → gate → govern → route

The demo prints per-phase timings and the final routing decisions so
operators can read the whole pipeline output at a glance.

Run::

    python -m examples.demo_skillops_m2_pipeline
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np

from attention_residuals.sre_control import (
    AuditRecord,
    SignalSpec,
    WeightedConvexCombiner,
)
from attention_residuals.skill.governance import (
    ConservativeCommit,
    ElitePool,
    ElitePoolConfig,
    SkillRepository,
    SkillVersionGraph,
)
from attention_residuals.skill.policy_skill import (
    DualGranularitySkillBank,
    ExplorationBiasScheduler,
    ExploreConfig,
    HindsightConfig,
    HindsightUtilityTracker,
    RetrieverConfig,
    RouterConfig,
    SkillRouter,
    UtilityAwareRetriever,
)
from attention_residuals.skill.skillops import (
    PipelineDeps,
    SkillOpsPipeline,
)
from attention_residuals.skill.trajectory import (
    HierarchicalPatchMerger,
    MustAttendSnapshot,
    Trace2SkillMiner,
)
from attention_residuals.skill.trajectory.miner import MinerConfig
from attention_residuals.skill.verify import (
    CombinerHarness,
    GateConfig,
    PatcherConfig,
    ReplayCase,
    SkillPatcher,
    SkillRegressionGate,
    SkillShadowVerifier,
)


def _audit_batch(n: int = 30) -> list[AuditRecord]:
    signals = ["cost", "error_budget"]
    records: list[AuditRecord] = []
    for step in range(n):
        records.append(
            AuditRecord(
                step=step,
                signal_names=signals,
                weights=np.array([0.92, 0.08]),
                action=np.zeros(1),
                context={"slo_breach": 3.3},
            )
        )
    return records


def _build_pipeline(tmp: Path) -> SkillOpsPipeline:
    snapshot = MustAttendSnapshot(
        floors={"error_budget": 0.25}, registry_hash="reg-m2-demo"
    )
    baseline_signals = [
        SignalSpec("cost", floor=0.0, ceiling=1.0, bias=0.0),
        SignalSpec("error_budget", floor=0.25, ceiling=1.0, bias=0.0),
    ]
    baseline = WeightedConvexCombiner(
        baseline_signals, query_dim=2, temperature=1.0, rng_seed=19
    )
    deps = PipelineDeps(
        repository=SkillRepository(graph=SkillVersionGraph(), base_dir=tmp),
        conservative=ConservativeCommit(),
        elite=ElitePool(ElitePoolConfig(capacity=4, min_probation_steps=1)),
        miner=Trace2SkillMiner(
            MinerConfig(support_min=5, cost_quantile=0.5, cluster_k_max=1)
        ),
        merger=HierarchicalPatchMerger(snapshot),
        patcher=SkillPatcher(PatcherConfig(max_delta_per_step=0.05)),
        verifier=SkillShadowVerifier(CombinerHarness(baseline, tolerance=0.5)),
        gate=SkillRegressionGate(GateConfig(divergence_ceiling=5.0)),
        bank=DualGranularitySkillBank(),
        retriever=UtilityAwareRetriever(
            dim=4,
            config=RetrieverConfig(lambda_util=0.3, lambda_explore=0.2),
        ),
        utility=HindsightUtilityTracker(HindsightConfig(alpha_ema=0.3)),
        explore=ExplorationBiasScheduler(
            ExploreConfig(beta0=0.3, min_protection_uses=3, global_budget=5.0)
        ),
        router=SkillRouter(
            bank=DualGranularitySkillBank(),            # temp placeholder
            retriever=UtilityAwareRetriever(dim=4),
            config=RouterConfig(default_top_k=2),
        ),
        registry_snapshot=snapshot,
    )
    # Crosslink: the router must point at the same bank/retriever/utility
    # that the pipeline's govern phase populates, or routing won't see new
    # skills. This awkwardness is the v1 cost of keeping the router as a
    # pure consumer; M3 will collapse the indirection.
    deps.router = SkillRouter(
        bank=deps.bank,
        retriever=deps.retriever,
        utility=deps.utility,
        explore=deps.explore,
        config=RouterConfig(default_top_k=2),
    )
    return SkillOpsPipeline(deps)


def _suite() -> list[ReplayCase]:
    return [
        ReplayCase(
            case_id="relaxed",
            signals=("cost", "error_budget"),
            query=np.array([1.0, 0.0]),
            values=(np.array([0.0]), np.array([1.0])),
            tolerance=0.5,
        ),
    ]


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        pipeline = _build_pipeline(Path(tmp))
        report = pipeline.tick(
            step=0,
            audit_batch=_audit_batch(),
            verify_suite=_suite(),
            router_query=np.array([1.0, 0.0, 0.0, 0.0]),
        )
        print(f"[M2] tick 0 total_ms={report.total_ms:.2f}")
        for p in report.phases:
            status = "ERR " if p.errored else ("SKIP" if p.note else "ok  ")
            note = p.note or p.error or ""
            print(f"    {status} {p.name:<8} {p.elapsed_ms:6.2f}ms  {note}")

        print(
            f"[M2] summary · candidates={report.candidates_mined} "
            f"merged_targets={report.merged_targets} "
            f"variants={report.variants_proposed} "
            f"verified=(pass {report.verifier_passed} / fail {report.verifier_failed}) "
            f"gate=(admit {report.gate_admits} / quar {report.gate_quarantines} / rb {report.gate_rollbacks})"
        )
        print(
            f"[M2] elite admissions={report.elite_admissions}  "
            f"evictions={report.elite_evictions}  "
            f"route_picks={report.route_picks}"
        )

        # A second tick that purely exercises routing (no new audit).
        # The router now has at least one skill registered from tick 0.
        report2 = pipeline.tick(
            step=1,
            audit_batch=[],
            verify_suite=None,
            router_query=np.array([1.0, 0.0, 0.0, 0.0]),
        )
        print(f"[M2] tick 1 (routing-only) route_picks={report2.route_picks}")


if __name__ == "__main__":
    main()
