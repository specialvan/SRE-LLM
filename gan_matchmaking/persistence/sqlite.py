"""SQLite-backed persistence.

Why SQLite
----------
- One file, no server, atomic commits via WAL mode.
- Readable from ``sqlite3`` CLI so on-call can inspect state without Python.
- Handles 100 TPS for our access pattern with ease.
- The schema uses only standard SQL so migrating to PostgreSQL later is a
  matter of swapping the driver.

Concurrency
-----------
- WAL mode is enabled so readers don't block writers.
- We serialise writes behind a per-connection lock on the Python side to
  avoid ``database is locked`` errors under contention.
- For cross-process coordination use either ``SQLITE_LOCK=EXCLUSIVE`` mode
  (single writer) or switch to a real DB.

Schema migrations
-----------------
A single ``schema_migrations`` table tracks what's been applied. New
migrations are appended to :data:`_MIGRATIONS`; the store runs them in
order on connect.
"""

from __future__ import annotations

import json
import os
import re as _re
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from ..core.errors import DataError
from ..sre.domain import Decision, Service
from .base import (
    Observation,
    ObservationRepository,
    PipelineStore,
    ServiceRepository,
    SynergyRepository,
)


# ---------------------------------------------------------------------------
# Migrations (append-only)
# ---------------------------------------------------------------------------
_MIGRATIONS: List[Tuple[int, str, str]] = [
    (
        1,
        "create_services",
        """
        CREATE TABLE IF NOT EXISTS services (
            id                TEXT PRIMARY KEY,
            mu                REAL NOT NULL,
            sigma             REAL NOT NULL,
            win_streak        INTEGER NOT NULL DEFAULT 0,
            loss_streak       INTEGER NOT NULL DEFAULT 0,
            total_releases    INTEGER NOT NULL DEFAULT 0,
            tier              TEXT NOT NULL DEFAULT 'standard',
            updated_at        REAL NOT NULL
        );
        """,
    ),
    (
        2,
        "create_synergy",
        """
        CREATE TABLE IF NOT EXISTS synergy_edges (
            a_id   TEXT NOT NULL,
            b_id   TEXT NOT NULL,
            games  INTEGER NOT NULL DEFAULT 0,
            wins   INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (a_id, b_id),
            CHECK (a_id <= b_id)
        );
        """,
    ),
    (
        3,
        "create_observations",
        """
        CREATE TABLE IF NOT EXISTS observations (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            service_id       TEXT NOT NULL,
            success          INTEGER NOT NULL,
            timestamp        REAL NOT NULL,
            duration_seconds REAL NOT NULL,
            features_json    TEXT,
            correlation_id   TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_observations_service
            ON observations (service_id, timestamp);
        """,
    ),
    (
        4,
        "create_decisions",
        """
        CREATE TABLE IF NOT EXISTS decisions (
            correlation_id   TEXT PRIMARY KEY,
            kind             TEXT NOT NULL,
            risk_level       TEXT NOT NULL,
            risk_prob        REAL NOT NULL,
            confidence       REAL NOT NULL,
            chosen_id        TEXT,
            rationale_json   TEXT NOT NULL,
            trace_json       TEXT NOT NULL,
            created_at       REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_decisions_kind_time
            ON decisions (kind, created_at);
        """,
    ),
    (
        5,
        "add_decision_artifact_version",
        """
        ALTER TABLE decisions ADD COLUMN artifact_version TEXT;
        """,
    ),
]


_ADD_COLUMN_RE = _re.compile(
    r"^ALTER\s+TABLE\s+(?P<table>\w+)\s+ADD\s+COLUMN\s+(?P<col>\w+)\s",
    _re.IGNORECASE,
)


def _idempotent_statement_skip(conn: sqlite3.Connection, statement: str) -> bool:
    """Return True if ``statement`` is a safe no-op given current schema.

    Covers SQLite's lack of ``ALTER TABLE ... ADD COLUMN IF NOT EXISTS``:
    if the column already exists on the target table, we treat the DDL as
    already applied rather than fail. Any other statement shape falls
    through and runs unconditionally.
    """
    match = _ADD_COLUMN_RE.match(statement.strip())
    if not match:
        return False
    table = match.group("table")
    column = match.group("col")
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    return column in existing


def _split_sql(script: str) -> List[str]:
    """Split a DDL string into individual statements (naive semicolon split).

    Good enough for the controlled DDL we ship here; do **not** use on
    user-provided SQL.
    """
    parts = [p.strip() for p in script.split(";")]
    return [p for p in parts if p]


