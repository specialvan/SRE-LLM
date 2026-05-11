"""Smoke tests for the ``python -m gan_matchmaking.cli`` entry point."""
from __future__ import annotations

import io
import json
import sys

import pytest

from gan_matchmaking import cli
from gan_matchmaking.core import AppConfig, MetricsRegistry
from gan_matchmaking.persistence import SQLitePipelineStore
from gan_matchmaking.sre import SelfIterationPipeline


def _sample_input():
    return {
        "service": {
            "id": "svc-demo",
            "mu": 0.995,
            "sigma": 0.005,
            "win_streak": 3,
            "tier": "standard",
        },
        "candidates": [
            {
                "id": "c-canary",
                "strategy": "canary",
                "canary_fraction": 0.1,
                "rollback_budget_seconds": 300,
                "expected_success": 0.99,
            },
            {
                "id": "c-full",
                "strategy": "full",
                "canary_fraction": 0.0,
                "rollback_budget_seconds": 600,
                "expected_success": 0.98,
            },
        ],
        "error_budget_remaining": 0.8,
        "freeze_window": False,
        "correlation_id": "cli-trace-1",
    }


def test_cli_decide_outputs_decision_dict(tmp_path, capsys):
    path = tmp_path / "ctx.json"
    path.write_text(json.dumps(_sample_input()), encoding="utf-8")
    exit_code = cli.main(["decide", "--input", str(path)])
    assert exit_code == 0
    out = capsys.readouterr().out.strip()
    payload = json.loads(out)
    assert payload["correlation_id"] == "cli-trace-1"
    assert payload["kind"] in {"go", "canary", "hold", "rollback", "escalate"}
    assert "trace" in payload
    assert "stages" in payload["trace"]


def test_cli_returns_error_code_on_bad_input(tmp_path, capsys):
    path = tmp_path / "ctx.json"
    path.write_text(json.dumps({
        "service": {"id": "svc-demo"},
        "candidates": [],
    }), encoding="utf-8")
    exit_code = cli.main(["decide", "--input", str(path)])
    assert exit_code == 2
    err = capsys.readouterr().err.strip()
    payload = json.loads(err)
    assert payload["error"]["code"].startswith("gan.")


def test_cli_metrics_output(capsys):
    exit_code = cli.main(["metrics"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "gan_decisions_total" in out or "# HELP" in out or out == ""


def test_cli_export_replay_writes_fixture(tmp_path, capsys):
    db_path = tmp_path / "state.sqlite"
    store = SQLitePipelineStore(db_path)
    try:
        pipeline = SelfIterationPipeline(
            config=AppConfig(),
            metrics=MetricsRegistry(),
            store=store,
        )
        pipeline.decide(cli._ctx_from_dict(_sample_input()))  # noqa: SLF001
    finally:
        store.close()

    out_path = tmp_path / "fixture.json"
    exit_code = cli.main([
        "export-replay",
        "--state-db",
        str(db_path),
        "--correlation-id",
        "cli-trace-1",
        "--output",
        str(out_path),
        "--name",
        "cli-exported",
    ])
    assert exit_code == 0
    status = json.loads(capsys.readouterr().out)
    assert status["status"] == "exported"
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["name"] == "cli-exported"
    assert payload["context"]["correlation_id"] == "cli-trace-1"
    assert payload["expected"]["artifact_version"] == "bootstrap"
