"""Replay fixture export tests."""
from __future__ import annotations

import json
import os

import numpy as np
import pytest

from gan_matchmaking.core import AppConfig, ArtifactsConfig, MetricsRegistry, load_config
from gan_matchmaking.core.errors import DataError
from gan_matchmaking.eomm import RetentionModel
from gan_matchmaking.persistence import SQLitePipelineStore
from gan_matchmaking.sre import ReleaseContext, SelfIterationPipeline
from gan_matchmaking.sre.artifacts import (
    EOMM_FEATURE_NAMES,
    _rating_scaling_version,
    build_metadata,
    save_cox_artifact,
    save_retention_artifact,
)
from gan_matchmaking.sre.features import RISK_FEATURE_NAMES
from gan_matchmaking.sre.replay import archive_artifact_bundle, export_replay_fixture
from gan_matchmaking.sre.shadow import ShadowMode
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
            "rating_scaling_version": _rating_scaling_version(),
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


def test_export_replay_fixture_round_trips_shadow_mode(tmp_path):
    db_path = tmp_path / "state.sqlite"
    store = SQLitePipelineStore(db_path)
    try:
        pipeline = SelfIterationPipeline(
            config=AppConfig(),
            metrics=MetricsRegistry(),
            store=store,
            shadow_mode=ShadowMode.ADVISORY,
        )
        original = pipeline.decide(
            ReleaseContext.from_dict(
                {
                    **_context_payload(),
                    "error_budget_remaining": 0.0,
                    "correlation_id": "export-shadow-corr-1",
                }
            )
        )
    finally:
        store.close()

    out_path = tmp_path / "shadow-fixture.json"
    fixture = export_replay_fixture(
        db_path,
        "export-shadow-corr-1",
        output=out_path,
        name="exported-shadow-decision",
    )

    assert fixture["shadow_mode"] == ShadowMode.ADVISORY.value
    assert fixture["expected"]["kind"] == original.kind.value
    assert fixture["expected"]["trace_values"]["shadow_mode"] == ShadowMode.ADVISORY.value
    assert json.loads(out_path.read_text(encoding="utf-8"))["shadow_mode"] == ShadowMode.ADVISORY.value

    replay = SelfIterationPipeline(
        config=load_config(fixture["config"]),
        metrics=MetricsRegistry(),
        shadow_mode=fixture["shadow_mode"],
    ).decide(ReleaseContext.from_dict(fixture["context"]))
    assert replay.kind.value == fixture["expected"]["kind"]
    assert replay.trace["shadow_mode"] == ShadowMode.ADVISORY.value
    assert any("shadow_mode=advisory" in item for item in replay.rationale)


def test_export_replay_fixture_round_trips_shadow_mode_rewrite(tmp_path):
    db_path = tmp_path / "state.sqlite"
    store = SQLitePipelineStore(db_path)
    try:
        pipeline = SelfIterationPipeline(
            config=AppConfig(),
            metrics=MetricsRegistry(),
            store=store,
            shadow_mode=ShadowMode.SHADOW,
        )
        original = pipeline.decide(
            ReleaseContext.from_dict(
                {
                    **_context_payload(),
                    "error_budget_remaining": 0.0,
                    "correlation_id": "export-shadow-hold-corr-1",
                }
            )
        )
    finally:
        store.close()

    out_path = tmp_path / "shadow-hold-fixture.json"
    fixture = export_replay_fixture(
        db_path,
        "export-shadow-hold-corr-1",
        output=out_path,
        name="exported-shadow-hold-decision",
    )

    assert fixture["shadow_mode"] == ShadowMode.SHADOW.value
    assert fixture["expected"]["kind"] == original.kind.value
    assert fixture["expected"]["trace_values"]["shadow_mode"] == ShadowMode.SHADOW.value
    assert fixture["expected"]["trace_values"]["shadow_suppressed_kind"] == "rollback"
    assert json.loads(out_path.read_text(encoding="utf-8"))["shadow_mode"] == ShadowMode.SHADOW.value

    replay = SelfIterationPipeline(
        config=load_config(fixture["config"]),
        metrics=MetricsRegistry(),
        shadow_mode=fixture["shadow_mode"],
    ).decide(ReleaseContext.from_dict(fixture["context"]))
    assert replay.kind.value == fixture["expected"]["kind"]
    assert replay.trace["shadow_mode"] == ShadowMode.SHADOW.value
    assert replay.trace["shadow_suppressed_kind"] == "rollback"
    assert any("shadow_mode=shadow" in item for item in replay.rationale)


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


