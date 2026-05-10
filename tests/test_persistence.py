"""Persistence layer tests — in-memory + SQLite parity."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from gan_matchmaking.core import AppConfig, MetricsRegistry
from gan_matchmaking.persistence import (
    InMemoryPipelineStore,
    Observation,
    SQLitePipelineStore,
)
from gan_matchmaking.sre import (
    ReleaseCandidate,
    ReleaseContext,
    SelfIterationPipeline,
    Service,
)


# ---------------------------------------------------------------------------
# Parity helpers — every test runs against both stores.
# ---------------------------------------------------------------------------
def _make_stores(tmp_path):
    return [
        ("memory", InMemoryPipelineStore()),
        ("sqlite", SQLitePipelineStore(tmp_path / "state.db")),
    ]


@pytest.fixture
def stores(tmp_path):
    opened = _make_stores(tmp_path)
    yield opened
    for _, s in opened:
        s.close()


# ---------------------------------------------------------------------------
# Service repository
# ---------------------------------------------------------------------------
def test_service_save_and_get_roundtrip(stores):
    for name, store in stores:
        svc = Service(id="svc-a", mu=0.985, sigma=0.021,
                      win_streak=4, loss_streak=0, total_releases=12,
                      tier="critical")
        store.services.save(svc)
        loaded = store.services.get("svc-a")
        assert loaded is not None, name
        assert loaded.mu == pytest.approx(0.985), name
        assert loaded.tier == "critical", name
        assert loaded.win_streak == 4, name
        assert store.services.get("missing") is None, name


def test_service_upsert_updates_in_place(stores):
    for name, store in stores:
        svc = Service(id="svc-b", mu=0.9, sigma=0.1)
        store.services.save(svc)
        svc.mu = 0.95; svc.sigma = 0.05
        store.services.save(svc)
        loaded = store.services.get("svc-b")
        assert loaded.mu == pytest.approx(0.95), name


def test_list_and_delete(stores):
    for name, store in stores:
        for sid in ("a", "b", "c"):
            store.services.save(Service(id=sid))
        ids = store.services.list_ids()
        assert set(ids) >= {"a", "b", "c"}, name
        assert store.services.delete("b") is True, name
        assert store.services.delete("b") is False, name


# ---------------------------------------------------------------------------
# Synergy
# ---------------------------------------------------------------------------
def test_synergy_accumulates(stores):
    for name, store in stores:
        store.synergy.increment("svc-a", "svc-b", win=True)
        store.synergy.increment("svc-b", "svc-a", win=True)  # same edge
        store.synergy.increment("svc-a", "svc-b", win=False)
        games, wins = store.synergy.stats("svc-a", "svc-b")
        assert games == 3, name
        assert wins == 2, name


def test_synergy_ignores_self_loops(stores):
    for name, store in stores:
        store.synergy.increment("svc-a", "svc-a", win=True)
        games, _ = store.synergy.stats("svc-a", "svc-a")
        assert games == 0, name


def test_synergy_edges_list(stores):
    for name, store in stores:
        store.synergy.increment("a", "b", win=True)
        store.synergy.increment("b", "c", win=False)
        edges = {(a, b) for a, b, _, _ in store.synergy.edges()}
        assert edges == {("a", "b"), ("b", "c")}, name


# ---------------------------------------------------------------------------
# Observations
# ---------------------------------------------------------------------------
def test_observation_recording_and_fetch(stores):
    for name, store in stores:
        ts0 = time.time()
        for i in range(5):
            store.observations.record(Observation(
                service_id="svc-a", success=bool(i % 2),
                timestamp=ts0 + i, duration_seconds=10.0,
                features={"x": float(i)}, correlation_id=f"c{i}"
            ))
        recent = store.observations.recent_observations("svc-a", limit=3)
        assert len(recent) == 3, name
        # Chronological order (oldest→newest).
        assert recent[0].timestamp < recent[-1].timestamp, name
        # Feature dict survives round-trip.
        assert recent[0].features["x"] == pytest.approx(2.0), name


def test_observation_rejects_empty_service(stores):
    for name, store in stores:
        with pytest.raises(Exception):
            store.observations.record(Observation(
                service_id="", success=True,
                timestamp=time.time(), duration_seconds=0.0))


# ---------------------------------------------------------------------------
# SQLite-specific: schema migrations and persistence across reopen.
# ---------------------------------------------------------------------------
def test_sqlite_state_persists_across_reopen(tmp_path):
    path = tmp_path / "db.sqlite"
    s1 = SQLitePipelineStore(path)
    s1.services.save(Service(id="persist", mu=0.977, sigma=0.011,
                              win_streak=3))
    s1.synergy.increment("persist", "dep", win=True)
    s1.observations.record(Observation(
        service_id="persist", success=True,
        timestamp=time.time(), duration_seconds=15.0
    ))
    s1.close()

    s2 = SQLitePipelineStore(path)
    try:
        assert s2.services.get("persist").mu == pytest.approx(0.977)
        games, wins = s2.synergy.stats("persist", "dep")
        assert games == 1 and wins == 1
        obs = s2.observations.recent_observations("persist")
        assert len(obs) == 1 and obs[0].success is True
    finally:
        s2.close()


def test_sqlite_migrations_idempotent(tmp_path):
    path = tmp_path / "db.sqlite"
    for _ in range(3):
        store = SQLitePipelineStore(path)
        store.close()
    # A valid services row can still be inserted.
    store = SQLitePipelineStore(path)
    try:
        store.services.save(Service(id="ok", mu=0.9, sigma=0.1))
        assert store.services.get("ok") is not None
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Integration with SelfIterationPipeline
# ---------------------------------------------------------------------------
def test_pipeline_hydrates_from_store(tmp_path):
    path = tmp_path / "hydrate.sqlite"
    # Seed one store.
    s1 = SQLitePipelineStore(path)
    try:
        s1.services.save(Service(id="svc-h", mu=0.993, sigma=0.008,
                                  win_streak=5, total_releases=20))
        s1.synergy.increment("svc-h", "dep-x", win=True)
    finally:
        s1.close()

    # Open a second store handle for the pipeline.
    s2 = SQLitePipelineStore(path)
    try:
        pipeline = SelfIterationPipeline(config=AppConfig(),
                                         metrics=MetricsRegistry(),
                                         store=s2)
        loaded = pipeline._services.get("svc-h")  # noqa: SLF001 (test intent)
        assert loaded is not None
        assert loaded.win_streak == 5

        # Decide must work against the hydrated state.
        candidate = ReleaseCandidate(
            id="c1", service_id="svc-h",
            strategy="canary", canary_fraction=0.05,
            rollback_budget_seconds=180, expected_success=0.995,
        )
        ctx = ReleaseContext(service=loaded, candidates=[candidate],
                             dependencies=["dep-x"])
        decision = pipeline.decide(ctx)
        assert decision is not None

        # Observing a release must persist the rating.
        pipeline.observe_release("svc-h", success=True,
                                  duration_seconds=12.0,
                                  correlation_id="obs-1")
    finally:
        s2.close()

    # Re-open a fresh store and confirm the observation landed.
    s3 = SQLitePipelineStore(path)
    try:
        svc = s3.services.get("svc-h")
        assert svc.total_releases == 21
        obs = s3.observations.recent_observations("svc-h")
        assert len(obs) == 1
        assert obs[0].correlation_id == "obs-1"
    finally:
        s3.close()
