"""Retention artifact persistence and EOMM feature construction.

The ``_RATING_*`` constants are part of the trained artifact contract:
``_rating_scaling_version`` hashes them so runtime can reject retention
artifacts trained against a different feature scale.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Sequence

import numpy as np

from ...eomm import RetentionModel
from ...persistence import Observation
from ...types import MatchConfig, Player, Rating
from ..domain import ReleaseCandidate, Service
from .metadata import (
    ArtifactMetadata,
    declared_feature_dim,
    declared_feature_names,
    load_metadata,
    write_metadata,
)


EOMM_FEATURE_NAMES = ("win_streak", "loss_streak", "last_duration",
                      "avg_duration", "rating_gap", "total_sigma",
                      "service_mu", "candidate_mu")

# Elo-style mapping from SRE release state to synthetic EOMM players.
# Changing any value invalidates previously fitted retention artifacts
# unless metadata.rating_scaling_version is updated and accepted.
_RATING_MU_BASE = 25.0                         # Elo pivot
_RATING_MU_SLOPE = 18.0                        # service.mu/candidate prior
_RATING_MU_WIN_GAIN = 1.5                      # consecutive-win bonus
_RATING_MU_LOSS_GAIN = -1.0                    # consecutive-loss penalty
_RATING_SIGMA_FLOOR = 1.0                      # minimum Player.sigma
_RATING_SIGMA_BASE = 5.0                       # service sigma baseline
_RATING_SIGMA_SIGMA_GAIN = 10.0                # service.sigma multiplier
_RATING_SIGMA_LOSS_STREAK_GAIN = 0.5           # loss-streak uncertainty
_RATING_CANARY_PENALTY = -14.0                 # canary fraction mu penalty
_RATING_CANARY_SIGMA_GAIN = 20.0               # canary fraction sigma gain
_RATING_CANDIDATE_SIGMA_BASE = 4.0             # candidate sigma baseline
_RATING_CANDIDATE_SUCCESS_SIGMA_GAIN = 0.5     # (1 - expected_success) gain


def _rating_scaling_payload() -> dict[str, float]:
    return {
        "mu_base": _RATING_MU_BASE,
        "mu_slope": _RATING_MU_SLOPE,
        "mu_win_gain": _RATING_MU_WIN_GAIN,
        "mu_loss_gain": _RATING_MU_LOSS_GAIN,
        "sigma_floor": _RATING_SIGMA_FLOOR,
        "sigma_base": _RATING_SIGMA_BASE,
        "sigma_sigma_gain": _RATING_SIGMA_SIGMA_GAIN,
        "sigma_loss_streak_gain": _RATING_SIGMA_LOSS_STREAK_GAIN,
        "canary_penalty": _RATING_CANARY_PENALTY,
        "canary_sigma_gain": _RATING_CANARY_SIGMA_GAIN,
        "candidate_sigma_base": _RATING_CANDIDATE_SIGMA_BASE,
        "candidate_success_sigma_gain": _RATING_CANDIDATE_SUCCESS_SIGMA_GAIN,
    }


def _rating_scaling_version() -> str:
    """Stable 12-hex hash that bumps when any ``_RATING_*`` value changes."""
    raw = json.dumps(_rating_scaling_payload(), sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:12]


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


def _service_player(service: Service) -> Player:
    mu = (_RATING_MU_BASE + _RATING_MU_SLOPE * (service.mu - 0.5)
          + _RATING_MU_WIN_GAIN * float(service.win_streak)
          + _RATING_MU_LOSS_GAIN * float(service.loss_streak))
    sigma = max(_RATING_SIGMA_FLOOR,
                _RATING_SIGMA_BASE
                + _RATING_SIGMA_SIGMA_GAIN * float(service.sigma)
                + _RATING_SIGMA_LOSS_STREAK_GAIN * float(service.loss_streak))
    return Player(
        id=service.id,
        rating=Rating(mu=mu, sigma=sigma),
        win_streak=service.win_streak,
        loss_streak=service.loss_streak,
        total_matches=service.total_releases,
    )


def _candidate_player(candidate: ReleaseCandidate) -> Player:
    mu = (_RATING_MU_BASE
          + _RATING_MU_SLOPE * (candidate.expected_success - 0.5)
          + _RATING_CANARY_PENALTY * candidate.canary_fraction)
    sigma = max(_RATING_SIGMA_FLOOR,
                _RATING_CANDIDATE_SIGMA_BASE
                + _RATING_CANARY_SIGMA_GAIN * candidate.canary_fraction
                + _RATING_CANDIDATE_SUCCESS_SIGMA_GAIN
                * (1.0 - candidate.expected_success))
    return Player(id=candidate.id, rating=Rating(mu=mu, sigma=sigma))


def build_match_config(service: Service, candidate: ReleaseCandidate) -> MatchConfig:
    """Turn SRE release state into the synthetic teams used by EOMM features."""
    return MatchConfig(
        team_a=[_service_player(service)],
        team_b=[_candidate_player(candidate)],
    )


def build_history_vector(
    service: Service,
    recent_observations: Sequence[Observation] | None = None,
    error_budget_remaining: float = 1.0,
) -> list[float]:
    """Build the 4-field EOMM history vector used by the runtime path."""
    if recent_observations:
        last_duration = float(recent_observations[-1].duration_seconds)
        avg_duration = float(
            sum(obs.duration_seconds for obs in recent_observations)
            / len(recent_observations)
        )
    else:
        last_duration = float(service.total_releases)
        avg_duration = float(service.total_releases)
    return [float(service.win_streak), float(service.loss_streak),
            last_duration, avg_duration]


def validate_retention_artifact(artifact: RetentionArtifact) -> list[str]:
    """Return manifest/shape issues that make a retention artifact unsafe."""
    errors: list[str] = []
    if artifact.metadata.name != "retention":
        errors.append(f"name={artifact.metadata.name!r} expected 'retention'")
    if artifact.weights.ndim != 1:
        errors.append(f"weights.ndim={artifact.weights.ndim} expected 1")
    if artifact.weights.shape[0] != len(EOMM_FEATURE_NAMES):
        errors.append(f"weights_dim={artifact.weights.shape[0]} expected "
                      f"{len(EOMM_FEATURE_NAMES)}")
    declared_dim = declared_feature_dim(artifact.metadata)
    if declared_dim is None:
        errors.append("manifest.extra.feature_dim missing")
    elif declared_dim != artifact.weights.shape[0]:
        errors.append(f"manifest.feature_dim={declared_dim} != "
                      f"weights_dim={artifact.weights.shape[0]}")
    declared_names = declared_feature_names(artifact.metadata)
    if declared_names is None:
        errors.append("manifest.extra.feature_names missing")
    elif declared_names != list(EOMM_FEATURE_NAMES):
        errors.append("manifest.extra.feature_names mismatch")
    if not np.isfinite(artifact.weights).all() or not np.isfinite(artifact.bias):
        errors.append("weights/bias contain non-finite values")
    return errors


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
    write_metadata(path / metadata_filename, metadata)
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
    metadata = load_metadata(path / metadata_filename, default_name="retention")
    with np.load(weights_path) as payload:
        weights = np.asarray(payload["weights"], dtype=float)
        bias_raw = payload["bias"]
        bias = float(np.asarray(bias_raw, dtype=float).reshape(-1)[0])
    return RetentionArtifact(metadata=metadata, weights=weights, bias=bias)
