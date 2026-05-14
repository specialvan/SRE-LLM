"""Golden replay corpus for SRE decisions."""
from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path, PurePosixPath, PureWindowsPath

import numpy as np
import pytest

from gan_matchmaking.core import MetricsRegistry, load_config
from gan_matchmaking.eomm import RetentionModel
from gan_matchmaking.sre import ReleaseContext, SelfIterationPipeline
from gan_matchmaking.sre.artifacts import (
    EOMM_FEATURE_NAMES,
    _rating_scaling_version,
    build_metadata,
    load_runtime_artifacts,
    save_cox_artifact,
    save_retention_artifact,
)
from gan_matchmaking.sre.circuit import CircuitBreaker
from gan_matchmaking.sre.features import RISK_FEATURE_NAMES
from gan_matchmaking.survival import CoxModel


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "replay"


def _fixture_paths() -> list[Path]:
    return sorted(FIXTURE_DIR.glob("*.json"))


def _write_artifacts(spec: dict, directory: Path, fixture_name: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    if "retention" in spec:
        raw = spec["retention"]
        model = RetentionModel(
            weights=np.asarray(raw["weights"], dtype=float),
            bias=float(raw["bias"]),
        )
        extra: dict[str, object] = {
            "feature_dim": len(EOMM_FEATURE_NAMES),
            "feature_names": list(EOMM_FEATURE_NAMES),
        }
        if "rating_scaling_version" in raw:
            extra = {**extra, "rating_scaling_version": raw["rating_scaling_version"]}
        metadata = build_metadata(
            "retention",
            source_window={"fixture": fixture_name},
            config={"fixture": fixture_name, "model": "retention"},
            extra=extra,
            trained_at=1.0,
            build_id="replay-fixture",
        )
        save_retention_artifact(directory, model, metadata)
    if "cox" in spec:
        raw = spec["cox"]
        model = CoxModel(
            beta=np.asarray(raw["beta"], dtype=float),
            _baseline_t=np.asarray(raw["baseline_t"], dtype=float),
            _baseline_H=np.asarray(raw["baseline_H"], dtype=float),
        )
        metadata = build_metadata(
            "cox",
            source_window={"fixture": fixture_name},
            config={"fixture": fixture_name, "model": "cox"},
            extra={"feature_dim": len(RISK_FEATURE_NAMES),
                   "feature_names": list(RISK_FEATURE_NAMES)},
            trained_at=1.0,
            build_id="replay-fixture",
        )
        save_cox_artifact(directory, model, metadata)


def _assert_fixture_config_safe(fixture_path: Path, raw: dict) -> None:
    config = raw.get("config", {})
    if not isinstance(config, Mapping):
        return
    artifacts = config.get("artifacts", {})
    if not isinstance(artifacts, Mapping):
        return
    assert "directory" not in artifacts, (
        f"{fixture_path.name} must not set config.artifacts.directory; "
        "use top-level artifacts or artifact_bundle"
    )


def _assert_artifact_bundle_directory_safe(fixture_path: Path, directory: Path) -> None:
    for child in directory.iterdir():
        assert not child.is_symlink(), (
            f"{fixture_path.name} artifact bundle directory must not contain symlinks: {child.name}"
        )


def _resolve_artifact_bundle_path(fixture_path: Path, raw_path: object) -> Path:
    bundle_path = str(raw_path)
    posix_path = PurePosixPath(bundle_path)
    windows_path = PureWindowsPath(bundle_path)
    assert bundle_path, f"{fixture_path.name} artifact_bundle.path must be non-empty"
    assert not posix_path.is_absolute(), (
        f"{fixture_path.name} artifact_bundle.path must be relative"
    )
    assert not windows_path.is_absolute(), (
        f"{fixture_path.name} artifact_bundle.path must be relative"
    )

    resolved = (fixture_path.parent / bundle_path).resolve()
    fixture_root = FIXTURE_DIR.resolve()
    try:
        resolved.relative_to(fixture_root)
    except ValueError as exc:
        raise AssertionError(
            f"{fixture_path.name} artifact_bundle.path must stay under {fixture_root}"
        ) from exc
    assert resolved.exists(), f"{fixture_path.name} artifact bundle path missing: {resolved}"
    assert resolved.is_dir(), f"{fixture_path.name} artifact bundle path must be a directory"
    _assert_artifact_bundle_directory_safe(fixture_path, resolved)
    return resolved


def _get_path(payload: dict, path: str):
    current = payload
    for part in path.split("."):
        if isinstance(current, list):
            current = current[int(part)]
        else:
            current = current[part]
    return current


@pytest.mark.parametrize("fixture_path", _fixture_paths(), ids=lambda p: p.stem)
def test_golden_replay_corpus(fixture_path, tmp_path):
    raw = json.loads(fixture_path.read_text(encoding="utf-8"))
    _assert_fixture_config_safe(fixture_path, raw)
    config_raw = dict(raw.get("config", {}))
    if raw.get("artifacts"):
        artifact_dir = tmp_path / raw["name"] / "artifacts"
        _write_artifacts(raw["artifacts"], artifact_dir, raw["name"])
        config_raw["artifacts"] = {"directory": str(artifact_dir)}
    elif raw.get("artifact_bundle"):
        artifact_bundle = raw["artifact_bundle"]
        artifact_path = _resolve_artifact_bundle_path(
            fixture_path,
            artifact_bundle["path"],
        )
        config_raw["artifacts"] = {
            **dict(config_raw.get("artifacts", {})),
            "directory": str(artifact_path),
        }

    cfg = load_config(config_raw)
    breaker = None
    if raw.get("circuit_breaker") == "open":
        breaker = CircuitBreaker(failure_threshold=1, recovery_seconds=3600.0)
        breaker.record_failure()
    shadow_mode = raw.get("shadow_mode")
    pipeline = SelfIterationPipeline(
        config=cfg,
        metrics=MetricsRegistry(),
        circuit_breaker=breaker,
        shadow_mode=shadow_mode,
    )
    decision = pipeline.decide(ReleaseContext.from_dict(raw["context"]))
    payload = decision.to_dict()
    expected = raw["expected"]

    assert payload["kind"] == expected["kind"]
    assert payload["chosen_id"] == expected["chosen_id"]
    assert payload["risk_level"] == expected["risk_level"]
    if expected["artifact_version"] == "bootstrap":
        assert payload["artifact_version"] == "bootstrap"
    else:
        assert payload["artifact_version"] != "bootstrap"
        assert payload["trace"]["artifacts"]["fitted"] is True
    if raw.get("requires_artifact_version"):
        assert payload["artifact_version"] == raw["requires_artifact_version"]

    if "eomm_source" in expected:
        assert payload["trace"]["stages"]["eomm"]["source"] == expected["eomm_source"]

    for needle in expected.get("rationale_contains", []):
        assert any(needle in item for item in payload["rationale"])

    for path, value in expected.get("trace_values", {}).items():
        assert _get_path(payload["trace"], path) == value

    for path in expected.get("trace_list_nonempty", []):
        value = _get_path(payload["trace"], path)
        assert isinstance(value, list) and value, (
            f"{fixture_path.name} expected non-empty trace list at {path!r}"
        )


_ALLOWED_FIXTURE_KINDS = {"go", "canary", "hold", "rollback", "escalate"}


def test_fixture_naming_matches_convention():
    """R-821/R-822: filenames match expected.kind and optional fixture name."""
    fixtures = sorted(Path("tests/fixtures/replay").glob("*.json"))
    assert fixtures, "expected at least one replay fixture"
    for path in fixtures:
        raw = json.loads(path.read_text(encoding="utf-8"))
        expected_kind = raw["expected"]["kind"]
        assert expected_kind in _ALLOWED_FIXTURE_KINDS
        assert path.stem.endswith(f"_{expected_kind}"), (
            f"{path.name} must end with _{expected_kind} from expected.kind"
        )
        if "name" in raw:
            assert raw["name"] == path.stem


def test_fixture_config_rejects_direct_artifact_directory(tmp_path):
    fixture_root = tmp_path / "fixtures" / "replay"
    fixture_root.mkdir(parents=True)
    fixture_path = fixture_root / "sample_fixture.json"
    fixture_path.write_text("{}", encoding="utf-8")

    with pytest.raises(AssertionError):
        _assert_fixture_config_safe(
            fixture_path,
            {"config": {"artifacts": {"directory": "C:/tmp/outside"}}},
        )


def test_resolve_artifact_bundle_path_accepts_relative_directory(tmp_path):
    fixture_root = tmp_path / "fixtures" / "replay"
    fixture_root.mkdir(parents=True)
    bundle_dir = fixture_root / "artifact-bundles" / "export-corr-1"
    bundle_dir.mkdir(parents=True)
    fixture_path = fixture_root / "sample_fixture.json"
    fixture_path.write_text("{}", encoding="utf-8")

    original_root = globals()["FIXTURE_DIR"]
    globals()["FIXTURE_DIR"] = fixture_root
    try:
        resolved = _resolve_artifact_bundle_path(
            fixture_path,
            "artifact-bundles/export-corr-1",
        )
    finally:
        globals()["FIXTURE_DIR"] = original_root

    assert resolved == bundle_dir.resolve()


@pytest.mark.parametrize(
    "raw_path",
    [
        "/tmp/export-corr-1",
        "C:/tmp/export-corr-1",
        "../outside/export-corr-1",
        "artifact-bundles/../../outside",
    ],
)
def test_resolve_artifact_bundle_path_rejects_absolute_or_escape(tmp_path, raw_path):
    fixture_root = tmp_path / "fixtures" / "replay"
    fixture_root.mkdir(parents=True)
    fixture_path = fixture_root / "sample_fixture.json"
    fixture_path.write_text("{}", encoding="utf-8")

    original_root = globals()["FIXTURE_DIR"]
    globals()["FIXTURE_DIR"] = fixture_root
    try:
        with pytest.raises(AssertionError):
            _resolve_artifact_bundle_path(fixture_path, raw_path)
    finally:
        globals()["FIXTURE_DIR"] = original_root


def test_artifact_bundle_directory_rejects_symlink_entries(tmp_path):
    fixture_root = tmp_path / "fixtures" / "replay"
    fixture_root.mkdir(parents=True)
    bundle_dir = fixture_root / "artifact-bundles" / "export-corr-1"
    bundle_dir.mkdir(parents=True)
    fixture_path = fixture_root / "sample_fixture.json"
    fixture_path.write_text("{}", encoding="utf-8")
    target = fixture_root / "outside-secret.txt"
    target.write_text("do-not-follow", encoding="utf-8")
    link_path = bundle_dir / "retention_artifact.json"
    try:
        os.symlink(target, link_path)
    except (AttributeError, NotImplementedError, OSError):
        pytest.skip("symlink unavailable")

    original_root = globals()["FIXTURE_DIR"]
    globals()["FIXTURE_DIR"] = fixture_root
    try:
        with pytest.raises(AssertionError):
            _resolve_artifact_bundle_path(
                fixture_path,
                "artifact-bundles/export-corr-1",
            )
    finally:
        globals()["FIXTURE_DIR"] = original_root


def _modern_retention_fixture_paths() -> list[Path]:
    paths: list[Path] = []
    for path in _fixture_paths():
        raw = json.loads(path.read_text(encoding="utf-8"))
        if "retention" not in raw.get("artifacts", {}):
            continue
        if raw.get("expected", {}).get("artifact_version") == "bootstrap":
            continue
        if path.stem.startswith("legacy_") or "_legacy_" in path.stem:
            continue
        paths.append(path)
    return paths


def test_modern_artifact_fixture_has_scaling_version():
    """PR-B: modern fitted replay fixtures declare current rating scaling."""
    fixtures = _modern_retention_fixture_paths()
    assert fixtures, "expected at least one modern retention artifact fixture"
    for path in fixtures:
        raw = json.loads(path.read_text(encoding="utf-8"))
        retention = raw["artifacts"]["retention"]
        assert retention.get("rating_scaling_version") == _rating_scaling_version(), (
            f"{path.name} must declare current rating_scaling_version"
        )


def test_modern_artifact_replay_reports_scaling_match():
    """PR-B: modern fitted replay fixtures assert scaling match in golden trace."""
    fixtures = _modern_retention_fixture_paths()
    assert fixtures, "expected at least one modern retention artifact fixture"
    for path in fixtures:
        raw = json.loads(path.read_text(encoding="utf-8"))
        trace_values = raw["expected"].get("trace_values", {})
        assert trace_values.get("artifacts.rating_scaling_status") == "match", (
            f"{path.name} must assert artifacts.rating_scaling_status == 'match'"
        )


def test_inline_artifact_writer_persists_scaling_version(tmp_path):
    """PR-B: inline replay artifact writer preserves rating scaling metadata."""
    fixture_path = FIXTURE_DIR / "artifact_canary.json"
    raw = json.loads(fixture_path.read_text(encoding="utf-8"))

    _write_artifacts(raw["artifacts"], tmp_path, raw["name"])

    bundle = load_runtime_artifacts(tmp_path)
    assert bundle.retention is not None
    assert (
        bundle.retention.metadata.extra.get("rating_scaling_version")
        == _rating_scaling_version()
    )


def test_legacy_artifact_fixture_is_explicitly_named():
    """PR-B: unknown rating-scaling fixtures must be visibly legacy fixtures."""
    for path in _fixture_paths():
        raw = json.loads(path.read_text(encoding="utf-8"))
        trace_values = raw.get("expected", {}).get("trace_values", {})
        if trace_values.get("artifacts.rating_scaling_status") != "unknown":
            continue

        assert path.stem.startswith("legacy_") or "_legacy_" in path.stem, (
            f"{path.name} preserves unknown scaling and must be legacy-named"
        )


def test_shadow_mode_fixtures_lock_trace_values():
    """Replay fixtures using top-level shadow_mode must lock matching trace fields."""
    for path in _fixture_paths():
        raw = json.loads(path.read_text(encoding="utf-8"))
        shadow_mode = raw.get("shadow_mode")
        if shadow_mode is None:
            continue

        trace_values = raw.get("expected", {}).get("trace_values", {})
        assert trace_values.get("shadow_mode") == shadow_mode, (
            f"{path.name} must assert expected.trace_values.shadow_mode == {shadow_mode!r}"
        )
        if shadow_mode == "shadow":
            assert "shadow_suppressed_kind" in trace_values, (
                f"{path.name} must assert expected.trace_values.shadow_suppressed_kind"
            )


def test_fixture_trace_list_nonempty_paths_exist():
    """Fixtures may require specific trace list paths to be present and non-empty."""
    for path in _fixture_paths():
        raw = json.loads(path.read_text(encoding="utf-8"))
        expected = raw.get("expected", {})
        list_paths = expected.get("trace_list_nonempty", [])
        for trace_path in list_paths:
            assert isinstance(trace_path, str) and trace_path, (
                f"{path.name} has invalid trace_list_nonempty entry {trace_path!r}"
            )
