"""Runtime artifact helpers for trained SRE models.

This package hosts the artifact metadata, retention and Cox persistence
helpers, and the runtime bundle that the self-iteration pipeline loads
during startup. Historically these lived in a single 488-line module;
they were split (F-006) into focused files while keeping the public
import surface unchanged.

All re-exports here intentionally mirror the previous single-file API so
external code using ``from gan_matchmaking.sre.artifacts import X``
continues to work without modification.
"""
from __future__ import annotations

from .metadata import ArtifactMetadata, build_metadata
from .retention import (
    EOMM_FEATURE_NAMES,
    RetentionArtifact,
    RetentionScalingCompatibility,
    _rating_scaling_version,
    build_history_vector,
    build_match_config,
    load_retention_artifact,
    retention_scaling_compatibility,
    save_retention_artifact,
    validate_retention_artifact,
)
from .cox import (
    CoxArtifact,
    load_cox_artifact,
    save_cox_artifact,
    validate_cox_artifact,
)
from .bundle import RuntimeArtifactBundle, load_runtime_artifacts

__all__ = [
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
]
