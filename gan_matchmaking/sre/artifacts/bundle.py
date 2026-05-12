"""Runtime artifact bundle and top-level loader."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from .cox import CoxArtifact, load_cox_artifact, validate_cox_artifact
from .retention import (
    RetentionArtifact,
    load_retention_artifact,
    validate_retention_artifact,
)


@dataclass(frozen=True)
class RuntimeArtifactBundle:
    retention: Optional[RetentionArtifact] = None
    cox: Optional[CoxArtifact] = None
    validation_errors: Mapping[str, Sequence[str]] = field(default_factory=dict)
    rating_scaling_status: str = "match"  # "match" | "mismatch" | "unknown"

    @property
    def version(self) -> str:
        parts: list[str] = []
        if self.retention is not None:
            parts.append(f"retention@{self.retention.metadata.version}")
        if self.cox is not None:
            parts.append(f"cox@{self.cox.metadata.version}")
        return "+".join(parts) if parts else "bootstrap"

    @property
    def fitted(self) -> bool:
        return self.retention is not None or self.cox is not None

    def with_scaling_status(self, status: str) -> "RuntimeArtifactBundle":
        """Return a copy with ``rating_scaling_status`` updated.

        Used by :meth:`SelfIterationPipeline._hydrate_runtime_artifacts`
        when a retention artifact's rating scaling version does not match
        the runtime's current constants. A bundle with status
        ``"mismatch"`` drops the retention artifact so the pipeline
        downgrades to the bootstrap path.
        """
        if status not in {"match", "mismatch", "unknown"}:
            raise ValueError(f"unknown rating_scaling_status {status!r}")
        if status == "mismatch":
            return replace(self, retention=None, rating_scaling_status=status)
        return replace(self, rating_scaling_status=status)

    def as_trace(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "fitted": self.fitted,
            "retention": None if self.retention is None else self.retention.as_trace(),
            "cox": None if self.cox is None else self.cox.as_trace(),
            "validation_errors": {
                key: list(errors)
                for key, errors in self.validation_errors.items()
            },
            "rating_scaling_status": self.rating_scaling_status,
        }


def load_runtime_artifacts(
    directory: str | Path | None,
    *,
    retention_filename: str = "retention_weights.npz",
    retention_metadata_filename: str = "retention_artifact.json",
    cox_filename: str = "cox_beta.npz",
    cox_metadata_filename: str = "cox_artifact.json",
) -> RuntimeArtifactBundle:
    if directory is None:
        return RuntimeArtifactBundle()
    path = Path(directory)
    retention = load_retention_artifact(
        path,
        weights_filename=retention_filename,
        metadata_filename=retention_metadata_filename,
    )
    cox = load_cox_artifact(
        path,
        weights_filename=cox_filename,
        metadata_filename=cox_metadata_filename,
    )
    validation_errors: dict[str, list[str]] = {}
    if retention is not None:
        errors = validate_retention_artifact(retention)
        if errors:
            validation_errors["retention"] = errors
            retention = None
    if cox is not None:
        errors = validate_cox_artifact(cox)
        if errors:
            validation_errors["cox"] = errors
            cox = None
    return RuntimeArtifactBundle(
        retention=retention,
        cox=cox,
        validation_errors=validation_errors,
    )
