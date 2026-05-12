"""SQLite migration tests (F-008)."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from gan_matchmaking.persistence.sqlite import _MIGRATIONS, SQLitePipelineStore


def test_migration_all_versions_clean_boot(tmp_path):
    """R-606: a fresh DB ends up with all known migrations applied."""
    db_path = tmp_path / "state.sqlite"
    store = SQLitePipelineStore(db_path)
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = list(conn.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            ))
        assert [row["version"] for row in rows] == [m[0] for m in _MIGRATIONS]
    finally:
        store.close()


def test_migration_v5_idempotent_on_legacy_db(tmp_path):
    """R-605: legacy DB that already owns ``artifact_version`` still boots."""
    db_path = tmp_path / "legacy.sqlite"
    # Hand-craft the schema at pre-v5 state (v1..v4) PLUS the v5 column so
    # we simulate a database that was manually patched in production before
    # the migration catalogue tracked the change.
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at REAL NOT NULL
            );
            CREATE TABLE services (
                id TEXT PRIMARY KEY, mu REAL NOT NULL, sigma REAL NOT NULL,
                win_streak INTEGER NOT NULL DEFAULT 0,
                loss_streak INTEGER NOT NULL DEFAULT 0,
                total_releases INTEGER NOT NULL DEFAULT 0,
                tier TEXT NOT NULL DEFAULT 'standard',
                updated_at REAL NOT NULL
            );
            CREATE TABLE synergy_edges (
                a_id TEXT NOT NULL, b_id TEXT NOT NULL,
                games INTEGER NOT NULL DEFAULT 0,
                wins INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (a_id, b_id),
                CHECK (a_id <= b_id)
            );
            CREATE TABLE observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_id TEXT NOT NULL,
                success INTEGER NOT NULL,
                timestamp REAL NOT NULL,
                duration_seconds REAL NOT NULL,
                features_json TEXT,
                correlation_id TEXT
            );
            CREATE TABLE decisions (
                correlation_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                risk_prob REAL NOT NULL,
                confidence REAL NOT NULL,
                chosen_id TEXT,
                rationale_json TEXT NOT NULL,
                trace_json TEXT NOT NULL,
                created_at REAL NOT NULL,
                artifact_version TEXT
            );
            """
        )
        now = time.time()
        conn.executemany(
            "INSERT INTO schema_migrations(version, name, applied_at) VALUES (?,?,?)",
            [
                (1, "create_services", now),
                (2, "create_synergy", now),
                (3, "create_observations", now),
                (4, "create_decisions", now),
            ],
        )
        conn.commit()

    # Re-open via SQLitePipelineStore — must not raise.
    store = SQLitePipelineStore(db_path)
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = list(conn.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            ))
            assert [row["version"] for row in rows] == [m[0] for m in _MIGRATIONS]
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(decisions)")}
            assert "artifact_version" in cols
    finally:
        store.close()


def test_migration_does_not_include_v5_special_case():
    """R-606: no ``if version == 5`` branch remains in _migrate."""
    migrate_source = Path(
        "gan_matchmaking/persistence/sqlite.py"
    ).read_text(encoding="utf-8")
    assert "if version == 5" not in migrate_source
