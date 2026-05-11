"""Replay fixture export helpers.

The online pipeline persists decisions as an audit log. This module turns one
SQLite decision row back into the JSON fixture shape consumed by
``tests/test_replay_corpus.py``. It intentionally works from SQLite directly so
on-call can use it against a copied production state file without booting the
HTTP service.
"""
from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from ..core.errors import DataError


@dataclass(frozen=True)
class DecisionAuditRow:
    correlation_id: str
    kind: str
    risk_level: str
    risk_prob: float
    confidence: float
    chosen_id: Optional[str]
    artifact_version: str
    rationale: list[str]
    trace: Mapping[str, Any]
    created_at: float


def _safe_fixture_name(raw: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", raw.strip()).strip("._-")
    return name or "replay_fixture"


def _loads_json_field(raw: str, *, field: str, correlation_id: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DataError(
            f"invalid JSON in decisions.{field}",
            details={"correlation_id": correlation_id, "field": field},
        ) from exc


def load_decision_audit_row(db_path: str | Path, correlation_id: str) -> DecisionAuditRow:
    """Load one persisted decision from SQLite."""
    path = Path(db_path)
    if not path.exists():
        raise DataError("SQLite state db not found", details={"path": str(path)})

    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT correlation_id, kind, risk_level, risk_prob, confidence, "
            "chosen_id, artifact_version, rationale_json, trace_json, created_at "
            "FROM decisions WHERE correlation_id = ?",
            (correlation_id,),
        ).fetchone()

    if row is None:
        raise DataError(
            "decision audit row not found",
            details={"path": str(path), "correlation_id": correlation_id},
        )

    rationale = _loads_json_field(
        row["rationale_json"],
        field="rationale_json",
        correlation_id=correlation_id,
    )
    trace = _loads_json_field(
        row["trace_json"],
        field="trace_json",
        correlation_id=correlation_id,
    )
    if not isinstance(rationale, list):
        raise DataError(
            "decisions.rationale_json must be a list",
            details={"correlation_id": correlation_id},
        )
    if not isinstance(trace, Mapping):
        raise DataError(
            "decisions.trace_json must be an object",
            details={"correlation_id": correlation_id},
        )

    artifact_version = row["artifact_version"]
    if artifact_version is None:
        artifacts = trace.get("artifacts", {})
        if not isinstance(artifacts, Mapping):
            artifacts = {}
        artifact_version = artifacts.get("version", "bootstrap")

    return DecisionAuditRow(
        correlation_id=row["correlation_id"],
        kind=row["kind"],
        risk_level=row["risk_level"],
        risk_prob=float(row["risk_prob"]),
        confidence=float(row["confidence"]),
        chosen_id=row["chosen_id"],
        artifact_version=str(artifact_version or "bootstrap"),
        rationale=[str(item) for item in rationale],
        trace=trace,
        created_at=float(row["created_at"]),
    )


def build_replay_fixture(
    row: DecisionAuditRow,
    *,
    config: Optional[Mapping[str, Any]] = None,
    name: Optional[str] = None,
    allow_fitted_artifacts: bool = False,
) -> dict[str, Any]:
    """Build a replay fixture from a decision audit row.

    Fitted artifacts are not embedded in the decision audit table. By default
    we refuse to export those rows as standalone golden fixtures, because they
    would replay through bootstrap weights and mask a real artifact dependency.
    """
    trace_input = row.trace.get("input", {})
    if not isinstance(trace_input, Mapping):
        trace_input = {}
    context = trace_input.get("context")
    if not isinstance(context, Mapping):
        raise DataError(
            "decision trace does not contain replay context",
            details={
                "correlation_id": row.correlation_id,
                "hint": "re-run the decision with a pipeline that records trace.input.context",
            },
        )

    artifact_version = row.artifact_version or "bootstrap"
    if artifact_version != "bootstrap" and not allow_fitted_artifacts:
        raise DataError(
            "cannot export fitted-artifact decision as a standalone fixture",
            details={
                "correlation_id": row.correlation_id,
                "artifact_version": artifact_version,
                "hint": "pass allow_fitted_artifacts=True and provide the matching artifact bundle when replaying",
            },
        )

    config_payload: Mapping[str, Any]
    if config is not None:
        config_payload = dict(config)
    else:
        embedded_config = trace_input.get("config", {})
        config_payload = dict(embedded_config) if isinstance(embedded_config, Mapping) else {}

    expected: dict[str, Any] = {
        "kind": row.kind,
        "chosen_id": row.chosen_id,
        "risk_level": row.risk_level,
        "artifact_version": artifact_version,
    }
    stages = row.trace.get("stages", {})
    if isinstance(stages, Mapping):
        eomm = stages.get("eomm", {})
        if isinstance(eomm, Mapping) and "source" in eomm:
            expected["eomm_source"] = str(eomm["source"])

    payload: dict[str, Any] = {
        "name": _safe_fixture_name(name or row.correlation_id),
        "config": config_payload,
        "context": dict(context),
        "expected": expected,
        "source": {
            "kind": "sqlite_decision_audit",
            "correlation_id": row.correlation_id,
            "created_at": row.created_at,
            "risk_prob": row.risk_prob,
            "confidence": row.confidence,
            "rationale": row.rationale,
        },
    }
    if artifact_version != "bootstrap":
        payload["requires_artifact_version"] = artifact_version
    return payload


def export_replay_fixture(
    db_path: str | Path,
    correlation_id: str,
    *,
    output: str | Path | None = None,
    config: Optional[Mapping[str, Any]] = None,
    name: Optional[str] = None,
    allow_fitted_artifacts: bool = False,
) -> dict[str, Any]:
    """Export one SQLite decision row as a replay fixture payload."""
    row = load_decision_audit_row(db_path, correlation_id)
    payload = build_replay_fixture(
        row,
        config=config,
        name=name,
        allow_fitted_artifacts=allow_fitted_artifacts,
    )
    if output is not None:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return payload
