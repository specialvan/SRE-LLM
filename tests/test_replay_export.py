"""Replay fixture export tests."""
from __future__ import annotations

import json

from gan_matchmaking.cli import _ctx_from_dict
from gan_matchmaking.core import AppConfig, MetricsRegistry, load_config
from gan_matchmaking.persistence import SQLitePipelineStore
from gan_matchmaking.sre import SelfIterationPipeline
from gan_matchmaking.sre.replay import export_replay_fixture


def _context_payload():
    return {
        "service": {
            "id": "svc-export",
            "mu": 0.995,
            "sigma": 0.005,
            "win_streak": 3,
            "total_releases": 30,
            "tier": "standard",
        },
        "candidates": [
            {
                "id": "c-canary",
                "strategy": "canary",
                "canary_fraction": 0.1,
                "rollback_budget_seconds": 300,
                "expected_success": 0.98,
            },
            {
                "id": "c-full",
                "strategy": "full",
                "canary_fraction": 0.0,
                "rollback_budget_seconds": 600,
                "expected_success": 0.97,
            },
        ],
        "error_budget_remaining": 0.8,
        "correlation_id": "export-corr-1",
    }


def test_export_replay_fixture_from_sqlite_decision(tmp_path):
    db_path = tmp_path / "state.sqlite"
    store = SQLitePipelineStore(db_path)
    try:
        pipeline = SelfIterationPipeline(
            config=AppConfig(),
            metrics=MetricsRegistry(),
            store=store,
        )
        original = pipeline.decide(_ctx_from_dict(_context_payload()))
    finally:
        store.close()

    out_path = tmp_path / "fixture.json"
    fixture = export_replay_fixture(
        db_path,
        "export-corr-1",
        output=out_path,
        name="exported-decision",
    )

    assert out_path.exists()
    assert json.loads(out_path.read_text(encoding="utf-8")) == fixture
    assert fixture["name"] == "exported-decision"
    assert fixture["context"]["service"]["id"] == "svc-export"
    assert fixture["expected"]["kind"] == original.kind.value
    assert fixture["expected"]["chosen_id"] == (
        original.chosen.id if original.chosen else None
    )
    assert fixture["expected"]["risk_level"] == original.risk_level.value
    assert fixture["expected"]["artifact_version"] == "bootstrap"
    assert fixture["source"]["correlation_id"] == "export-corr-1"

    replay = SelfIterationPipeline(
        config=load_config(fixture["config"]),
        metrics=MetricsRegistry(),
    ).decide(_ctx_from_dict(fixture["context"]))
    assert replay.kind.value == fixture["expected"]["kind"]
    assert (replay.chosen.id if replay.chosen else None) == fixture["expected"]["chosen_id"]
    assert replay.risk_level.value == fixture["expected"]["risk_level"]
