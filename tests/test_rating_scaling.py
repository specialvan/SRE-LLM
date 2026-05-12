"""Tests for the rating scaling contract (F-005)."""
from __future__ import annotations

import io
import json
import logging
from pathlib import Path

import numpy as np
import pytest

from gan_matchmaking.core import AppConfig, ArtifactsConfig, MetricsRegistry
from gan_matchmaking.core.logging import JsonLineFormatter, JsonLineLogger
from gan_matchmaking.sre import SelfIterationPipeline
from gan_matchmaking.sre.artifacts import (
    ArtifactMetadata,
    EOMM_FEATURE_NAMES,
    _rating_scaling_version,
    save_retention_artifact,
)
from gan_matchmaking.sre.artifacts import retention as retention_mod
from gan_matchmaking.sre.domain import ReleaseCandidate, Service
from gan_matchmaking.eomm import RetentionModel


def _logger_to_buffer(name: str):
    logger = logging.getLogger(name)
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JsonLineFormatter())
    logger.addHandler(handler)
    wrapped = JsonLineLogger.__new__(JsonLineLogger)
    wrapped._logger = logger  # type: ignore[attr-defined]
    return wrapped, buf


def _parse_json_lines(buf: io.StringIO) -> list[dict]:
    buf.seek(0)
    return [json.loads(line) for line in buf.getvalue().splitlines() if line.strip()]


def test_rating_scaling_version_is_stable():
    """R-306: version hash is deterministic and 12 hex chars long."""
    v1 = _rating_scaling_version()
    v2 = _rating_scaling_version()
    assert v1 == v2
    assert len(v1) == 12
    assert all(c in "0123456789abcdef" for c in v1)


def test_rating_scaling_version_changes_with_constant(monkeypatch):
    """R-306: changing any _RATING_* constant must bump the version."""
    before = _rating_scaling_version()
    monkeypatch.setattr(retention_mod, "_RATING_MU_SLOPE", 17.5)
    after = _rating_scaling_version()
    assert before != after


def test_rating_scaling_contract_snapshot():
    """R-308: byte-level snapshot of Player rating construction."""
    svc = Service(
        id="snap", mu=0.95, sigma=0.03,
        win_streak=2, loss_streak=0, tier="standard",
    )
    p = retention_mod._service_player(svc)
    assert p.rating.mu == pytest.approx(
        25.0 + 18.0 * (0.95 - 0.5) + 1.5 * 2 - 1.0 * 0, rel=1e-9
    )
    assert p.rating.sigma == pytest.approx(
        max(1.0, 5.0 + 10.0 * 0.03 + 0.5 * 0), rel=1e-9
    )

    cand = ReleaseCandidate(
        id="c", service_id="snap", strategy="canary",
        canary_fraction=0.1, rollback_budget_seconds=180,
        expected_success=0.99,
    )
    q = retention_mod._candidate_player(cand)
    assert q.rating.mu == pytest.approx(
        25.0 + 18.0 * (0.99 - 0.5) + (-14.0) * 0.1, rel=1e-9
    )
    assert q.rating.sigma == pytest.approx(
        max(1.0, 4.0 + 20.0 * 0.1 + 0.5 * (1.0 - 0.99)), rel=1e-9
    )


def _build_retention_artifact(
    tmp_path: Path,
    *,
    rating_scaling_version: str | None,
) -> None:
    model = RetentionModel()
    model.weights = np.ones(len(EOMM_FEATURE_NAMES), dtype=float) * 0.25
    model.bias = 0.1
    extra: dict[str, object] = {
        "feature_dim": len(EOMM_FEATURE_NAMES),
        "feature_names": list(EOMM_FEATURE_NAMES),
    }
    if rating_scaling_version is not None:
        extra["rating_scaling_version"] = rating_scaling_version
    metadata = ArtifactMetadata(
        name="retention",
        version="test-fixed",
        trained_at=0.0,
        source_window={"n_samples": 128},
        config_hash="cfg",
        build_id="build",
        fitted=True,
        fallback=False,
        extra=extra,
    )
    save_retention_artifact(tmp_path, model, metadata)


def test_artifact_version_mismatch_downgrades_to_bootstrap(tmp_path):
    """R-307: mismatched version → downgrade + warning + trace marker."""
    _build_retention_artifact(tmp_path, rating_scaling_version="deadbeef0000")
    cfg = AppConfig(artifacts=ArtifactsConfig(directory=str(tmp_path)))
    pipeline = SelfIterationPipeline(config=cfg, metrics=MetricsRegistry())
    logger, buf = _logger_to_buffer("gan.test.rating.mismatch")
    pipeline.logger = logger
    # Re-run hydrate with the captured logger so warning goes into our buffer.
    pipeline.artifacts = pipeline.artifacts.with_scaling_status("match")
    # Reload the retention artifact from disk through the public loader.
    from gan_matchmaking.sre.artifacts import load_runtime_artifacts
    pipeline.artifacts = load_runtime_artifacts(str(tmp_path))
    pipeline._hydrate_runtime_artifacts()

    assert pipeline.artifacts.as_trace()["rating_scaling_status"] == "mismatch"
    assert pipeline.artifacts.retention is None
    lines = _parse_json_lines(buf)
    assert any(line["event"] == "artifacts.retention.scaling_mismatch"
               for line in lines)


def test_artifact_version_match_hydrates_retention(tmp_path):
    """R-307: matching version → retention stays loaded + status=match."""
    _build_retention_artifact(
        tmp_path, rating_scaling_version=_rating_scaling_version(),
    )
    cfg = AppConfig(artifacts=ArtifactsConfig(directory=str(tmp_path)))
    pipeline = SelfIterationPipeline(config=cfg, metrics=MetricsRegistry())

    assert pipeline.artifacts.as_trace()["rating_scaling_status"] == "match"
    assert pipeline.artifacts.retention is not None


def test_artifact_without_version_is_marked_unknown(tmp_path):
    """R-307: legacy artifact without version → status=unknown (still loaded)."""
    _build_retention_artifact(tmp_path, rating_scaling_version=None)
    cfg = AppConfig(artifacts=ArtifactsConfig(directory=str(tmp_path)))
    pipeline = SelfIterationPipeline(config=cfg, metrics=MetricsRegistry())

    assert pipeline.artifacts.as_trace()["rating_scaling_status"] == "unknown"
    assert pipeline.artifacts.retention is not None
