"""Train the EOMM :class:`RetentionModel` on pairs of adjacent observations.

Definition: "retention" == a release within the next ``horizon_hours``
that also succeeds.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

import numpy as np

from ..core.errors import DataError
from ..eomm import RetentionModel, _features as _eomm_features
from ..persistence import Observation, PipelineStore
from ..sre.artifacts import (
    EOMM_FEATURE_NAMES,
    _rating_scaling_version,
    build_history_vector,
    build_match_config,
    build_metadata,
    save_retention_artifact,
)
from ..sre.domain import ReleaseCandidate
from ..sre.features import empirical_service


@dataclass
class RetentionTrainingReport:
    n_samples: int = 0
    positive_rate: float = 0.0
    loss_start: float = 0.0
    loss_end: float = 0.0
    output_path: Optional[str] = None
    artifact_version: Optional[str] = None
    metadata_path: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "n_samples": self.n_samples,
            "positive_rate": self.positive_rate,
            "loss_start": self.loss_start,
            "loss_end": self.loss_end,
            "output_path": self.output_path,
            "artifact_version": self.artifact_version,
            "metadata_path": self.metadata_path,
        }


def _build_dataset(observations: Iterable[Observation],
                    horizon_seconds: float):
    """Build (histories, cfgs, retained) triples.

    For each observation we look at the following one *of the same service*.
    ``retained = 1`` iff that next observation lands within ``horizon_seconds``
    and succeeds.
    """
    by_svc: dict[str, List[Observation]] = {}
    for o in sorted(observations, key=lambda o: (o.service_id, o.timestamp)):
        by_svc.setdefault(o.service_id, []).append(o)

    histories, cfgs, retained = [], [], []
    for sid, seq in by_svc.items():
        loss_streak = 0; win_streak = 0; successes = 0
        for i, cur in enumerate(seq[:-1]):
            nxt = seq[i + 1]
            next_win_streak = win_streak + 1 if cur.success else 0
            next_loss_streak = 0 if cur.success else loss_streak + 1
            next_successes = successes + (1 if cur.success else 0)
            svc = empirical_service(
                sid,
                win_streak=next_win_streak,
                loss_streak=next_loss_streak,
                successes=next_successes,
                total_observations=i + 1,
            )
            recent = seq[max(0, i - 7): i + 1]
            hist = build_history_vector(svc, recent_observations=recent)
            raw_features = cur.features or {}
            canary_fraction = float(raw_features.get("canary_fraction", 0.1))
            expected_success = float(raw_features.get("expected_success", svc.mu))
            cfg_stub = ReleaseCandidate(
                id=f"stub-{i}", service_id=sid, strategy="canary",
                canary_fraction=max(0.0, min(1.0, canary_fraction)),
                rollback_budget_seconds=60,
                expected_success=max(1e-6, min(1.0 - 1e-6, expected_success)),
            )
            histories.append(hist)
            cfgs.append(build_match_config(svc, cfg_stub))
            label = int(
                nxt.timestamp - cur.timestamp <= horizon_seconds and nxt.success
            )
            retained.append(label)
            # Move the rolling state to after ``cur``.
            successes = next_successes
            if cur.success:
                win_streak = next_win_streak; loss_streak = 0
            else:
                loss_streak = next_loss_streak; win_streak = 0
    return histories, cfgs, retained


def train_retention_from_store(
    store: PipelineStore,
    horizon_hours: float = 24.0,
    output_dir: str | Path = "training_artifacts",
    min_samples: int = 10,
    lr: float = 0.005,
    iters: int = 1000,
) -> RetentionTrainingReport:
    observations = list(store.observations.observations())
    if not observations:
        raise DataError("no observations available")
    horizon = horizon_hours * 3600.0
    histories, cfg_lists, retained = _build_dataset(observations, horizon)
    if len(histories) < min_samples:
        raise DataError(
            f"too few (history, next) pairs (got {len(histories)}, need >= {min_samples})")

    model = RetentionModel()
    model.fit(histories, cfg_lists, retained, lr=lr, iters=iters)

    # Compute a loss delta as a report signal.
    X0 = np.stack([_eomm_features(h, c) for h, c in zip(histories, cfg_lists)])
    y = np.asarray(retained, dtype=float)
    def _loss(weights, bias):
        z = np.clip(X0 @ weights + bias, -500, 500)
        p = 1.0 / (1.0 + np.exp(-z))
        p = np.clip(p, 1e-6, 1 - 1e-6)
        return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())

    loss_start = _loss(np.zeros_like(model.weights), 0.0)
    loss_end = _loss(model.weights, model.bias)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata = build_metadata(
        "retention",
        source_window={
            "n_observations": len(observations),
            "n_samples": len(histories),
            "positive_rate": float(y.mean()),
            "horizon_hours": horizon_hours,
        },
        config={
            "horizon_hours": horizon_hours,
            "min_samples": min_samples,
            "lr": lr,
            "iters": iters,
        },
        extra={"feature_dim": int(X0.shape[1]),
               "feature_names": list(EOMM_FEATURE_NAMES),
               "rating_scaling_version": _rating_scaling_version()},
    )
    np_path = save_retention_artifact(
        output_dir,
        model,
        metadata,
        weights_filename="retention_weights.npz",
        metadata_filename="retention_artifact.json",
    )

    report = RetentionTrainingReport(
        n_samples=len(histories),
        positive_rate=float(y.mean()),
        loss_start=loss_start,
        loss_end=loss_end,
        output_path=str(np_path),
        artifact_version=metadata.version,
        metadata_path=str(output_dir / "retention_artifact.json"),
    )
    (output_dir / "retention_report.json").write_text(
        json.dumps(report.as_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report
