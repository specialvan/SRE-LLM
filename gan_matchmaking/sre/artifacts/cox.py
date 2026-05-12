"""Cox survival artifact persistence and validation."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np

from ...survival import CoxModel
from ..features import RISK_FEATURE_NAMES
from .metadata import (
    ArtifactMetadata,
    declared_feature_dim,
    declared_feature_names,
    load_metadata,
    write_metadata,
)


@dataclass(frozen=True)
class CoxArtifact:
    metadata: ArtifactMetadata
    beta: np.ndarray
    baseline_t: np.ndarray
    baseline_H: np.ndarray

    def as_trace(self) -> dict[str, Any]:
        return {
            **self.metadata.as_dict(),
            "beta_shape": list(self.beta.shape),
            "baseline_points": int(self.baseline_t.shape[0]),
        }


def validate_cox_artifact(artifact: CoxArtifact) -> list[str]:
    """Return manifest/shape issues that make a Cox artifact unsafe."""
    errors: list[str] = []
    if artifact.metadata.name != "cox":
        errors.append(f"name={artifact.metadata.name!r} expected 'cox'")
    if artifact.beta.ndim != 1:
        errors.append(f"beta.ndim={artifact.beta.ndim} expected 1")
    if artifact.beta.shape[0] != len(RISK_FEATURE_NAMES):
        errors.append(
            f"beta_dim={artifact.beta.shape[0]} expected {len(RISK_FEATURE_NAMES)}"
        )
    declared_dim = declared_feature_dim(artifact.metadata)
    if declared_dim is None:
        errors.append("manifest.extra.feature_dim missing")
    elif declared_dim != artifact.beta.shape[0]:
        errors.append(
            f"manifest.feature_dim={declared_dim} != beta_dim={artifact.beta.shape[0]}"
        )
    declared_names = declared_feature_names(artifact.metadata)
    if declared_names is None:
        errors.append("manifest.extra.feature_names missing")
    elif declared_names != list(RISK_FEATURE_NAMES):
        errors.append("manifest.extra.feature_names mismatch")
    if artifact.baseline_t.ndim != 1 or artifact.baseline_H.ndim != 1:
        errors.append("baseline arrays must be 1-dimensional")
    elif artifact.baseline_t.shape[0] != artifact.baseline_H.shape[0]:
        errors.append(
            f"baseline length mismatch: t={artifact.baseline_t.shape[0]} "
            f"H={artifact.baseline_H.shape[0]}"
        )
    elif artifact.baseline_t.shape[0] <= 0:
        errors.append("baseline arrays are empty")
    if (
        not np.isfinite(artifact.beta).all()
        or not np.isfinite(artifact.baseline_t).all()
        or not np.isfinite(artifact.baseline_H).all()
    ):
        errors.append("beta/baseline contain non-finite values")
    return errors


def save_cox_artifact(
    directory: str | Path,
    model: CoxModel,
    metadata: ArtifactMetadata,
    *,
    weights_filename: str = "cox_beta.npz",
    metadata_filename: str = "cox_artifact.json",
) -> Path:
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    baseline_t = (
        model._baseline_t
        if model._baseline_t is not None
        else np.asarray([], dtype=float)
    )
    baseline_H = (
        model._baseline_H
        if model._baseline_H is not None
        else np.asarray([], dtype=float)
    )
    np.savez(
        path / weights_filename,
        beta=np.asarray(model.beta, dtype=float),
        baseline_t=np.asarray(baseline_t, dtype=float),
        baseline_H=np.asarray(baseline_H, dtype=float),
    )
    write_metadata(path / metadata_filename, metadata)
    return path / weights_filename


def load_cox_artifact(
    directory: str | Path,
    *,
    weights_filename: str = "cox_beta.npz",
    metadata_filename: str = "cox_artifact.json",
) -> Optional[CoxArtifact]:
    path = Path(directory)
    weights_path = path / weights_filename
    if not weights_path.exists():
        return None
    metadata = load_metadata(path / metadata_filename, default_name="cox")
    with np.load(weights_path) as payload:
        return CoxArtifact(
            metadata=metadata,
            beta=np.asarray(payload["beta"], dtype=float),
            baseline_t=np.asarray(payload["baseline_t"], dtype=float),
            baseline_H=np.asarray(payload["baseline_H"], dtype=float),
        )
