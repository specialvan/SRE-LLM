"""Replay fixture export helpers.

The online pipeline persists decisions as an audit log. This module turns one
SQLite decision row back into the JSON fixture shape consumed by
``tests/test_replay_corpus.py``. It intentionally works from SQLite directly so
on-call can use it against a copied production state file without booting the
HTTP service.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from stat import S_ISDIR, S_ISREG
from typing import Any, Optional

from ..core.errors import DataError
from .artifacts import load_runtime_artifacts, retention_scaling_compatibility


DEFAULT_ARTIFACT_FILENAMES = {
    "retention_filename": "retention_weights.npz",
    "retention_metadata_filename": "retention_artifact.json",
    "cox_filename": "cox_beta.npz",
    "cox_metadata_filename": "cox_artifact.json",
}


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


def _artifact_filename(raw: Any, *, key: str) -> str:
    filename = str(raw)
    posix_path = PurePosixPath(filename)
    windows_path = PureWindowsPath(filename)
    if (
        not filename
        or posix_path.is_absolute()
        or windows_path.is_absolute()
        or posix_path.name != filename
        or windows_path.name != filename
        or filename in {".", ".."}
    ):
        raise DataError(
            "artifact filename must be a basename",
            details={"field": f"artifacts.{key}", "filename": filename},
        )
    return filename


def _artifact_filenames(config: Mapping[str, Any]) -> dict[str, str]:
    artifacts = config.get("artifacts", {})
    if not isinstance(artifacts, Mapping):
        artifacts = {}
    return {
        key: _artifact_filename(artifacts.get(key, default), key=key)
        for key, default in DEFAULT_ARTIFACT_FILENAMES.items()
    }


def _reject_symlink_artifacts(
    artifact_directory: str | Path,
    filenames: Mapping[str, str],
) -> None:
    directory = Path(artifact_directory)
    for key, filename in filenames.items():
        artifact_path = directory / filename
        if artifact_path.is_symlink():
            raise DataError(
                "artifact file must not be a symlink",
                details={"field": f"artifacts.{key}", "filename": filename},
            )


def _open_no_follow_read(path: Path, *, filename: str) -> int:
    try:
        before = path.stat(follow_symlinks=False)
        if not S_ISREG(before.st_mode):
            raise OSError("source is not a regular file")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        try:
            after = os.fstat(fd)
            if not os.path.samestat(before, after):
                raise OSError("source changed while opening")
            return fd
        except Exception:
            os.close(fd)
            raise
    except OSError as exc:
        raise DataError(
            "artifact file must be a regular non-symlink file",
            details={"filename": filename},
        ) from exc


def _open_no_follow_create(
    path: str | Path,
    *,
    filename: str,
    dir_fd: int,
) -> int:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        return os.open(path, flags, 0o600, dir_fd=dir_fd)
    except OSError as exc:
        raise DataError(
            "artifact archive destination must be a new non-symlink file",
            details={"filename": filename},
        ) from exc


def _copy_regular_file_no_follow(
    source: Path,
    *,
    filename: str,
    dir_fd: int,
) -> None:
    source_fd = _open_no_follow_read(source, filename=filename)
    try:
        if not S_ISREG(os.fstat(source_fd).st_mode):
            raise DataError(
                "artifact file must be a regular non-symlink file",
                details={"filename": filename},
            )
        destination_fd = _open_no_follow_create(
            filename,
            filename=filename,
            dir_fd=dir_fd,
        )
        try:
            with os.fdopen(source_fd, "rb") as src_file:
                source_fd = -1
                with os.fdopen(destination_fd, "wb") as dst_file:
                    destination_fd = -1
                    while True:
                        chunk = src_file.read(1024 * 1024)
                        if not chunk:
                            break
                        dst_file.write(chunk)
        finally:
            if destination_fd >= 0:
                os.close(destination_fd)
    finally:
        if source_fd >= 0:
            os.close(source_fd)


def _write_new_file_no_follow(
    content: str,
    *,
    filename: str,
    dir_fd: int,
) -> None:
    fd = _open_no_follow_create(filename, filename=filename, dir_fd=dir_fd)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file_obj:
            fd = -1
            file_obj.write(content)
    finally:
        if fd >= 0:
            os.close(fd)


def _reject_symlink_path(path: Path) -> None:
    candidates = [path, *path.parents]
    for candidate in candidates:
        if candidate.exists() and candidate.is_symlink():
            raise DataError(
                "artifact archive path must not contain symlinks",
                details={"path": str(candidate)},
            )


def _open_directory_at(parent_fd: int, name: str, *, path: Path) -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(name, flags, dir_fd=parent_fd)
        try:
            if not S_ISDIR(os.fstat(fd).st_mode):
                raise OSError("path component is not a directory")
            return fd
        except Exception:
            os.close(fd)
            raise
    except OSError as exc:
        raise DataError(
            "artifact archive path must contain only non-symlink directories",
            details={"path": str(path)},
        ) from exc


def _create_archive_directory(path: Path) -> int:
    if os.name == "nt":
        raise DataError(
            "artifact archive output directory could not be opened securely",
            details={"path": str(path)},
        )
    absolute = path if path.is_absolute() else Path.cwd() / path
    parts = absolute.parts
    if not parts:
        raise DataError(
            "artifact archive output directory is invalid",
            details={"path": str(path)},
        )
    root_fd = os.open(parts[0], os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    current_fd = root_fd
    try:
        for index, part in enumerate(parts[1:], start=1):
            component_path = Path(*parts[: index + 1])
            is_leaf = index == len(parts) - 1
            if is_leaf:
                try:
                    os.mkdir(part, 0o700, dir_fd=current_fd)
                except FileExistsError as exc:
                    raise DataError(
                        "artifact archive output directory must not already exist",
                        details={"path": str(path)},
                    ) from exc
            next_fd = _open_directory_at(current_fd, part, path=component_path)
            if current_fd != root_fd:
                os.close(current_fd)
            current_fd = next_fd
        return current_fd
    except Exception:
        if current_fd != root_fd:
            os.close(current_fd)
        raise
    finally:
        os.close(root_fd)


def _archive_validation_directory(path: Path, dir_fd: int) -> Path:
    fd_path = Path(f"/proc/self/fd/{dir_fd}")
    if fd_path.exists():
        return fd_path
    raise DataError(
        "artifact archive validation requires fd-addressable directory access",
        details={"path": str(path)},
    )


def _relative_or_absolute(path: Path, *, base: Path | None) -> str:
    if base is None:
        return str(path)
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def validate_artifact_bundle(
    artifact_directory: str | Path,
    expected_version: str,
    *,
    config: Optional[Mapping[str, Any]] = None,
    allow_legacy_unknown: bool = False,
) -> dict[str, Any]:
    """Validate that a runtime artifact directory can replay a fitted decision."""
    filenames = _artifact_filenames(config or {})
    _reject_symlink_artifacts(artifact_directory, filenames)
    bundle = load_runtime_artifacts(
        artifact_directory,
        retention_filename=filenames["retention_filename"],
        retention_metadata_filename=filenames["retention_metadata_filename"],
        cox_filename=filenames["cox_filename"],
        cox_metadata_filename=filenames["cox_metadata_filename"],
    )
    if bundle.validation_errors:
        raise DataError(
            "artifact bundle failed manifest validation",
            details={
                "artifact_directory": str(artifact_directory),
                "validation_errors": {
                    key: list(errors)
                    for key, errors in bundle.validation_errors.items()
                },
            },
        )
    scaling = retention_scaling_compatibility(bundle.retention)
    if scaling.status == "mismatch" or (
        scaling.status == "unknown" and not allow_legacy_unknown
    ):
        raise DataError(
            "retention artifact rating-scaling version mismatch"
            if scaling.status == "mismatch"
            else "retention artifact rating-scaling version is unknown",
            details={
                "artifact_directory": str(artifact_directory),
                "artifact_version": scaling.artifact_version,
                "expected_rating_scaling_version": scaling.expected_version,
                "actual_rating_scaling_version": scaling.actual_version,
                "rating_scaling_status": scaling.status,
            },
        )
    if bundle.version != expected_version:
        raise DataError(
            "artifact bundle version mismatch",
            details={
                "artifact_directory": str(artifact_directory),
                "expected_version": expected_version,
                "actual_version": bundle.version,
            },
        )
    if not bundle.fitted:
        raise DataError(
            "artifact bundle is empty",
            details={"artifact_directory": str(artifact_directory)},
        )
    files = [
        filename
        for filename in filenames.values()
        if (Path(artifact_directory) / filename).is_file()
    ]
    return {
        "version": bundle.version,
        "files": files,
        "retention_version": (
            None if bundle.retention is None else bundle.retention.metadata.version
        ),
        "cox_version": None if bundle.cox is None else bundle.cox.metadata.version,
        "rating_scaling_status": scaling.status,
    }


def archive_artifact_bundle(
    artifact_directory: str | Path,
    output_directory: str | Path,
    expected_version: str,
    *,
    config: Optional[Mapping[str, Any]] = None,
    allow_legacy_unknown: bool = False,
) -> dict[str, Any]:
    """Copy a validated artifact bundle to an archive directory."""
    filenames = _artifact_filenames(config or {})
    src = Path(artifact_directory)
    dst = Path(output_directory)
    dst_fd = _create_archive_directory(dst)
    try:
        for filename in filenames.values():
            source = src / filename
            if source.is_file():
                _copy_regular_file_no_follow(
                    source,
                    filename=filename,
                    dir_fd=dst_fd,
                )
        manifest = validate_artifact_bundle(
            _archive_validation_directory(dst, dst_fd),
            expected_version,
            config=config,
            allow_legacy_unknown=allow_legacy_unknown,
        )
        _write_new_file_no_follow(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            filename="replay_artifact_manifest.json",
            dir_fd=dst_fd,
        )
    except Exception:
        for filename in [*filenames.values(), "replay_artifact_manifest.json"]:
            try:
                os.unlink(filename, dir_fd=dst_fd)
            except FileNotFoundError:
                pass
        try:
            dst.rmdir()
        except OSError:
            pass
        raise
    finally:
        if dst_fd is not None:
            os.close(dst_fd)
    return manifest


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
    artifact_bundle: Optional[Mapping[str, Any]] = None,
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
    if artifact_version != "bootstrap" and artifact_bundle is None:
        raise DataError(
            "fitted-artifact replay requires a validated artifact bundle",
            details={
                "correlation_id": row.correlation_id,
                "artifact_version": artifact_version,
                "hint": "pass artifact_directory and archive the bundle with the fixture",
            },
        )

    config_payload: Mapping[str, Any]
    if config is not None:
        config_payload = dict(config)
    else:
        embedded_config = trace_input.get("config", {})
        config_payload = dict(embedded_config) if isinstance(embedded_config, Mapping) else {}
    if artifact_bundle is not None:
        config_payload = dict(config_payload)
        raw_artifacts_cfg = config_payload.get("artifacts", {})
        artifacts_cfg = (
            dict(raw_artifacts_cfg)
            if isinstance(raw_artifacts_cfg, Mapping)
            else {}
        )
        artifacts_cfg.pop("directory", None)
        config_payload["artifacts"] = artifacts_cfg

    expected: dict[str, Any] = {
        "kind": row.kind,
        "chosen_id": row.chosen_id,
        "risk_level": row.risk_level,
        "artifact_version": artifact_version,
    }
    trace_values: dict[str, Any] = {}
    shadow_mode = row.trace.get("shadow_mode")
    if shadow_mode is not None:
        trace_values["shadow_mode"] = str(shadow_mode)
        suppressed_kind = row.trace.get("shadow_suppressed_kind")
        if suppressed_kind is not None:
            trace_values["shadow_suppressed_kind"] = str(suppressed_kind)
    if trace_values:
        expected["trace_values"] = trace_values
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
    if shadow_mode is not None:
        payload["shadow_mode"] = str(shadow_mode)
    if artifact_version != "bootstrap":
        payload["requires_artifact_version"] = artifact_version
        payload["artifact_bundle"] = dict(artifact_bundle or {})
    return payload


def export_replay_fixture(
    db_path: str | Path,
    correlation_id: str,
    *,
    output: str | Path | None = None,
    config: Optional[Mapping[str, Any]] = None,
    name: Optional[str] = None,
    allow_fitted_artifacts: bool = False,
    artifact_directory: str | Path | None = None,
    artifact_output_directory: str | Path | None = None,
    allow_legacy_unknown: bool = False,
) -> dict[str, Any]:
    """Export one SQLite decision row as a replay fixture payload."""
    row = load_decision_audit_row(db_path, correlation_id)
    trace_input = row.trace.get("input", {})
    if not isinstance(trace_input, Mapping):
        trace_input = {}
    config_payload = dict(config) if config is not None else trace_input.get("config", {})
    if not isinstance(config_payload, Mapping):
        config_payload = {}

    artifact_bundle = None
    if row.artifact_version != "bootstrap" and allow_fitted_artifacts:
        if artifact_directory is None:
            raise DataError(
                "artifact_directory is required for fitted-artifact replay export",
                details={
                    "correlation_id": row.correlation_id,
                    "artifact_version": row.artifact_version,
                },
            )
        bundle_dir = Path(artifact_directory)
        if artifact_output_directory is not None:
            archive_manifest = archive_artifact_bundle(
                bundle_dir,
                artifact_output_directory,
                row.artifact_version,
                config=config_payload,
                allow_legacy_unknown=allow_legacy_unknown,
            )
            bundle_path = Path(artifact_output_directory)
        else:
            archive_manifest = validate_artifact_bundle(
                bundle_dir,
                row.artifact_version,
                config=config_payload,
                allow_legacy_unknown=allow_legacy_unknown,
            )
            bundle_path = bundle_dir
        output_base = None if output is None else Path(output).parent
        artifact_bundle = {
            **archive_manifest,
            "path": _relative_or_absolute(bundle_path, base=output_base),
        }

    payload = build_replay_fixture(
        row,
        config=config_payload,
        name=name,
        allow_fitted_artifacts=allow_fitted_artifacts,
        artifact_bundle=artifact_bundle,
    )
    if output is not None:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return payload
