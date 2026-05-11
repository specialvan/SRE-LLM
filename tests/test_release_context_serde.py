"""Tests for ReleaseContext.from_dict public serialisation API (F-007)."""
from __future__ import annotations

from pathlib import Path

import pytest

from gan_matchmaking import cli
from gan_matchmaking.sre import ReleaseContext


def _sample_payload() -> dict:
    return {
        "service": {
            "id": "svc-a",
            "mu": 0.98,
            "sigma": 0.04,
            "tier": "standard",
            "win_streak": 1,
            "loss_streak": 0,
            "total_releases": 12,
        },
        "candidates": [
            {
                "id": "c-0",
                "service_id": "svc-a",
                "strategy": "canary",
                "canary_fraction": 0.1,
                "rollback_budget_seconds": 180,
                "expected_success": 0.99,
                "notes": "first slice",
            },
        ],
        "dependencies": ["svc-b"],
        "error_budget_remaining": 0.7,
        "freeze_window": False,
        "telemetry": {"cpu": 0.4, "mem": 0.6},
        "correlation_id": "serde-1",
    }


def test_release_context_from_dict_matches_cli_helper():
    """R-505 / R-506: public API and legacy alias must produce equal objects."""
    payload = _sample_payload()
    via_public = ReleaseContext.from_dict(payload)
    via_private = cli._ctx_from_dict(payload)
    assert via_public == via_private


def test_release_context_from_dict_rejects_missing_service():
    """R-505: required fields missing should raise (not silently default)."""
    with pytest.raises(KeyError):
        ReleaseContext.from_dict({"candidates": []})


def test_release_context_from_dict_defaults_are_safe():
    """R-505: missing optional fields fall back to documented defaults."""
    ctx = ReleaseContext.from_dict({
        "service": {"id": "svc-min"},
        "candidates": [],
    })
    assert ctx.error_budget_remaining == 1.0
    assert ctx.freeze_window is False
    assert ctx.dependencies == []
    assert ctx.telemetry is None
    assert ctx.correlation_id is None
    assert ctx.service.mu == pytest.approx(0.99)
    assert ctx.service.sigma == pytest.approx(0.02)


def test_release_context_from_dict_forces_matching_service_id():
    """R-505: candidate service_id is forced to service.id so validate() passes."""
    payload = _sample_payload()
    # Even when the payload lies about the candidate service_id, from_dict
    # must normalise it so ``validate`` does not reject perfectly good input.
    payload["candidates"][0]["service_id"] = "wrong-svc"
    ctx = ReleaseContext.from_dict(payload)
    ctx.validate()
    assert all(c.service_id == ctx.service.id for c in ctx.candidates)


def test_no_private_ctx_import_in_public_modules():
    """R-507: public modules and replay tests must stop importing the legacy private helper."""
    repo = Path(__file__).resolve().parents[1]
    for relpath in (
        Path("gan_matchmaking") / "service" / "app.py",
        Path("tests") / "test_replay_corpus.py",
        Path("tests") / "test_replay_export.py",
    ):
        text = (repo / relpath).read_text(encoding="utf-8")
        assert "_ctx_from_dict" not in text, (
            f"{relpath} still imports the deprecated private helper"
        )
