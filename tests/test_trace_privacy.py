"""Tests for the decision-trace config allowlist."""
from __future__ import annotations

from gan_matchmaking.core import AppConfig, MetricsRegistry
from gan_matchmaking.core.config import ArtifactsConfig, ObservabilityConfig
from gan_matchmaking.sre import (
    ReleaseCandidate,
    ReleaseContext,
    SelfIterationPipeline,
    Service,
)


EXPECTED_ALLOWLIST = {
    "seed": None,
    "observability": ["log_level", "service_name"],
    "trueskill": ["mu0", "sigma0", "beta", "tau", "draw_probability"],
    "dynamic_k": ["k_max", "k_min", "lam", "theta", "penalize_wins"],
    "handicap": ["max_penalty", "tau"],
    "entropy": ["min_entropy"],
    "eomm": ["epsilon", "lr", "iters", "l2"],
    "survival": ["horizon_hours", "warn_threshold", "alarm_threshold"],
    "gnn": ["hidden_dim", "layers", "seed"],
    "artifacts": [
        "directory",
        "retention_filename",
        "retention_metadata_filename",
        "cox_filename",
        "cox_metadata_filename",
    ],
}


def _sample_ctx() -> ReleaseContext:
    svc = Service(id="svc-priv", mu=0.99, sigma=0.02, tier="standard")
    cand = ReleaseCandidate(
        id="c1",
        service_id=svc.id,
        strategy="canary",
        canary_fraction=0.05,
        rollback_budget_seconds=180,
        expected_success=0.99,
    )
    return ReleaseContext(service=svc, candidates=[cand], correlation_id="priv-1")


def test_trace_config_only_embeds_allowlisted_keys(tmp_path):
    cfg = AppConfig(
        observability=ObservabilityConfig(
            log_level="INFO",
            log_sink=str(tmp_path / "internal-secret-path.log"),
            emit_metrics=True,
            service_name="svc-test",
        ),
    )
    pipeline = SelfIterationPipeline(config=cfg, metrics=MetricsRegistry())

    decision = pipeline.decide(_sample_ctx())

    trace_cfg = decision.trace["input"]["config"]
    assert "log_sink" not in trace_cfg["observability"]
    assert "emit_metrics" not in trace_cfg["observability"]
    assert trace_cfg["observability"] == {
        "log_level": "INFO",
        "service_name": "svc-test",
    }
    assert trace_cfg["seed"] == 0
    assert cfg.to_dict()["observability"]["log_sink"] == str(
        tmp_path / "internal-secret-path.log"
    )


def test_trace_config_allowlist_snapshot():
    assert AppConfig.trace_allowlist_snapshot() == EXPECTED_ALLOWLIST


def test_to_trace_dict_is_pure():
    cfg = AppConfig()

    first = cfg.to_trace_dict()
    second = cfg.to_trace_dict()
    first["seed"] = 999

    assert second == cfg.to_trace_dict()
    assert cfg.seed == 0


def test_to_trace_dict_preserves_optional_artifact_fields():
    cfg = AppConfig(
        artifacts=ArtifactsConfig(
            directory=None,
            retention_filename="r.npz",
            retention_metadata_filename="r.json",
            cox_filename="c.npz",
            cox_metadata_filename="c.json",
        ),
    )

    trace_cfg = cfg.to_trace_dict()

    assert trace_cfg["artifacts"]["directory"] is None
    assert trace_cfg["artifacts"]["retention_filename"] == "r.npz"
