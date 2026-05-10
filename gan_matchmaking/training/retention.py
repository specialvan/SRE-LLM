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
from ..sre.artifacts import build_metadata, save_retention_artifact
from ..sre.domain import ReleaseCandidate, ReleaseContext, Service


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
        loss_streak = 0; win_streak = 0; avg_dur = 0.0
        for i, cur in enumerate(seq[:-1]):
            nxt = seq[i + 1]
            hist = [float(win_streak), float(loss_streak),
                    float(cur.duration_seconds), float(avg_dur)]
            cfg_stub = ReleaseCandidate(
                id=f"stub-{i}", service_id=sid, strategy="canary",
                canary_fraction=0.1, rollback_budget_seconds=60,
                expected_success=0.95,
            )
            svc = Service(id=sid)
            ctx = ReleaseContext(service=svc, candidates=[cfg_stub])
            histories.append(hist)
            cfgs.append(ctx.candidates)  # list of one.
            label = int(
                nxt.timestamp - cur.timestamp <= horizon_seconds and nxt.success
            )
            retained.append(label)
            # Update rolling streaks for the *next* step.
            avg_dur = 0.5 * avg_dur + 0.5 * float(cur.duration_seconds)
            if cur.success:
                win_streak += 1; loss_streak = 0
            else:
                loss_streak += 1; win_streak = 0
    return histories, cfgs, retained


def train_retention_from_store(
    store: PipelineStore,
    horizon_hours: float = 24.0,
    output_dir: str | Path = "training_artifacts",
    min_samples: int = 10,
    lr: float = 0.05,
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

    # Construct the full (feature, label) arrays by collapsing the first
    # candidate per pair.
    from ..sre.domain import ReleaseContext  # noqa
    cfgs = [cfg[0] for cfg in cfg_lists]

    # Wrap as a MatchConfig look-alike by creating a tiny adapter
    # since RetentionModel.fit expects ``MatchConfig``; but _eomm_features
    # only touches attributes the adapter can provide.
    class _Adapter:
        def __init__(self, rc):
            self.team_a = [_StubPlayer()]
            self.team_b = [_StubPlayer()]

    class _StubPlayer:
        class rating:
            mu = 25.0; sigma = 5.0

    adapters = [_Adapter(rc) for rc in cfgs]

    model = RetentionModel()
    model.fit(histories, adapters, retained, lr=lr, iters=iters)

    # Compute a loss delta as a report signal.
    X0 = np.stack([_eomm_features(h, c) for h, c in zip(histories, adapters)])
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
        extra={"feature_dim": int(X0.shape[1])},
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
