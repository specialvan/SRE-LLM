from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from analysis.control_center_data import build_control_center_payload
from scripts import package_smoke
from scripts.control_center_server import (
    API_PATH,
    CONTRACT_VERSION,
    validate_control_center_payload,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BROWSER_REPORT = (
    REPO_ROOT / "analysis" / "artifacts" / "control-center-browser-evidence-report.json"
)
DEFAULT_AUDIT_PATH = (
    REPO_ROOT / "analysis" / "artifacts" / "control-center-integration-audit.json"
)
AUDIT_ARTIFACT = "control-center-integration-audit.v1"
VOLATILE_API_FIELDS = ("generated_at",)


def _summary_value(summary: str, key: str) -> str | None:
    prefix = f"{key}="
    for part in summary.split(";"):
        field = part.strip()
        if field.startswith(prefix):
            return field.removeprefix(prefix)
    return None


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _load_browser_report(path: Path) -> dict[str, object]:
    if not path.exists():
        raise RuntimeError(f"control-center browser evidence report missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_artifact_path(path: str, repo_root: Path) -> Path:
    artifact_path = Path(path)
    if artifact_path.is_absolute():
        return artifact_path
    return repo_root / artifact_path


def _normal_manifest_path(report: dict[str, object], repo_root: Path) -> Path:
    manifest_paths = report.get("manifest_paths")
    if not isinstance(manifest_paths, dict):
        raise RuntimeError("control-center browser evidence report missing manifest_paths")
    normal = manifest_paths.get("normal")
    if not isinstance(normal, str) or not normal:
        raise RuntimeError("control-center browser evidence report missing normal manifest path")
    return _resolve_artifact_path(normal, repo_root)


def _browser_api_snapshot_path(report: dict[str, object], repo_root: Path) -> Path:
    manifest_path = _normal_manifest_path(report, repo_root)
    if not manifest_path.exists():
        raise RuntimeError(f"control-center browser manifest missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    api_snapshot = manifest.get("api_snapshot")
    if not isinstance(api_snapshot, dict):
        raise RuntimeError("control-center browser manifest missing api_snapshot metadata")
    snapshot_path = api_snapshot.get("path")
    if not isinstance(snapshot_path, str) or not snapshot_path:
        raise RuntimeError("control-center browser manifest missing api_snapshot path")
    return _resolve_artifact_path(snapshot_path, repo_root)


def _canonical_payload_bytes(payload: dict[str, object]) -> bytes:
    stable_payload = dict(payload)
    for field in VOLATILE_API_FIELDS:
        stable_payload.pop(field, None)
    return json.dumps(
        stable_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _payload_fingerprint(payload: dict[str, object]) -> str:
    return hashlib.sha256(_canonical_payload_bytes(payload)).hexdigest()


def _verify_browser_api_snapshot_current(
    *,
    current_payload: dict[str, object],
    report: dict[str, object],
    repo_root: Path,
) -> dict[str, object]:
    snapshot_path = _browser_api_snapshot_path(report, repo_root)
    if not snapshot_path.exists():
        raise RuntimeError(f"control-center browser API snapshot missing: {snapshot_path}")
    snapshot_payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    current_hash = _payload_fingerprint(current_payload)
    snapshot_hash = _payload_fingerprint(snapshot_payload)
    if current_hash != snapshot_hash:
        raise RuntimeError(
            "browser API snapshot is stale: "
            f"current={current_hash} snapshot={snapshot_hash} path={snapshot_path}"
        )
    return {
        "match": True,
        "current_sha256": current_hash,
        "snapshot_sha256": snapshot_hash,
        "volatile_fields_ignored": list(VOLATILE_API_FIELDS),
        "path": _relative(snapshot_path, repo_root),
    }


def _payload_counts(payload: dict[str, object]) -> dict[str, object]:
    timeline = payload.get("timeline")
    adapters = payload.get("adapters")
    benefits = payload.get("algorithm_benefits")
    events = payload.get("events")
    return {
        "contract_valid": True,
        "timeline_rows": len(timeline) if isinstance(timeline, list) else 0,
        "adapter_count": len(adapters) if isinstance(adapters, list) else 0,
        "algorithm_benefit_count": len(benefits) if isinstance(benefits, list) else 0,
        "event_total": events.get("total") if isinstance(events, dict) else None,
    }


def build_integration_audit(
    report_path: Path = DEFAULT_BROWSER_REPORT,
    repo_root: Path = REPO_ROOT,
) -> dict[str, object]:
    payload = build_control_center_payload()
    errors = validate_control_center_payload(payload)
    if errors:
        raise RuntimeError("backend payload contract failed: " + "; ".join(errors))

    report = _load_browser_report(report_path)
    package_summary = package_smoke.verify_control_center_evidence_report(
        report_path,
        repo_root=repo_root,
    )
    api_snapshot_fingerprint = _verify_browser_api_snapshot_current(
        current_payload=payload,
        report=report,
        repo_root=repo_root,
    )

    return {
        "artifact": AUDIT_ARTIFACT,
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "ok",
        "contract": {"version": CONTRACT_VERSION, "api_path": API_PATH},
        "backend_payload": _payload_counts(payload),
        "api_snapshot_fingerprint": api_snapshot_fingerprint,
        "browser_evidence": {
            "contract": report.get("contract"),
            "normal_viewports": report.get("normal_viewports"),
            "backend_error_viewport": report.get("error_viewport"),
            "frontend_error_viewport": report.get("frontend_error_viewport"),
            "contract_depth": report.get("contract_depth"),
            "manifest_paths": report.get("manifest_paths"),
            "manifest_records": _summary_value(package_summary, "manifest_records"),
        },
        "package_smoke": {
            "summary": package_summary,
            "manifest_replay": _summary_value(package_summary, "manifest_replay"),
            "contract_depth": _summary_value(package_summary, "contract_depth"),
        },
        "source_artifacts": {
            "browser_report": _relative(report_path, repo_root),
            "browser_api_snapshot": api_snapshot_fingerprint["path"],
        },
    }


def write_integration_audit(
    output_path: Path = DEFAULT_AUDIT_PATH,
    report_path: Path = DEFAULT_BROWSER_REPORT,
    repo_root: Path = REPO_ROOT,
) -> Path:
    audit = build_integration_audit(report_path=report_path, repo_root=repo_root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            audit,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        ) + "\n",
        encoding="utf-8",
    )
    return output_path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Write a machine-readable control-center integration audit."
    )
    parser.add_argument("--report-json", type=Path, default=DEFAULT_BROWSER_REPORT)
    parser.add_argument("--output", type=Path, default=DEFAULT_AUDIT_PATH)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)

    output_path = write_integration_audit(
        output_path=args.output,
        report_path=args.report_json,
        repo_root=args.repo_root,
    )
    print(f"control-center integration audit ok: {output_path}")


if __name__ == "__main__":
    main()
