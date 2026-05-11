"""Replay fixture export tests."""
from __future__ import annotations

import json

import numpy as np
import pytest

from gan_matchmaking.core import AppConfig, ArtifactsConfig, MetricsRegistry, load_config
from gan_matchmaking.core.errors import DataError
from gan_matchmaking.eomm import RetentionModel
from gan_matchmaking.persistence import SQLitePipelineStore
from gan_matchmaking.sre import ReleaseContext, SelfIterationPipeline
from gan_matchmaking.sre.artifacts import (
    EOMM_FEATURE_NAMES,
    build_metadata,
    save_cox_artifact,
    save_retention_artifact,
)
from gan_matchmaking.sre.features import RISK_FEATURE_NAMES
from gan_matchmaking.sre.replay import export_replay_fixture
from gan_matchmaking.survival import CoxModel


def _context_payload():
    return {
        "service": {
            "id": "svc-export",
            "mu": 0.995,
            "sigma": 0.005,
            "win_streak": 3,
            "total_releases": 30,
            "tier": "standard",
        },
        "candidates": [
            {
                "id": "c-canary",
                "strategy": "canary",
                "canary_fraction": 0.1,
                "rollback_budget_seconds": 300,
                "expected_success": 0.98,
            },
            {
                "id": "c-full",
                "strategy": "full",
                "canary_fraction": 0.0,
                "rollback_budget_seconds": 600,
                "expected_success": 0.97,
            },
        ],
        "error_budget_remaining": 0.8,
        "correlation_id": "export-corr-1",
    }


def _write_fitted_artifacts(path):
    retention_model = RetentionModel(
        weights=np.array([0.2, -0.1, 0.05, 0.01, 0.3, -0.2, 0.15, 0.04],
                         dtype=float),
        bias=-0.2,
    )
    retention_meta = build_metadata(
        "retention",
        source_window={"n_samples": 12},
        config={"fixture": "export", "model": "retention"},
        extra={
            "feature_dim": len(EOMM_FEATURE_NAMES),
            "feature_names": list(EOMM_FEATURE_NAMES),
        },
        trained_at=1.0,
        build_id="test-export",
    )
    save_retention_artifact(path, retention_model, retention_meta)

    cox_model = CoxModel(
        beta=np.array([0.1, -0.05, 0.2, 0.1, 0.05, 0.3], dtype=float),
        _baseline_t=np.array([1.0, 24.0], dtype=float),
        _baseline_H=np.array([0.01, 0.05], dtype=float),
    )
    cox_meta = build_metadata(
        "cox",
        source_window={"n_events": 3},
        config={"fixture": "export", "model": "cox"},
        extra={
            "feature_dim": len(RISK_FEATURE_NAMES),
            "feature_names": list(RISK_FEATURE_NAMES),
        },
        trained_at=1.0,
        build_id="test-export",
    )
    save_cox_artifact(path, cox_model, cox_meta)


def test_export_replay_fixture_from_sqlite_decision(tmp_path):
    db_path = tmp_path / "state.sqlite"
    store = SQLitePipelineStore(db_path)
    try:
        pipeline = SelfIterationPipeline(
            config=AppConfig(),
            metrics=MetricsRegistry(),
            store=store,
        )
        original = pipeline.decide(ReleaseContext.from_dict(_context_payload()))
    finally:
        store.close()

    out_path = tmp_path / "fixture.json"
    fixture = export_replay_fixture(
        db_path,
        "export-corr-1",
        output=out_path,
        name="exported-decision",
    )

    assert out_path.exists()
    assert json.loads(out_path.read_text(encoding="utf-8")) == fixture
    assert fixture["name"] == "exported-decision"
    assert fixture["context"]["service"]["id"] == "svc-export"
    assert fixture["expected"]["kind"] == original.kind.value
    assert fixture["expected"]["chosen_id"] == (
        original.chosen.id if original.chosen else None
    )
    assert fixture["expected"]["risk_level"] == original.risk_level.value
    assert fixture["expected"]["artifact_version"] == "bootstrap"
    assert fixture["source"]["correlation_id"] == "export-corr-1"

    replay = SelfIterationPipeline(
        config=load_config(fixture["config"]),
        metrics=MetricsRegistry(),
    ).decide(ReleaseContext.from_dict(fixture["context"]))
    assert replay.kind.value == fixture["expected"]["kind"]
    assert (replay.chosen.id if replay.chosen else None) == fixture["expected"]["chosen_id"]
    assert replay.risk_level.value == fixture["expected"]["risk_level"]


def test_export_fitted_decision_requires_artifact_bundle(tmp_path):
    artifact_dir = tmp_path / "runtime-artifacts"
    _write_fitted_artifacts(artifact_dir)
    db_path = tmp_path / "state.sqlite"
    store = SQLitePipelineStore(db_path)
    try:
        pipeline = SelfIterationPipeline(
            config=AppConfig(artifacts=ArtifactsConfig(directory=str(artifact_dir))),
            metrics=MetricsRegistry(),
            store=store,
        )
        original = pipeline.decide(ReleaseContext.from_dict(_context_payload()))
    finally:
        store.close()

    assert original.artifact_version != "bootstrap"
    with pytest.raises(DataError):
        export_replay_fixture(
            db_path,
            "export-corr-1",
            allow_fitted_artifacts=True,
        )


def test_export_fitted_decision_archives_valid_artifact_bundle(tmp_path):
    artifact_dir = tmp_path / "runtime-artifacts"
    _write_fitted_artifacts(artifact_dir)
    db_path = tmp_path / "state.sqlite"
    store = SQLitePipelineStore(db_path)
    try:
        pipeline = SelfIterationPipeline(
            config=AppConfig(artifacts=ArtifactsConfig(directory=str(artifact_dir))),
            metrics=MetricsRegistry(),
            store=store,
        )
        original = pipeline.decide(ReleaseContext.from_dict(_context_payload()))
    finally:
        store.close()

    out_path = tmp_path / "fixture.json"
    bundle_out = tmp_path / "artifact-bundles" / "export-corr-1"
    fixture = export_replay_fixture(
        db_path,
        "export-corr-1",
        output=out_path,
        allow_fitted_artifacts=True,
        artifact_directory=artifact_dir,
        artifact_output_directory=bundle_out,
        name="exported-fitted-decision",
    )

    bundle_path = out_path.parent / fixture["artifact_bundle"]["path"]
    assert bundle_path == bundle_out
    assert (bundle_path / "replay_artifact_manifest.json").exists()
    assert fixture["requires_artifact_version"] == original.artifact_version
    assert fixture["artifact_bundle"]["version"] == original.artifact_version
    assert fixture["expected"]["artifact_version"] == original.artifact_version

    config_raw = dict(fixture["config"])
    config_raw["artifacts"] = {
        **dict(config_raw.get("artifacts", {})),
        "directory": str(bundle_path),
    }
    replay = SelfIterationPipeline(
        config=load_config(config_raw),
        metrics=MetricsRegistry(),
    ).decide(ReleaseContext.from_dict(fixture["context"]))
    assert replay.artifact_version == original.artifact_version
    assert replay.kind.value == fixture["expected"]["kind"]
