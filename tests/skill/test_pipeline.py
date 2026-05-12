"""Tests for :class:`SkillOpsPipeline` (PR-025)."""

from __future__ import annotations

import numpy as np
import pytest

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
    PipelineReport,
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


# -----------------------------------------------------------------------------
# Fixture helpers
# -----------------------------------------------------------------------------


def _build_audit(n: int = 20) -> list[AuditRecord]:
    signals = ["cost", "error_budget"]
    return [
        AuditRecord(
            step=i,
            signal_names=signals,
            weights=np.array([0.92, 0.08]),
            action=np.zeros(1),
            context={"slo_breach": 3.0, "tenant": "default"},
        )
        for i in range(n)
    ]


def _build_harness() -> CombinerHarness:
    signals = [
        SignalSpec("cost", floor=0.0, ceiling=1.0, bias=0.0),
        SignalSpec("error_budget", floor=0.25, ceiling=1.0, bias=0.0),
    ]
    baseline = WeightedConvexCombiner(signals, query_dim=2, temperature=1.0, rng_seed=31)
    return CombinerHarness(baseline, tolerance=0.5)


def _build_suite() -> list[ReplayCase]:
    return [
        ReplayCase(
            case_id="baseline-friendly",
            signals=("cost", "error_budget"),
            query=np.array([1.0, 0.0]),
            values=(np.array([0.0]), np.array([1.0])),
            tolerance=0.5,
        )
    ]


def _make_pipeline(tmp_path=None) -> SkillOpsPipeline:
    snapshot = MustAttendSnapshot(
        floors={"error_budget": 0.25}, registry_hash="reg-m2-v1"
    )
    miner = Trace2SkillMiner(
        MinerConfig(support_min=5, cost_quantile=0.5, cluster_k_max=1)
    )
    merger = HierarchicalPatchMerger(snapshot)
    patcher = SkillPatcher(PatcherConfig(max_delta_per_step=0.05))
    harness = _build_harness()
    verifier = SkillShadowVerifier(harness)
    gate = SkillRegressionGate(GateConfig(divergence_ceiling=5.0))
    repo = SkillRepository(
        graph=SkillVersionGraph(),
        base_dir=tmp_path,
    )
    elite = ElitePool(ElitePoolConfig(capacity=4, min_probation_steps=0))
    bank = DualGranularitySkillBank()
    retriever = UtilityAwareRetriever(
        dim=4, config=RetrieverConfig(lambda_util=0.2, lambda_explore=0.1)
    )
    utility = HindsightUtilityTracker(HindsightConfig(alpha_ema=0.3))
    explore = ExplorationBiasScheduler(
        ExploreConfig(beta0=0.3, min_protection_uses=5, global_budget=5.0)
    )
    router = SkillRouter(
        bank=bank,
        retriever=retriever,
        utility=utility,
        explore=explore,
        config=RouterConfig(default_top_k=2),
    )
    deps = PipelineDeps(
        repository=repo,
        conservative=ConservativeCommit(),
        elite=elite,
        miner=miner,
        merger=merger,
        patcher=patcher,
        verifier=verifier,
        gate=gate,
        bank=bank,
        retriever=retriever,
        utility=utility,
        explore=explore,
        router=router,
        registry_snapshot=snapshot,
    )
    return SkillOpsPipeline(deps)


# -----------------------------------------------------------------------------
# REQ-OPS-001 · advances every phase
# -----------------------------------------------------------------------------


def test_req_ops_001_tick_advances_phases(tmp_path) -> None:
    pipeline = _make_pipeline(tmp_path)
    report = pipeline.tick(
        step=0,
        audit_batch=_build_audit(),
        verify_suite=_build_suite(),
        router_query=np.array([1.0, 0.0, 0.0, 0.0]),
    )
    assert isinstance(report, PipelineReport)
    phase_names = [p.name for p in report.phases]
    assert phase_names == [
        "evidence", "mine", "merge", "propose", "verify", "gate", "govern", "route"
    ]
    assert report.total_ms > 0
    assert report.candidates_mined > 0
    assert report.merged_targets > 0
    assert report.gate_admits >= 1
    assert report.elite_admissions >= 1


def test_req_ops_003_exception_isolated_as_phase_note(tmp_path) -> None:
    pipeline = _make_pipeline(tmp_path)

    class _ExplodingMerger:
        def merge(self, candidates):  # pragma: no cover - raise only
            raise RuntimeError("merge boom")

    pipeline.deps.merger = _ExplodingMerger()  # type: ignore[assignment]
    report = pipeline.tick(
        step=1,
        audit_batch=_build_audit(),
        verify_suite=_build_suite(),
        router_query=np.array([1.0, 0.0, 0.0, 0.0]),
    )
    merge_phase = next(p for p in report.phases if p.name == "merge")
    assert merge_phase.errored
    assert "merge boom" in (merge_phase.error or "")
    # Subsequent phases should still run (they'll mostly skip).
    names_after_merge = [p.name for p in report.phases[report.phases.index(merge_phase):]]
    assert names_after_merge[1:]  # at least one more phase recorded


def test_pause_returns_skipped_report(tmp_path) -> None:
    pipeline = _make_pipeline(tmp_path)
    pipeline.pause()
    report = pipeline.tick(
        step=0,
        audit_batch=_build_audit(),
        verify_suite=_build_suite(),
        router_query=np.array([1.0, 0.0, 0.0, 0.0]),
    )
    assert report.skipped_reason == "paused"
    assert report.phases == []
    pipeline.resume()
    assert pipeline.tick(
        step=1,
        audit_batch=_build_audit(),
        verify_suite=_build_suite(),
        router_query=np.array([1.0, 0.0, 0.0, 0.0]),
    ).phases  # non-empty


def test_missing_audit_skips_gracefully(tmp_path) -> None:
    pipeline = _make_pipeline(tmp_path)
    report = pipeline.tick(
        step=0,
        audit_batch=[],
        verify_suite=_build_suite(),
        router_query=np.array([1.0, 0.0, 0.0, 0.0]),
    )
    evidence = next(p for p in report.phases if p.name == "evidence")
    assert evidence.note and "no audit batch" in evidence.note
    assert report.candidates_mined == 0
    assert report.elite_admissions == 0


def test_pipeline_without_verifier_or_router_is_safe(tmp_path) -> None:
    pipeline = _make_pipeline(tmp_path)
    pipeline.deps.verifier = None
    pipeline.deps.router = None
    report = pipeline.tick(
        step=0,
        audit_batch=_build_audit(),
        verify_suite=None,
        router_query=None,
    )
    verify_phase = next(p for p in report.phases if p.name == "verify")
    route_phase = next(p for p in report.phases if p.name == "route")
    assert verify_phase.note  # skipped
    assert route_phase.note   # skipped
    # The pipeline did not crash.
    assert report.total_ms > 0


def test_three_consecutive_ticks_are_stable(tmp_path) -> None:
    pipeline = _make_pipeline(tmp_path)
    for step in range(3):
        report = pipeline.tick(
            step=step,
            audit_batch=_build_audit(),
            verify_suite=_build_suite(),
            router_query=np.array([1.0, 0.0, 0.0, 0.0]),
        )
        assert report.skipped_reason is None
        assert report.total_ms > 0
