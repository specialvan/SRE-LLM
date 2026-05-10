"""Train the Cox proportional-hazards model from observations.

The observation log stores ``(service_id, success, timestamp,
duration_seconds, features, correlation_id)``. We treat each *failure* as
an "event" and each *success* as "censored at duration_seconds past the
previous event". The feature vector defaults to ``[loss_streak_so_far,
time_since_prev]`` so the pipeline's untrained fallback sees a compatible
input shape.
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import numpy as np

from ..core.errors import DataError
from ..persistence import Observation, PipelineStore
from ..survival import CoxModel


@dataclass
class CoxTrainingReport:
    n_observations: int = 0
    n_events: int = 0
    services: int = 0
    beta: List[float] = field(default_factory=list)
    output_path: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "n_observations": self.n_observations,
            "n_events": self.n_events,
            "services": self.services,
            "beta": self.beta,
            "output_path": self.output_path,
        }


def _build_matrices(observations: Iterable[Observation]):
    """Turn ``Observation`` stream into ``(X, durations, events)`` numpy arrays.

    Feature vector convention:

        x = [loss_streak_so_far, gap_seconds_since_previous]
    """
    X: List[List[float]] = []
    durations: List[float] = []
    events: List[int] = []
    loss_streaks: Dict[str, int] = defaultdict(int)
    last_ts: Dict[str, float] = {}

    # We iterate in chronological order.
    sorted_obs = sorted(observations, key=lambda o: (o.service_id, o.timestamp))
    for obs in sorted_obs:
        sid = obs.service_id
        prev_ts = last_ts.get(sid, obs.timestamp)
        gap = max(obs.timestamp - prev_ts, 0.0)
        last_ts[sid] = obs.timestamp

        loss_streak = loss_streaks[sid]
        # Update streak after recording the feature vector for this obs.
        X.append([float(loss_streak), float(gap)])
        durations.append(max(float(obs.duration_seconds), 1e-3))
        events.append(0 if obs.success else 1)
        loss_streaks[sid] = 0 if obs.success else loss_streak + 1

    return (np.asarray(X, dtype=float),
            np.asarray(durations, dtype=float),
            np.asarray(events, dtype=int))


def train_cox_from_store(
    store: PipelineStore,
    output_dir: str | Path = "training_artifacts",
    min_events: int = 3,
) -> CoxTrainingReport:
    """Fit the Cox model on observations persisted in ``store``.

    The trained ``beta`` is serialised to
    ``output_dir/cox_beta.npz`` alongside a JSON report.
    """
    observations = list(store.observations.observations())
    if not observations:
        raise DataError("no observations available",
                        details={"hint": "persist releases before training"})
    X, durations, events = _build_matrices(observations)
    n_events = int(events.sum())
    if n_events < min_events:
        raise DataError(
            f"too few failures to fit Cox (got {n_events}, need >= {min_events})",
            details={"n_observations": len(observations),
                     "n_events": n_events},
        )

    model = CoxModel().fit(X, durations, events, iters=2000)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    np_path = output_dir / "cox_beta.npz"
    baseline_t = model._baseline_t if model._baseline_t is not None else []
    baseline_H = model._baseline_H if model._baseline_H is not None else []
    np.savez(np_path,
             beta=np.asarray(model.beta, dtype=float),
             baseline_t=np.asarray(baseline_t, dtype=float),
             baseline_H=np.asarray(baseline_H, dtype=float))

    beta_list = [] if model.beta is None else [float(v) for v in model.beta]
    report = CoxTrainingReport(
        n_observations=len(observations),
        n_events=n_events,
        services=len({o.service_id for o in observations}),
        beta=beta_list,
        output_path=str(np_path),
    )
    (output_dir / "cox_report.json").write_text(
        json.dumps(report.as_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report
