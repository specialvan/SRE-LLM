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


def test_reject_symlink_artifacts(tmp_path):
    """Validate that symlink artifacts in the bundle directory are rejected."""
    from gan_matchmaking.sre.replay import _reject_symlink_artifacts

    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    sensitive = tmp_path / "outside.txt"
    sensitive.write_text("secret")
    os.symlink(sensitive, artifact_dir / "retention_weights.npz")

    with pytest.raises(DataError) as exc_info:
        _reject_symlink_artifacts(artifact_dir, {"retention_filename": "retention_weights.npz"})
    assert "must not be a symlink" in str(exc_info.value)


def test_open_no_follow_read_rejects_symlink(tmp_path):
    """Verify that _open_no_follow_read rejects symlinked files."""
    from gan_matchmaking.sre.replay import _open_no_follow_read

    real_file = tmp_path / "real.txt"
    real_file.write_text("content", encoding="utf-8")
    link_file = tmp_path / "link.txt"
    try:
        os.symlink(real_file, link_file)
    except (AttributeError, NotImplementedError, OSError):
        pytest.skip("symlink unavailable")

    with pytest.raises(DataError) as exc_info:
        _open_no_follow_read(link_file, filename="link.txt")
    assert "must be a regular non-symlink file" in str(exc_info.value)


def test_open_no_follow_read_rejects_directory(tmp_path):
    """Verify that _open_no_follow_read rejects directories."""
    from gan_matchmaking.sre.replay import _open_no_follow_read

    with pytest.raises(DataError) as exc_info:
        _open_no_follow_read(tmp_path, filename=".")
    assert "must be a regular non-symlink file" in str(exc_info.value)


def test_copy_regular_file_no_follow_validates_source(tmp_path):
    """Verify that file copy validates source is a regular file."""
    from gan_matchmaking.sre.replay import _copy_regular_file_no_follow

    real_file = tmp_path / "source.txt"
    real_file.write_text("data", encoding="utf-8")
    link_file = tmp_path / "link.txt"
    try:
        os.symlink(real_file, link_file)
    except (AttributeError, NotImplementedError, OSError):
        pytest.skip("symlink unavailable")

    with pytest.raises(DataError) as exc_info:
        _copy_regular_file_no_follow(link_file, filename="link.txt", dir_fd=-1)
    assert "must be a regular non-symlink file" in str(exc_info.value)


def test_reject_symlink_path(tmp_path):
    """Verify that symlink paths in archive output are rejected."""
    from gan_matchmaking.sre.replay import _reject_symlink_path

    target = tmp_path / "outside"
    target.mkdir()
    link = tmp_path / "link_to_outside"
    try:
        os.symlink(target, link, target_is_directory=True)
    except (AttributeError, NotImplementedError, OSError):
        pytest.skip("symlink unavailable")

    with pytest.raises(DataError) as exc_info:
        _reject_symlink_path(link)
    assert "must not contain symlinks" in str(exc_info.value)


def test_safe_fixture_name_handles_edge_cases():
    """Verify _safe_fixture_name handles empty and special characters."""
    from gan_matchmaking.sre.replay import _safe_fixture_name

    assert _safe_fixture_name("") == "replay_fixture"
    assert _safe_fixture_name("   ") == "replay_fixture"
    assert _safe_fixture_name("..") == "replay_fixture"
    assert _safe_fixture_name("./") == "replay_fixture"
    assert _safe_fixture_name("abc-123_DEF.ghi") == "abc-123_DEF.ghi"
    assert _safe_fixture_name("file/with/slashes") == "file_with_slashes"


def test_loads_json_field_rejects_invalid_json():
    """Verify JSON parsing errors are wrapped with context."""
    from gan_matchmaking.sre.replay import _loads_json_field

    with pytest.raises(DataError) as exc_info:
        _loads_json_field("not valid json {{{", field="test_field", correlation_id="test-123")
    assert exc_info.value.details["field"] == "test_field"
    assert exc_info.value.details["correlation_id"] == "test-123"


def test_artifact_filename_rejects_various_attacks():
    """Verify path traversal attempts in artifact filenames are rejected."""
    from gan_matchmaking.sre.replay import _artifact_filename

    dangerous_filenames = [
        "../etc/passwd",
        "..\\windows\\system32",
        "/absolute/path",
        "C:\\absolute\\windows",
        "subdir/filename",
        "../../escape",
    ]
    for dangerous in dangerous_filenames:
        with pytest.raises(DataError) as exc_info:
            _artifact_filename(dangerous, key="test_key")
        assert "must be a basename" in str(exc_info.value)


def test_artifact_filename_accepts_safe_names():
    """Verify safe artifact filenames are accepted."""
    from gan_matchmaking.sre.replay import _artifact_filename

    safe_filenames = [
        "retention_weights.npz",
        "cox_beta.npz",
        "artifact.json",
        "data-file.txt",
        "v1.2.3_model.bin",
    ]
    for safe in safe_filenames:
        assert _artifact_filename(safe, key="test_key") == safe


