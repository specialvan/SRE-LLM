"""Runtime artifact helpers for trained SRE models.

This module keeps the trained-model metadata and runtime hydration logic
close to the SRE layer so the pipeline can load fitted artifacts without
learning about training internals.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import numpy as np

from ..eomm import RetentionModel
from ..persistence import Observation
from ..survival import CoxModel
from ..types import MatchConfig, Player, Rating
from .domain import ReleaseCandidate, Service


EOMM_FEATURE_NAMES = (
    "win_streak",
    "loss_streak",
    "last_duration",
    "avg_duration",
    "rating_gap",
    "total_sigma",
    "service_mu",
    "candidate_mu",
)


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (set, tuple)):
        return list(value)
    return value


def _stable_version(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, default=_json_safe).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def _build_id() -> str:
    return (
        os.environ.get("GIT_SHA")
        or os.environ.get("BUILD_ID")
        or os.environ.get("CI_COMMIT_SHA")
        or "unknown"
    )


def _config_hash(config: Mapping[str, Any]) -> str:
    return _stable_version({"config": dict(config)})


@dataclass(frozen=True)
class ArtifactMetadata:
    name: str
    version: str
    trained_at: float
    source_window: Mapping[str, Any]
    config_hash: str
    build_id: str
    fitted: bool = True
    fallback: bool = False
    extra: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "trained_at": self.trained_at,
            "source_window": dict(self.source_window),
            "config_hash": self.config_hash,
            "build_id": self.build_id,
            "fitted": self.fitted,
            "fallback": self.fallback,
            "extra": dict(self.extra),
        }


@dataclass(frozen=True)
class RetentionArtifact:
    metadata: ArtifactMetadata
    weights: np.ndarray
    bias: float

    def as_trace(self) -> dict[str, Any]:
        return {
            **self.metadata.as_dict(),
            "weights_shape": list(self.weights.shape),
        }


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


@dataclass(frozen=True)
class RuntimeArtifactBundle:
    retention: Optional[RetentionArtifact] = None
    cox: Optional[CoxArtifact] = None

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

    def as_trace(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "fitted": self.fitted,
            "retention": None if self.retention is None else self.retention.as_trace(),
            "cox": None if self.cox is None else self.cox.as_trace(),
        }


def build_metadata(
    name: str,
    *,
    source_window: Mapping[str, Any],
    config: Mapping[str, Any],
    extra: Optional[Mapping[str, Any]] = None,
    trained_at: Optional[float] = None,
    build_id: Optional[str] = None,
    fitted: bool = True,
    fallback: bool = False,
) -> ArtifactMetadata:
    payload = {
        "name": name,
        "trained_at": trained_at if trained_at is not None else time.time(),
        "source_window": dict(source_window),
        "config_hash": _config_hash(config),
        "build_id": build_id or _build_id(),
        "fitted": fitted,
        "fallback": fallback,
        "extra": dict(extra or {}),
    }
    version = _stable_version(payload)
    return ArtifactMetadata(
        name=name,
        version=version,
        trained_at=float(payload["trained_at"]),
        source_window=dict(source_window),
        config_hash=payload["config_hash"],
        build_id=payload["build_id"],
        fitted=fitted,
        fallback=fallback,
        extra=dict(extra or {}),
    )


def _write_metadata(path: Path, metadata: ArtifactMetadata) -> None:
    path.write_text(json.dumps(metadata.as_dict(), ensure_ascii=False, indent=2),
                    encoding="utf-8")


def _load_metadata(path: Path) -> Optional[ArtifactMetadata]:
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    return ArtifactMetadata(
        name=str(raw.get("name", "unknown")),
        version=str(raw.get("version", "unknown")),
        trained_at=float(raw.get("trained_at", 0.0)),
        source_window=dict(raw.get("source_window", {})),
        config_hash=str(raw.get("config_hash", "unknown")),
        build_id=str(raw.get("build_id", "unknown")),
        fitted=bool(raw.get("fitted", True)),
        fallback=bool(raw.get("fallback", False)),
        extra=dict(raw.get("extra", {})),
    )


def _service_player(service: Service) -> Player:
    mu = 25.0 + 18.0 * (service.mu - 0.5) + 1.5 * float(service.win_streak) - 1.0 * float(service.loss_streak)
    sigma = max(1.0, 5.0 + 10.0 * float(service.sigma) + 0.5 * float(service.loss_streak))
    return Player(
        id=service.id,
        rating=Rating(mu=mu, sigma=sigma),
        win_streak=service.win_streak,
        loss_streak=service.loss_streak,
        total_matches=service.total_releases,
    )


def _candidate_player(candidate: ReleaseCandidate) -> Player:
    mu = 25.0 + 18.0 * (candidate.expected_success - 0.5) - 14.0 * candidate.canary_fraction
    sigma = max(1.0, 4.0 + 20.0 * candidate.canary_fraction + 0.5 * (1.0 - candidate.expected_success))
    return Player(
        id=candidate.id,
        rating=Rating(mu=mu, sigma=sigma),
    )


def build_match_config(service: Service, candidate: ReleaseCandidate) -> MatchConfig:
    """Turn SRE release state into the synthetic teams used by EOMM features."""
    return MatchConfig(team_a=[_service_player(service)], team_b=[_candidate_player(candidate)])


def build_history_vector(
    service: Service,
    recent_observations: Sequence[Observation] | None = None,
    error_budget_remaining: float = 1.0,
) -> list[float]:
    """Build the 4-field EOMM history vector used by the runtime path.

    The training pipeline uses the same shape, but its values come from the
    observation sequence rather than the live service object.
    """
    if recent_observations:
        last_duration = float(recent_observations[-1].duration_seconds)
        avg_duration = float(
            sum(obs.duration_seconds for obs in recent_observations) / len(recent_observations)
        )
    else:
        last_duration = float(service.total_releases)
        avg_duration = float(service.total_releases)
    return [
        float(service.win_streak),
        float(service.loss_streak),
        last_duration,
        avg_duration,
    ]


def save_retention_artifact(
    directory: str | Path,
    model: RetentionModel,
    metadata: ArtifactMetadata,
    *,
    weights_filename: str = "retention_weights.npz",
    metadata_filename: str = "retention_artifact.json",
) -> Path:
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    np.savez(
        path / weights_filename,
        weights=np.asarray(model.weights, dtype=float),
        bias=np.asarray([model.bias], dtype=float),
    )
    _write_metadata(path / metadata_filename, metadata)
    return path / weights_filename


def load_retention_artifact(
    directory: str | Path,
    *,
    weights_filename: str = "retention_weights.npz",
    metadata_filename: str = "retention_artifact.json",
) -> Optional[RetentionArtifact]:
    path = Path(directory)
    weights_path = path / weights_filename
    if not weights_path.exists():
        return None
    metadata = _load_metadata(path / metadata_filename)
    if metadata is None:
        metadata = ArtifactMetadata(
            name="retention",
            version="unversioned",
            trained_at=0.0,
            source_window={},
            config_hash="unknown",
            build_id="unknown",
            fitted=True,
            fallback=False,
            extra={},
        )
    with np.load(weights_path) as payload:
        weights = np.asarray(payload["weights"], dtype=float)
        bias_raw = payload["bias"]
        bias = float(np.asarray(bias_raw, dtype=float).reshape(-1)[0])
    return RetentionArtifact(metadata=metadata, weights=weights, bias=bias)


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
    baseline_t = model._baseline_t if model._baseline_t is not None else np.asarray([], dtype=float)
    baseline_H = model._baseline_H if model._baseline_H is not None else np.asarray([], dtype=float)
    np.savez(
        path / weights_filename,
        beta=np.asarray(model.beta, dtype=float),
        baseline_t=np.asarray(baseline_t, dtype=float),
        baseline_H=np.asarray(baseline_H, dtype=float),
    )
    _write_metadata(path / metadata_filename, metadata)
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
    metadata = _load_metadata(path / metadata_filename)
    if metadata is None:
        metadata = ArtifactMetadata(
            name="cox",
            version="unversioned",
            trained_at=0.0,
            source_window={},
            config_hash="unknown",
            build_id="unknown",
            fitted=True,
            fallback=False,
            extra={},
        )
    with np.load(weights_path) as payload:
        return CoxArtifact(
            metadata=metadata,
            beta=np.asarray(payload["beta"], dtype=float),
            baseline_t=np.asarray(payload["baseline_t"], dtype=float),
            baseline_H=np.asarray(payload["baseline_H"], dtype=float),
        )


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
    return RuntimeArtifactBundle(
        retention=load_retention_artifact(
            path,
            weights_filename=retention_filename,
            metadata_filename=retention_metadata_filename,
        ),
        cox=load_cox_artifact(
            path,
            weights_filename=cox_filename,
            metadata_filename=cox_metadata_filename,
        ),
    )