@pytest.mark.parametrize(
    "filename",
    [
        "../retention_weights.npz",
        "..\\retention_weights.npz",
        "/tmp/retention_weights.npz",
        "C:\\tmp\\retention_weights.npz",
        "\\\\server\\share\\retention_weights.npz",
    ],
)
def test_validate_artifact_bundle_rejects_path_traversal_filename(tmp_path, filename):
    from gan_matchmaking.sre.replay import validate_artifact_bundle

    _write_fitted_artifacts(tmp_path)

    with pytest.raises(DataError) as exc_info:
        validate_artifact_bundle(
            tmp_path,
            "retention@0e0b32d594442c35+cox@a27fddc11a9484da",
            config={"artifacts": {"retention_filename": filename}},
        )

    assert exc_info.value.details["field"] == "artifacts.retention_filename"


def test_archive_artifact_bundle_fails_closed_without_secure_directory_handle(tmp_path):
    artifact_dir = tmp_path / "runtime-artifacts"
    _write_fitted_artifacts(artifact_dir)

    if os.name == "nt":
        with pytest.raises(DataError) as exc_info:
            archive_artifact_bundle(
                artifact_dir,
                tmp_path / "artifact-bundles" / "export-corr-1",
                "retention@0e0b32d594442c35+cox@a27fddc11a9484da",
            )
        assert "opened securely" in str(exc_info.value)
    else:
        manifest = archive_artifact_bundle(
            artifact_dir,
            tmp_path / "artifact-bundles" / "export-corr-1",
            "retention@0e0b32d594442c35+cox@a27fddc11a9484da",
        )
        assert manifest["version"] == "retention@0e0b32d594442c35+cox@a27fddc11a9484da"


@pytest.mark.skipif(os.name == "nt", reason="secure archive directory handles unavailable")
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
    assert "directory" not in dict(config_raw.get("artifacts", {}))
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


@pytest.mark.skipif(os.name == "nt", reason="secure archive directory handles unavailable")
@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlink unavailable")
def test_archive_artifact_bundle_rejects_symlinked_artifact_file(tmp_path):
    artifact_dir = tmp_path / "runtime-artifacts"
    _write_fitted_artifacts(artifact_dir)
    sensitive_file = tmp_path / "outside-secret.txt"
    sensitive_file.write_text("do-not-copy", encoding="utf-8")
    (artifact_dir / "cox_artifact.json").unlink()
    os.symlink(sensitive_file, artifact_dir / "cox_artifact.json")

    with pytest.raises(DataError) as exc_info:
        archive_artifact_bundle(
            artifact_dir,
            tmp_path / "artifact-bundles" / "export-corr-1",
            "retention@0e0b32d594442c35+cox@a27fddc11a9484da",
        )

    assert exc_info.value.details["filename"] == "cox_artifact.json"
    assert not (tmp_path / "artifact-bundles" / "export-corr-1" / "cox_artifact.json").exists()


@pytest.mark.skipif(os.name == "nt", reason="secure archive directory handles unavailable")
@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlink unavailable")
def test_archive_artifact_bundle_rejects_symlinked_destination_file(tmp_path):
    artifact_dir = tmp_path / "runtime-artifacts"
    _write_fitted_artifacts(artifact_dir)
    bundle_out = tmp_path / "artifact-bundles" / "export-corr-1"
    bundle_out.mkdir(parents=True)
    sensitive_file = tmp_path / "outside-secret.txt"
    sensitive_file.write_text("do-not-overwrite", encoding="utf-8")
    os.symlink(sensitive_file, bundle_out / "cox_artifact.json")

    with pytest.raises(DataError) as exc_info:
        archive_artifact_bundle(
            artifact_dir,
            bundle_out,
            "retention@0e0b32d594442c35+cox@a27fddc11a9484da",
        )

    assert exc_info.value.details["path"] == str(bundle_out)
    assert sensitive_file.read_text(encoding="utf-8") == "do-not-overwrite"


@pytest.mark.skipif(os.name == "nt", reason="secure archive directory handles unavailable")
@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlink unavailable")
def test_archive_artifact_bundle_rejects_symlinked_output_directory(tmp_path):
    artifact_dir = tmp_path / "runtime-artifacts"
    _write_fitted_artifacts(artifact_dir)
    outside_dir = tmp_path / "outside-archive"
    outside_dir.mkdir()
    artifact_bundles = tmp_path / "artifact-bundles"
    artifact_bundles.mkdir()
    bundle_out = artifact_bundles / "export-corr-1"
    os.symlink(outside_dir, bundle_out, target_is_directory=True)

    with pytest.raises(DataError) as exc_info:
        archive_artifact_bundle(
            artifact_dir,
            bundle_out,
            "retention@0e0b32d594442c35+cox@a27fddc11a9484da",
        )

    assert exc_info.value.details["path"] == str(bundle_out)
    assert not (outside_dir / "replay_artifact_manifest.json").exists()
