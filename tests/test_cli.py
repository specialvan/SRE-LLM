"""Smoke tests for the ``python -m gan_matchmaking.cli`` entry point."""
from __future__ import annotations

import io
import json
import sys

import pytest

from gan_matchmaking import cli


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