def test_relative_or_absolute_handles_both_cases(tmp_path):
    """Verify relative/absolute path resolution."""
    from gan_matchmaking.sre.replay import _relative_or_absolute

    from pathlib import Path

    # With base - use actual tmp_path for cross-platform correctness
    base = tmp_path / "project"
    base.mkdir()
    child = base / "src" / "main.py"
    child.parent.mkdir()
    child.write_text("", encoding="utf-8")

    # Relative path works
    result = _relative_or_absolute(child, base=base)
    assert result.replace("\\", "/") == "src/main.py"

    # Absolute path outside base returns absolute
    external = tmp_path / "other" / "path.py"
    external.parent.mkdir()
    external.write_text("", encoding="utf-8")
    result2 = _relative_or_absolute(external, base=base)
    # Should be absolute
    assert result2.replace("\\", "/") in ("other/path.py", str(external).replace("\\", "/"))

    # Without base returns absolute path
    assert _relative_or_absolute(child, base=None) == str(child)


@pytest.mark.skipif(os.name == "nt", reason="secure archive directory handles unavailable")
def test_create_archive_directory_rejects_existing(tmp_path):
    """Verify archive directory creation fails if path already exists."""
    from gan_matchmaking.sre.replay import _create_archive_directory

    existing = tmp_path / "already_exists"
    existing.mkdir()
    with pytest.raises(DataError) as exc_info:
        _create_archive_directory(existing)
    assert "must not already exist" in str(exc_info.value)


