"""Public import compatibility for SRE runtime artifacts."""
from __future__ import annotations

import numpy as np

import gan_matchmaking.sre.artifacts as artifacts
from gan_matchmaking.eomm import RetentionModel
from gan_matchmaking.sre.artifacts import (
    EOMM_FEATURE_NAMES,
    build_metadata,
    load_runtime_artifacts,
    save_retention_artifact,
)


EXPECTED_PUBLIC_SYMBOLS = {
    "ArtifactMetadata",
    "build_metadata",
    "EOMM_FEATURE_NAMES",
    "RetentionArtifact",
    "RetentionScalingCompatibility",
    "_rating_scaling_version",
    "build_history_vector",
    "build_match_config",
    "load_retention_artifact",
    "retention_scaling_compatibility",
    "save_retention_artifact",
    "validate_retention_artifact",
    "CoxArtifact",
    "load_cox_artifact",
    "save_cox_artifact",
    "validate_cox_artifact",
    "RuntimeArtifactBundle",
    "load_runtime_artifacts",
}


def test_artifacts_public_surface_is_stable():
    assert set(artifacts.__all__) == EXPECTED_PUBLIC_SYMBOLS
    for symbol in EXPECTED_PUBLIC_SYMBOLS:
        assert hasattr(artifacts, symbol)


def test_runtime_artifacts_do_not_trust_error_kind_without_validation_failure(tmp_path):
    model = RetentionModel()
    model.weights = np.ones(len(EOMM_FEATURE_NAMES), dtype=float)
    model.bias = -0.2
    metadata = build_metadata(
        "retention",
        source_window={"fixture": "public-api"},
        config={"fixture": "public-api", "model": "retention"},
        extra={
            "feature_dim": len(EOMM_FEATURE_NAMES),
            "feature_names": list(EOMM_FEATURE_NAMES),
            "error_kind": "metadata_missing",
        },
        trained_at=1.0,
        build_id="public-api-test",
    )
    save_retention_artifact(tmp_path, model, metadata)

    bundle = load_runtime_artifacts(tmp_path)

    assert bundle.retention is not None
    assert bundle.validation_errors == {}
    assert bundle.as_trace()["error_kinds"] == {}
