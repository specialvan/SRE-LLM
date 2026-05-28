from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import control_center_integration_audit


def _browser_report() -> dict[str, object]:
    return {
        "contract": "control-center.v1 @ /api/control-center",
        "frontend_api_url": "/api/control-center",
        "health_status": "ok",
        "timeline": "12 rows / 12 ticks / 23 events",
        "normal_viewports": ["desktop:1440x960:dom97245", "mobile:390x844:dom97245"],
        "error_viewport": "desktop:1440x960:dom63279",
        "frontend_error_viewport": "desktop:1440x960:dom63261",
        "manifest_paths": {
            "normal": "analysis/artifacts/control-center-browser-smoke-manifest.json",
            "backend_error": "analysis/artifacts/control-center-browser-error-smoke-manifest.json",
            "frontend_error": "analysis/artifacts/control-center-browser-frontend-error-smoke-manifest.json",
        },
        "manifest_records": {
            "normal": {"path": "analysis/artifacts/control-center-browser-smoke-manifest.json", "bytes": 1, "sha256": "0" * 64},
            "backend_error": {"path": "analysis/artifacts/control-center-browser-error-smoke-manifest.json", "bytes": 1, "sha256": "1" * 64},
            "frontend_error": {"path": "analysis/artifacts/control-center-browser-frontend-error-smoke-manifest.json", "bytes": 1, "sha256": "2" * 64},
        },
        "contract_depth": {
            "top_level": 11,
            "object_groups": 5,
            "object_fields": 21,
            "array_item_groups": 7,
            "array_item_fields": 36,
            "timeline_fields": 14,
        },
    }


def _package_summary() -> str:
    return (
        "control-center.v1 @ /api/control-center; desktop+mobile; "
        "error=desktop:1440x960:dom63279; frontend_error=desktop:1440x960:dom63261; "
        "manifest_records=normal+backend_error+frontend_error; "
        "manifest_replay=normal+backend_error+frontend_error; "
        "contract_depth=top_level:11 object_groups:5 object_fields:21 "
        "array_item_groups:7 array_item_fields:36 timeline_fields:14"
    )


def _write_browser_report_with_snapshot(
    tmp_path: Path,
    payload: dict[str, object] | None = None,
) -> Path:
    payload = payload or control_center_integration_audit.build_control_center_payload()
    artifacts = tmp_path / "analysis" / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)

    api_snapshot = artifacts / "control-center-browser-smoke-api.json"
    api_snapshot.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    manifest = artifacts / "control-center-browser-smoke-manifest.json"
    manifest.write_text(
        json.dumps(
            {"api_snapshot": {"path": "analysis/artifacts/control-center-browser-smoke-api.json"}},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report_path = tmp_path / "browser-report.json"
    report_path.write_text(json.dumps(_browser_report()), encoding="utf-8")
    return report_path


def test_control_center_integration_audit_aggregates_backend_browser_and_package_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    report_path = _write_browser_report_with_snapshot(tmp_path)
    package_summary = _package_summary()

    monkeypatch.setattr(
        control_center_integration_audit.package_smoke,
        "verify_control_center_evidence_report",
        lambda path, repo_root=None: package_summary,
    )

    audit = control_center_integration_audit.build_integration_audit(
        report_path=report_path,
        repo_root=tmp_path,
    )

    assert audit["status"] == "ok"
    assert audit["contract"] == {
        "version": "control-center.v1",
        "api_path": "/api/control-center",
    }
    assert audit["backend_payload"]["contract_valid"] is True
    assert audit["backend_payload"]["timeline_rows"] == 12
    assert audit["backend_payload"]["adapter_count"] == 8
    assert audit["backend_payload"]["algorithm_benefit_count"] == 8
    assert audit["browser_evidence"]["normal_viewports"] == [
        "desktop:1440x960:dom97245",
        "mobile:390x844:dom97245",
    ]
    assert audit["browser_evidence"]["backend_error_viewport"] == "desktop:1440x960:dom63279"
    assert audit["browser_evidence"]["frontend_error_viewport"] == "desktop:1440x960:dom63261"
    assert audit["browser_evidence"]["manifest_records"] == "normal+backend_error+frontend_error"
    assert audit["api_snapshot_fingerprint"]["match"] is True
    assert audit["api_snapshot_fingerprint"]["volatile_fields_ignored"] == ["generated_at"]
    assert audit["package_smoke"]["manifest_replay"] == "normal+backend_error+frontend_error"
    assert audit["package_smoke"]["summary"] == package_summary


def test_control_center_integration_audit_fails_when_backend_payload_contract_breaks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    report_path = _write_browser_report_with_snapshot(tmp_path)

    def broken_payload() -> dict[str, object]:
        return {"frontend_contract": {"timeline_required_fields": []}, "timeline": []}

    monkeypatch.setattr(
        control_center_integration_audit,
        "build_control_center_payload",
        broken_payload,
    )

    with pytest.raises(RuntimeError, match="backend payload contract failed"):
        control_center_integration_audit.build_integration_audit(
            report_path=report_path,
            repo_root=tmp_path,
        )


def test_control_center_integration_audit_rejects_stale_browser_api_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    stale_payload = control_center_integration_audit.build_control_center_payload()
    stale_payload["summary"]["current_replicas"] = stale_payload["summary"]["current_replicas"] + 1
    report_path = _write_browser_report_with_snapshot(tmp_path, payload=stale_payload)

    monkeypatch.setattr(
        control_center_integration_audit.package_smoke,
        "verify_control_center_evidence_report",
        lambda path, repo_root=None: _package_summary(),
    )

    with pytest.raises(RuntimeError, match="browser API snapshot is stale"):
        control_center_integration_audit.build_integration_audit(
            report_path=report_path,
            repo_root=tmp_path,
        )


def test_control_center_integration_audit_writes_stable_json_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    report_path = _write_browser_report_with_snapshot(tmp_path)
    output_path = tmp_path / "analysis" / "artifacts" / "control-center-integration-audit.json"

    monkeypatch.setattr(
        control_center_integration_audit.package_smoke,
        "verify_control_center_evidence_report",
        lambda path, repo_root=None: _package_summary(),
    )

    written = control_center_integration_audit.write_integration_audit(
        output_path=output_path,
        report_path=report_path,
        repo_root=tmp_path,
    )

    assert written == output_path
    artifact = json.loads(output_path.read_text(encoding="utf-8"))
    assert artifact["artifact"] == "control-center-integration-audit.v1"
    assert artifact["status"] == "ok"
    first_bytes = output_path.read_bytes()
    written_again = control_center_integration_audit.write_integration_audit(
        output_path=output_path,
        report_path=report_path,
        repo_root=tmp_path,
    )

    assert written_again == output_path
    assert output_path.read_bytes() == first_bytes
    assert artifact["source_artifacts"]["browser_report"] == "browser-report.json"
    assert artifact["source_artifacts"]["browser_api_snapshot"] == "analysis/artifacts/control-center-browser-smoke-api.json"