@pytest.mark.skipif(os.name == "nt", reason="secure archive directory handles unavailable")
def test_write_new_file_no_follow(tmp_path):
    """Verify atomic file write with no-follow semantics."""
    from gan_matchmaking.sre.replay import _write_new_file_no_follow

    content = '{"key": "value"}'
    tmp_dir = tmp_path / "atomic_write"
    tmp_dir.mkdir()

    # Use dir_fd via file creation
    dir_fd = os.open(str(tmp_dir), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        _write_new_file_no_follow(content, filename="test.json", dir_fd=dir_fd)
        written = (tmp_dir / "test.json").read_text(encoding="utf-8")
        assert written == content
    finally:
        os.close(dir_fd)


@pytest.mark.skipif(os.name == "nt", reason="secure archive directory handles unavailable")
def test_open_directory_at_rejects_symlink(tmp_path):
    """Verify directory opening rejects symlinked paths."""
    from gan_matchmaking.sre.replay import _open_directory_at

    target = tmp_path / "real_dir"
    target.mkdir()
    link = tmp_path / "link_dir"
    try:
        os.symlink(target, link, target_is_directory=True)
    except (AttributeError, NotImplementedError, OSError):
        pytest.skip("symlink unavailable")

    parent_fd = os.open(str(tmp_path), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        with pytest.raises(DataError) as exc_info:
            _open_directory_at(parent_fd, "link_dir", path=link)
        assert "must not contain symlinks" in str(exc_info.value)
    finally:
        os.close(parent_fd)


def test_load_decision_audit_row_not_found(tmp_path):
    """Verify error when correlation_id not found in database."""
    from gan_matchmaking.sre.replay import load_decision_audit_row

    db = tmp_path / "nonexistent.db"
    with pytest.raises(DataError) as exc_info:
        load_decision_audit_row(db, "missing-corr-id")
    assert "not found" in str(exc_info.value)


def test_build_replay_fixture_requires_context():
    """Verify error when replay context is missing."""
    from gan_matchmaking.sre.replay import build_replay_fixture, DecisionAuditRow

    row = DecisionAuditRow(
        correlation_id="test-123",
        kind="go",
        risk_level="low",
        risk_prob=0.1,
        confidence=0.9,
        chosen_id="svc-1",
        artifact_version="bootstrap",
        rationale=["test"],
        trace={"input": {}},  # Missing context
        created_at=1.0,
    )
    with pytest.raises(DataError) as exc_info:
        build_replay_fixture(row)
    assert "does not contain replay context" in str(exc_info.value)


def test_build_replay_fixture_blocks_fitted_without_bundle():
    """Verify error when fitted artifact decision lacks bundle."""
    from gan_matchmaking.sre.replay import build_replay_fixture, DecisionAuditRow

    row = DecisionAuditRow(
        correlation_id="test-123",
        kind="go",
        risk_level="low",
        risk_prob=0.1,
        confidence=0.9,
        chosen_id="svc-1",
        artifact_version="retention@v1",  # Fitted artifact
        rationale=["test"],
        trace={"input": {"context": {}}},
        created_at=1.0,
    )
    with pytest.raises(DataError) as exc_info:
        build_replay_fixture(row, allow_fitted_artifacts=False)
    assert "cannot export fitted-artifact" in str(exc_info.value)


def test_build_replay_fixture_requires_bundle_for_fitted():
    """Verify error when fitted artifact but no bundle provided."""
    from gan_matchmaking.sre.replay import build_replay_fixture, DecisionAuditRow

    row = DecisionAuditRow(
        correlation_id="test-123",
        kind="go",
        risk_level="low",
        risk_prob=0.1,
        confidence=0.9,
        chosen_id="svc-1",
        artifact_version="retention@v1",
        rationale=["test"],
        trace={"input": {"context": {}}},
        created_at=1.0,
    )
    with pytest.raises(DataError) as exc_info:
        build_replay_fixture(row, allow_fitted_artifacts=True)
    assert "requires a validated artifact bundle" in str(exc_info.value)


def test_validate_artifact_bundle_version_mismatch(tmp_path):
    """Verify error when artifact bundle version doesn't match expected."""
    from gan_matchmaking.sre.replay import validate_artifact_bundle

    artifact_dir = tmp_path / "artifacts"
    _write_fitted_artifacts(artifact_dir)

    with pytest.raises(DataError) as exc_info:
        validate_artifact_bundle(
            artifact_dir,
            "wrong-version@v99",  # Wrong version
        )
    assert "version mismatch" in str(exc_info.value)


def test_validate_artifact_bundle_empty_bundle(tmp_path):
    """Verify error when artifact bundle is empty (no files)."""
    from gan_matchmaking.sre.replay import validate_artifact_bundle

    artifact_dir = tmp_path / "empty"
    artifact_dir.mkdir()

    # Empty directory has no artifacts, so version mismatch is thrown first
    with pytest.raises(DataError) as exc_info:
        validate_artifact_bundle(
            artifact_dir,
            "any@version",
        )
    # Could be version mismatch or empty bundle depending on implementation
    assert "version mismatch" in str(exc_info.value) or "bundle is empty" in str(exc_info.value)


@pytest.mark.skipif(os.name == "nt", reason="secure archive directory handles unavailable")
def test_archive_artifact_bundle_cleans_up_on_failure(tmp_path):
    """Verify partial archive is cleaned up when validation fails."""
    from gan_matchmaking.sre.replay import archive_artifact_bundle

    artifact_dir = tmp_path / "artifacts"
    _write_fitted_artifacts(artifact_dir)

    bad_output = tmp_path / "artifact-bundles" / "failing"

    with pytest.raises(DataError):
        archive_artifact_bundle(
            artifact_dir,
            bad_output,
            "wrong-version",  # This will fail validation
        )

    # Verify cleanup happened
    assert not bad_output.exists()


def test_load_decision_audit_row_invalid_rationale_type(tmp_path):
    """Verify error when rationale_json is not a list."""
    import sqlite3
    from gan_matchmaking.sre.replay import load_decision_audit_row

    db_path = tmp_path / "state.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE decisions (
                correlation_id TEXT PRIMARY KEY,
                kind TEXT, risk_level TEXT, risk_prob REAL, confidence REAL,
                chosen_id TEXT, artifact_version TEXT, rationale_json TEXT,
                trace_json TEXT, created_at REAL
            )
        """)
        conn.execute("""
            INSERT INTO decisions VALUES (
                'test-123', 'go', 'low', 0.1, 0.9, 'svc-1', 'bootstrap',
                '{"not": "a list"}',  -- Rationale must be a list
                '{"input": {"context": {}}}',
                1.0
            )
        """)

    with pytest.raises(DataError) as exc_info:
        load_decision_audit_row(db_path, "test-123")
    assert "rationale_json must be a list" in str(exc_info.value)


def test_load_decision_audit_row_invalid_trace_type(tmp_path):
    """Verify error when trace_json is not an object."""
    import sqlite3
    from gan_matchmaking.sre.replay import load_decision_audit_row

    db_path = tmp_path / "state.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE decisions (
                correlation_id TEXT PRIMARY KEY,
                kind TEXT, risk_level TEXT, risk_prob REAL, confidence REAL,
                chosen_id TEXT, artifact_version TEXT, rationale_json TEXT,
                trace_json TEXT, created_at REAL
            )
        """)
        conn.execute("""
            INSERT INTO decisions VALUES (
                'test-456', 'go', 'low', 0.1, 0.9, 'svc-1', 'bootstrap',
                '["rationale item"]',
                '[1, 2, 3]',  -- Trace must be an object
                1.0
            )
        """)

    with pytest.raises(DataError) as exc_info:
        load_decision_audit_row(db_path, "test-456")
    assert "trace_json must be an object" in str(exc_info.value)


@pytest.mark.skipif(os.name == "nt", reason="secure archive directory handles unavailable")
def test_export_fitted_decision_without_allow_fitted_artifacts():
    """Verify error when fitted decision exported without flag."""
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
            # Missing artifact_directory
        )


@pytest.mark.skipif(os.name == "nt", reason="secure archive directory handles unavailable")
def test_export_fitted_decision_with_artifact_directory(tmp_path):
    """Verify fitted decision export works with artifact_directory."""
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
    fixture = export_replay_fixture(
        db_path,
        "export-corr-1",
        output=out_path,
        allow_fitted_artifacts=True,
        artifact_directory=artifact_dir,
        name="fitted-export",
    )

    assert fixture["requires_artifact_version"] == original.artifact_version
    assert fixture["expected"]["artifact_version"] == original.artifact_version
    assert "artifact_bundle" in fixture


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
