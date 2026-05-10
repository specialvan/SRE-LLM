"""Integration & property tests for :class:`SelfIterationPipeline`."""
from __future__ import annotations

import numpy as np
import pytest

from gan_matchmaking.core import AppConfig, MetricsRegistry
from gan_matchmaking.core.config import ArtifactsConfig
from gan_matchmaking.core.errors import DataError
from gan_matchmaking.eomm import RetentionModel
from gan_matchmaking.survival import CoxModel
from gan_matchmaking.sre import (
    Decision,
    DecisionKind,
    ReleaseCandidate,
    ReleaseContext,
    RiskLevel,
    SelfIterationPipeline,
    Service,
)
from gan_matchmaking.sre.artifacts import (
    build_metadata,
    save_cox_artifact,
    save_retention_artifact,
)


def _ctx(**overrides):
    service = overrides.pop("service", Service(id="svc-a", mu=0.995, sigma=0.005,
                                               win_streak=3, total_releases=30))
    candidates = overrides.pop("candidates", [
        ReleaseCandidate(id="c-canary", service_id=service.id, strategy="canary",
                         canary_fraction=0.1, rollback_budget_seconds=300,
                         expected_success=0.98),
        ReleaseCandidate(id="c-full", service_id=service.id, strategy="full",
                         canary_fraction=0.0, rollback_budget_seconds=600,
                         expected_success=0.97),
    ])
    return ReleaseContext(service=service, candidates=candidates, **overrides)


def _pipeline():
    # Fresh metrics registry per test — avoids shared state across tests.
    return SelfIterationPipeline(config=AppConfig(), metrics=MetricsRegistry())


def test_decision_returns_valid_decision_for_healthy_service():
    pipeline = _pipeline()
    decision = pipeline.decide(_ctx())
    assert isinstance(decision, Decision)
    assert decision.kind in {DecisionKind.GO, DecisionKind.CANARY}
    assert decision.chosen is not None
    assert decision.risk_level in {RiskLevel.OK, RiskLevel.WARN, RiskLevel.ALARM}
    assert 0.0 <= decision.risk_prob <= 1.0
    assert 0.0 <= decision.confidence <= 1.0
    assert "stages" in decision.trace
    assert {"pca", "synergy", "adjusted_probs", "entropy", "eomm", "risk"} <= decision.trace["stages"].keys()
    assert decision.artifact_version == "bootstrap"
    assert decision.trace["artifacts"]["version"] == "bootstrap"


def test_freeze_window_forces_hold():
    decision = _pipeline().decide(_ctx(freeze_window=True))
    assert decision.kind == DecisionKind.HOLD
    assert any("freeze_window" in r for r in decision.rationale)


def test_exhausted_budget_forces_rollback():
    decision = _pipeline().decide(_ctx(error_budget_remaining=0.0))
    assert decision.kind == DecisionKind.ROLLBACK
    assert decision.risk_level == RiskLevel.ALARM


def test_no_candidates_raises_data_error():
    pipeline = _pipeline()
    bad = ReleaseContext(service=Service(id="svc"), candidates=[])
    with pytest.raises(DataError):
        pipeline.decide(bad)


def test_candidate_service_id_mismatch_raises():
    pipeline = _pipeline()
    service = Service(id="svc-a")
    bad = ReleaseContext(
        service=service,
        candidates=[ReleaseCandidate(id="c", service_id="other",
                                     strategy="canary", canary_fraction=0.1,
                                     rollback_budget_seconds=60)],
    )
    with pytest.raises(DataError):
        pipeline.decide(bad)


def test_loss_streak_and_alarm_triggers_rollback():
    pipeline = _pipeline()
    service = Service(id="svc-a", mu=0.80, sigma=0.08, loss_streak=3)
    ctx = _ctx(service=service,
               candidates=[ReleaseCandidate(id="c", service_id="svc-a",
                                            strategy="canary", canary_fraction=0.05,
                                            rollback_budget_seconds=60,
                                            expected_success=0.9)])
    decision = pipeline.decide(ctx)
    # With low mu and loss_streak, the Cox heuristic will push risk_level up.
    assert decision.kind in {DecisionKind.HOLD, DecisionKind.ROLLBACK}


