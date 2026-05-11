"""Tests for offline training pipelines."""
from __future__ import annotations

import json
import time

import pytest

from gan_matchmaking.core.errors import DataError
from gan_matchmaking.persistence import (
    InMemoryPipelineStore,
    Observation,
    SQLitePipelineStore,
)
from gan_matchmaking.sre.artifacts import EOMM_FEATURE_NAMES
from gan_matchmaking.sre.features import RISK_FEATURE_NAMES
from gan_matchmaking.training import (
    train_cox_from_store,
    train_retention_from_store,
)


def _seed(store, n_success: int = 30, n_failure: int = 8):
    ts = time.time() - 3600
    for i in range(n_success):
        store.observations.record(Observation(
            service_id="svc-a", success=True,
            timestamp=ts + i * 60, duration_seconds=60.0))
    for j in range(n_failure):
        store.observations.record(Observation(
            service_id="svc-a", success=False,
            timestamp=ts + (n_success + j) * 60, duration_seconds=120.0))
    # Second service for variety.
    for k in range(15):
        store.observations.record(Observation(
            service_id="svc-b", success=bool(k % 2),
            timestamp=ts + k * 90, duration_seconds=75.0))


def test_train_cox_from_memory_store(tmp_path):
    store = InMemoryPipelineStore()
    _seed(store)
    report = train_cox_from_store(store, output_dir=tmp_path)
    assert report.n_events >= 3
    assert len(report.beta) == len(RISK_FEATURE_NAMES)
    assert report.output_path.endswith("cox_beta.npz")
    assert report.artifact_version
    assert report.metadata_path.endswith("cox_artifact.json")
    assert (tmp_path / "cox_beta.npz").exists()
    assert (tmp_path / "cox_artifact.json").exists()
    assert (tmp_path / "cox_report.json").exists()
    metadata = json.loads((tmp_path / "cox_artifact.json").read_text(encoding="utf-8"))
    assert metadata["extra"]["feature_names"] == list(RISK_FEATURE_NAMES)


def test_train_cox_errors_on_empty_store(tmp_path):
    store = InMemoryPipelineStore()
    with pytest.raises(DataError):
        train_cox_from_store(store, output_dir=tmp_path)


def test_train_retention_from_sqlite_store(tmp_path):
    db = tmp_path / "state.db"
    store = SQLitePipelineStore(db)
    try:
        _seed(store)
        report = train_retention_from_store(store, output_dir=tmp_path)
    finally:
        store.close()
    assert report.n_samples > 10
    assert 0.0 <= report.positive_rate <= 1.0
    # Training should not regress the logistic loss beyond a tiny numerical
    # slack (the model does gradient descent with a fixed step size).
    assert report.loss_end <= report.loss_start + 0.1
    assert (tmp_path / "retention_weights.npz").exists()
    assert (tmp_path / "retention_artifact.json").exists()
    assert report.artifact_version
    assert report.metadata_path.endswith("retention_artifact.json")
    metadata = json.loads((tmp_path / "retention_artifact.json").read_text(encoding="utf-8"))
    assert metadata["extra"]["feature_names"] == list(EOMM_FEATURE_NAMES)
