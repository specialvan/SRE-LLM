"""Tests for replay.py boundary conditions."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from gan_matchmaking.core.errors import DataError
from gan_matchmaking.sre.replay import (
    DecisionAuditRow,
    build_replay_fixture,
    load_decision_audit_row,
)


class TestBuildReplayFixture:
    """Tests for build_replay_fixture function."""

    def test_build_replay_fixture_with_config_override(self):
        """Verify config overrides are embedded in fixture."""
        row = DecisionAuditRow(
            correlation_id="test-config-001",
            kind="go",
            risk_level="low",
            risk_prob=0.1,
            confidence=0.9,
            chosen_id="svc-1",
            artifact_version="bootstrap",
            rationale=["test"],
            trace={
                "input": {
                    "context": {
                        "service": {"id": "svc-1"},
                        "candidates": [{"id": "c-1", "strategy": "canary"}],
                    }
                }
            },
            created_at=1.0,
        )
        fixture = build_replay_fixture(
            row,
            config={"seed": 42, "artifacts": {"directory": "/tmp/artifacts"}},
            name="test_fixture",
        )
        assert fixture["name"] == "test_fixture"
        assert fixture["config"]["seed"] == 42
        assert fixture["config"]["artifacts"]["directory"] == "/tmp/artifacts"

    def test_build_replay_fixture_with_artifact_bundle(self):
        """Verify artifact bundle reference is embedded in fixture."""
        row = DecisionAuditRow(
            correlation_id="test-bundle-001",
            kind="canary",
            risk_level="low",
            risk_prob=0.1,
            confidence=0.9,
            chosen_id="svc-1",
            artifact_version="retention@v1",
            rationale=["test"],
            trace={
                "input": {
                    "context": {
                        "service": {"id": "svc-1"},
                        "candidates": [{"id": "c-1", "strategy": "canary"}],
                    }
                }
            },
            created_at=1.0,
        )
        fixture = build_replay_fixture(
            row,
            name="test_bundle_fixture",
            allow_fitted_artifacts=True,
            artifact_bundle={"path": "artifacts/my-bundle"},
        )
        assert fixture["artifact_bundle"]["path"] == "artifacts/my-bundle"
        assert fixture["expected"]["artifact_version"] == "retention@v1"

    def test_build_replay_fixture_requires_context_not_empty(self):
        """Verify error when context exists but is empty mapping."""
        row = DecisionAuditRow(
            correlation_id="test-empty-001",
            kind="go",
            risk_level="low",
            risk_prob=0.1,
            confidence=0.9,
            chosen_id="svc-1",
            artifact_version="bootstrap",
            rationale=["test"],
            trace={"input": {"context": None}},  # context is None, not a Mapping
            created_at=1.0,
        )
        with pytest.raises(DataError) as exc_info:
            build_replay_fixture(row)
        assert "does not contain replay context" in str(exc_info.value)

    def test_build_replay_fixture_preserves_shadow_mode_in_config(self):
        """Verify shadow_mode is embedded in config when passed."""
        row = DecisionAuditRow(
            correlation_id="test-shadow-001",
            kind="hold",
            risk_level="medium",
            risk_prob=0.3,
            confidence=0.8,
            chosen_id="svc-1",
            artifact_version="bootstrap",
            rationale=["shadow mode"],
            trace={
                "input": {
                    "context": {
                        "service": {"id": "svc-1"},
                        "candidates": [{"id": "c-1", "strategy": "canary"}],
                    }
                },
                "stages": {},
            },
            created_at=1.0,
        )
        fixture = build_replay_fixture(
            row,
            name="test_shadow",
            config={"shadow_mode": "shadow"},
        )
        # shadow_mode goes into config, not as top-level field
        assert fixture["config"]["shadow_mode"] == "shadow"
        assert fixture["expected"]["kind"] == "hold"


class TestLoadDecisionAuditRow:
    """Tests for load_decision_audit_row function."""

    def test_load_decision_audit_row_with_null_artifact_version(self, tmp_path):
        """Verify artifact_version defaults to bootstrap when null."""
        db_path = tmp_path / "test.db"
        with sqlite3.connect(db_path) as conn:
            conn.execute("""
                CREATE TABLE decisions (
                    correlation_id TEXT PRIMARY KEY,
                    kind TEXT, risk_level TEXT, risk_prob REAL, confidence REAL,
                    chosen_id TEXT, artifact_version TEXT, rationale_json TEXT,
                    trace_json TEXT, created_at REAL
                )
            """)
            conn.execute("""
                INSERT INTO decisions VALUES (
                    'test-001', 'go', 'low', 0.1, 0.9, 'svc-1', NULL,
                    '["test"]',
                    '{"input": {"context": {}}}',
                    1.0
                )
            """)

        row = load_decision_audit_row(db_path, "test-001")
        assert row.artifact_version == "bootstrap"

    def test_load_decision_audit_row_with_artifacts_version(self, tmp_path):
        """Verify artifact_version from trace.artifacts.version."""
        db_path = tmp_path / "test.db"
        with sqlite3.connect(db_path) as conn:
            conn.execute("""
                CREATE TABLE decisions (
                    correlation_id TEXT PRIMARY KEY,
                    kind TEXT, risk_level TEXT, risk_prob REAL, confidence REAL,
                    chosen_id TEXT, artifact_version TEXT, rationale_json TEXT,
                    trace_json TEXT, created_at REAL
                )
            """)
            conn.execute("""
                INSERT INTO decisions VALUES (
                    'test-002', 'canary', 'warn', 0.2, 0.85, 'svc-1', NULL,
                    '["test"]',
                    '{"input": {"context": {}}, "artifacts": {"version": "retention@v2"}}',
                    1.0
                )
            """)

        row = load_decision_audit_row(db_path, "test-002")
        assert row.artifact_version == "retention@v2"

    def test_load_decision_audit_row_rationale_parsed(self, tmp_path):
        """Verify rationale_json is parsed as list."""
        db_path = tmp_path / "test.db"
        with sqlite3.connect(db_path) as conn:
            conn.execute("""
                CREATE TABLE decisions (
                    correlation_id TEXT PRIMARY KEY,
                    kind TEXT, risk_level TEXT, risk_prob REAL, confidence REAL,
                    chosen_id TEXT, artifact_version TEXT, rationale_json TEXT,
                    trace_json TEXT, created_at REAL
                )
            """)
            conn.execute("""
                INSERT INTO decisions VALUES (
                    'test-003', 'go', 'low', 0.1, 0.9, 'svc-1', 'bootstrap',
                    '["step 1", "step 2", "step 3"]',
                    '{"input": {"context": {}}}',
                    1.0
                )
            """)

        row = load_decision_audit_row(db_path, "test-003")
        assert row.rationale == ["step 1", "step 2", "step 3"]