def test_critical_tier_forced_to_canary():
    pipeline = _pipeline()
    service = Service(id="svc-crit", mu=0.999, sigma=0.001,
                      win_streak=10, total_releases=100, tier="critical")
    cand_full = ReleaseCandidate(id="c-full", service_id="svc-crit",
                                 strategy="full", canary_fraction=0.0,
                                 rollback_budget_seconds=300,
                                 expected_success=0.995)
    cand_canary = ReleaseCandidate(id="c-canary", service_id="svc-crit",
                                   strategy="canary", canary_fraction=0.05,
                                   rollback_budget_seconds=300,
                                   expected_success=0.995)
    ctx = _ctx(service=service, candidates=[cand_full, cand_canary])
    decision = pipeline.decide(ctx)
    assert decision.kind == DecisionKind.CANARY


def test_observe_release_shifts_confidence():
    pipeline = _pipeline()
    svc = Service(id="svc-z", mu=0.90, sigma=0.10)
    pipeline.register_service(svc)
    initial = svc.mu
    for _ in range(20):
        pipeline.observe_release("svc-z", success=True)
    assert svc.mu > initial
    assert svc.sigma < 0.10
    assert svc.win_streak == 20


def test_correlation_id_propagated():
    pipeline = _pipeline()
    ctx = _ctx(correlation_id="corr-1234")
    decision = pipeline.decide(ctx)
    assert decision.correlation_id == "corr-1234"


def test_metrics_counter_increments_on_decide():
    reg = MetricsRegistry()
    pipeline = SelfIterationPipeline(config=AppConfig(), metrics=reg)
    pipeline.decide(_ctx())
    pipeline.decide(_ctx())
    total = sum(v for v in reg.get("gan_decisions_total").snapshot().values())
    assert total == 2


def test_deterministic_decision_under_same_config():
    reg1 = MetricsRegistry()
    reg2 = MetricsRegistry()
    p1 = SelfIterationPipeline(config=AppConfig(), metrics=reg1)
    p2 = SelfIterationPipeline(config=AppConfig(), metrics=reg2)
    d1 = p1.decide(_ctx())
    d2 = p2.decide(_ctx())
    assert d1.kind == d2.kind
    assert d1.chosen and d2.chosen
    assert d1.chosen.id == d2.chosen.id
    assert d1.risk_level == d2.risk_level


def test_pipeline_hydrates_runtime_artifacts(tmp_path):
    retention_model = RetentionModel()
    retention_model.weights = np.array([0.2, -0.1, 0.05, 0.01, 0.3, -0.2, 0.15, 0.04], dtype=float)
    retention_model.bias = -0.2
    retention_meta = build_metadata(
        "retention",
        source_window={"n_samples": 12, "n_observations": 18},
        config={"lr": 0.05, "iters": 200},
        build_id="test-build",
    )
    save_retention_artifact(tmp_path, retention_model, retention_meta)

    cox_model = CoxModel(
        beta=np.array([0.9, -0.4], dtype=float),
        _baseline_t=np.array([1.0, 10.0], dtype=float),
        _baseline_H=np.array([0.1, 0.25], dtype=float),
    )
    cox_meta = build_metadata(
        "cox",
        source_window={"n_observations": 18, "n_events": 6},
        config={"min_events": 3},
        build_id="test-build",
    )
    save_cox_artifact(tmp_path, cox_model, cox_meta)

    cfg = AppConfig(artifacts=ArtifactsConfig(directory=str(tmp_path)))
    pipeline = SelfIterationPipeline(config=cfg, metrics=MetricsRegistry())

    assert pipeline.artifacts.version == f"retention@{retention_meta.version}+cox@{cox_meta.version}"
    assert pipeline.eomm.model.bias == pytest.approx(retention_model.bias)
    assert np.allclose(pipeline.eomm.model.weights, retention_model.weights)
    assert np.allclose(pipeline.risk.model.beta, cox_model.beta)

    decision = pipeline.decide(_ctx())
    assert decision.artifact_version == pipeline.artifacts.version
    assert decision.trace["artifacts"]["version"] == pipeline.artifacts.version
    assert decision.trace["stages"]["eomm"]["source"] == "artifact"