# ---------------------------------------------------------------------------
# Low-level connection helper
# ---------------------------------------------------------------------------
class _SqliteConnection:
    """Serialised sqlite3 wrapper with schema auto-migration."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        Path(os.path.dirname(self.path) or ".").mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            self.path,
            isolation_level=None,  # autocommit — we manage transactions by hand.
            check_same_thread=False,
            detect_types=sqlite3.PARSE_DECLTYPES,
            timeout=5.0,
        )
        self._conn.row_factory = sqlite3.Row
        self._configure()
        self._migrate()

    def _configure(self) -> None:
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("PRAGMA foreign_keys=ON")

    def _migrate(self) -> None:
        with self._lock:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at REAL NOT NULL)"
            )
            applied = {
                row["version"]
                for row in self._conn.execute("SELECT version FROM schema_migrations")
            }
            for version, name, ddl in _MIGRATIONS:
                if version in applied:
                    continue
                # ``executescript`` issues an implicit COMMIT, so we run the
                # statement list ourselves and wrap it in an explicit
                # transaction for atomicity. Each statement is first filtered
                # through ``_idempotent_statement_skip`` so legacy databases
                # that already have an ``ALTER TABLE ... ADD COLUMN`` applied
                # (e.g. because they were hand-patched before the schema
                # version catalogue tracked it) still move forward cleanly.
                try:
                    self._conn.execute("BEGIN IMMEDIATE")
                    for statement in _split_sql(ddl):
                        if _idempotent_statement_skip(self._conn, statement):
                            continue
                        self._conn.execute(statement)
                    self._conn.execute(
                        "INSERT INTO schema_migrations(version, name, applied_at) VALUES (?, ?, ?)",
                        (version, name, time.time()),
                    )
                    self._conn.execute("COMMIT")
                except Exception:
                    try:
                        self._conn.execute("ROLLBACK")
                    except sqlite3.OperationalError:
                        pass
                    raise

    @contextmanager
    def transaction(self):
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield self._conn
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, params)

    def executemany(self, sql: str, seq_of_params) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.executemany(sql, seq_of_params)

    def close(self) -> None:
        with self._lock:
            self._conn.close()


# ---------------------------------------------------------------------------
# Repositories
# ---------------------------------------------------------------------------
class SQLiteServiceRepository(ServiceRepository):
    def __init__(self, conn: _SqliteConnection):
        self._c = conn

    def get(self, service_id: str) -> Optional[Service]:
        row = self._c.execute(
            "SELECT id, mu, sigma, win_streak, loss_streak, total_releases, tier "
            "FROM services WHERE id = ?",
            (service_id,),
        ).fetchone()
        if row is None:
            return None
        return Service(
            id=row["id"],
            mu=row["mu"],
            sigma=row["sigma"],
            win_streak=row["win_streak"],
            loss_streak=row["loss_streak"],
            total_releases=row["total_releases"],
            tier=row["tier"],
        )

    def save(self, service: Service) -> None:
        with self._c.transaction() as c:
            c.execute(
                "INSERT INTO services(id, mu, sigma, win_streak, loss_streak, "
                "total_releases, tier, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET "
                " mu=excluded.mu, sigma=excluded.sigma, "
                " win_streak=excluded.win_streak, loss_streak=excluded.loss_streak, "
                " total_releases=excluded.total_releases, tier=excluded.tier, "
                " updated_at=excluded.updated_at",
                (
                    service.id,
                    float(service.mu),
                    float(service.sigma),
                    int(service.win_streak),
                    int(service.loss_streak),
                    int(service.total_releases),
                    service.tier,
                    time.time(),
                ),
            )

    def list_ids(self, limit: Optional[int] = None) -> List[str]:
        if limit is None:
            cur = self._c.execute("SELECT id FROM services ORDER BY id")
        else:
            cur = self._c.execute(
                "SELECT id FROM services ORDER BY id LIMIT ?", (limit,)
            )
        return [row["id"] for row in cur.fetchall()]

    def delete(self, service_id: str) -> bool:
        with self._c.transaction() as c:
            cur = c.execute("DELETE FROM services WHERE id = ?", (service_id,))
            return cur.rowcount > 0


class SQLiteSynergyRepository(SynergyRepository):
    def __init__(self, conn: _SqliteConnection):
        self._c = conn

    @staticmethod
    def _norm(a: str, b: str) -> Tuple[str, str]:
        return (a, b) if a <= b else (b, a)

    def increment(self, a: str, b: str, win: bool) -> None:
        if a == b:
            return
        na, nb = self._norm(a, b)
        with self._c.transaction() as c:
            c.execute(
                "INSERT INTO synergy_edges(a_id, b_id, games, wins) VALUES(?,?,?,?) "
                "ON CONFLICT(a_id, b_id) DO UPDATE SET "
                " games = games + 1, "
                " wins  = wins  + ?",
                (na, nb, 1, 1 if win else 0, 1 if win else 0),
            )

    def stats(self, a: str, b: str) -> Tuple[int, int]:
        na, nb = self._norm(a, b)
        row = self._c.execute(
            "SELECT games, wins FROM synergy_edges WHERE a_id=? AND b_id=?",
            (na, nb),
        ).fetchone()
        if row is None:
            return 0, 0
        return row["games"], row["wins"]

    def edges(self, limit: Optional[int] = None) -> Iterable[Tuple[str, str, int, int]]:
        if limit is None:
            cur = self._c.execute(
                "SELECT a_id, b_id, games, wins FROM synergy_edges ORDER BY a_id, b_id"
            )
        else:
            cur = self._c.execute(
                "SELECT a_id, b_id, games, wins FROM synergy_edges "
                "ORDER BY a_id, b_id LIMIT ?",
                (limit,),
            )
        for row in cur.fetchall():
            yield row["a_id"], row["b_id"], row["games"], row["wins"]


class SQLiteObservationRepository(ObservationRepository):
    def __init__(self, conn: _SqliteConnection):
        self._c = conn

    def record(self, observation: Observation) -> None:
        if observation.service_id == "":
            raise DataError("observation.service_id must be non-empty")
        features = None
        if observation.features is not None:
            features = json.dumps(observation.features, ensure_ascii=False)
        with self._c.transaction() as c:
            c.execute(
                "INSERT INTO observations(service_id, success, timestamp, "
                "duration_seconds, features_json, correlation_id) "
                "VALUES(?,?,?,?,?,?)",
                (
                    observation.service_id,
                    1 if observation.success else 0,
                    float(observation.timestamp),
                    float(observation.duration_seconds),
                    features,
                    observation.correlation_id,
                ),
            )

    def record_decision(self, decision: Decision) -> None:
        with self._c.transaction() as c:
            c.execute(
                "INSERT INTO decisions(correlation_id, kind, risk_level, risk_prob, "
                "confidence, chosen_id, artifact_version, rationale_json, trace_json, created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(correlation_id) DO UPDATE SET "
                " kind=excluded.kind, risk_level=excluded.risk_level, "
                " risk_prob=excluded.risk_prob, confidence=excluded.confidence, "
                " chosen_id=excluded.chosen_id, artifact_version=excluded.artifact_version, "
                " rationale_json=excluded.rationale_json, trace_json=excluded.trace_json, "
                " created_at=excluded.created_at",
                (
                    decision.correlation_id,
                    decision.kind.value,
                    decision.risk_level.value,
                    float(decision.risk_prob),
                    float(decision.confidence),
                    decision.chosen.id if decision.chosen else None,
                    decision.artifact_version,
                    json.dumps(decision.rationale, ensure_ascii=False),
                    json.dumps(decision.trace, ensure_ascii=False, default=str),
                    time.time(),
                ),
            )

    def recent_observations(
        self, service_id: str, limit: int = 200
    ) -> List[Observation]:
        cur = self._c.execute(
            "SELECT service_id, success, timestamp, duration_seconds, "
            "features_json, correlation_id FROM observations "
            "WHERE service_id = ? ORDER BY timestamp DESC LIMIT ?",
            (service_id, int(limit)),
        )
        rows = cur.fetchall()
        # Return in chronological order (oldest first) for training code.
        return list(reversed([_row_to_obs(r) for r in rows]))

    def observations(self) -> Iterable[Observation]:
        cur = self._c.execute(
            "SELECT service_id, success, timestamp, duration_seconds, "
            "features_json, correlation_id FROM observations ORDER BY timestamp"
        )
        for row in cur.fetchall():
            yield _row_to_obs(row)


def _row_to_obs(row: sqlite3.Row) -> Observation:
    feats = None
    if row["features_json"]:
        try:
            feats = json.loads(row["features_json"])
        except json.JSONDecodeError:
            feats = None
    return Observation(
        service_id=row["service_id"],
        success=bool(row["success"]),
        timestamp=float(row["timestamp"]),
        duration_seconds=float(row["duration_seconds"]),
        features=feats,
        correlation_id=row["correlation_id"],
    )


class SQLitePipelineStore(PipelineStore):
    def __init__(self, path: str | Path):
        self._conn = _SqliteConnection(path)
        self.services = SQLiteServiceRepository(self._conn)
        self.synergy = SQLiteSynergyRepository(self._conn)
        self.observations = SQLiteObservationRepository(self._conn)

    def close(self) -> None:
        self._conn.close()
