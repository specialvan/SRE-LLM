from __future__ import annotations

import importlib
import json


def test_control_center_browser_smoke_can_verify_manifest_without_browser(
    monkeypatch, tmp_path, capsys
):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")
    verified = []

    monkeypatch.setattr(smoke, "sync_playwright", None)
    monkeypatch.setattr(
        smoke,
        "find_system_browser",
        lambda: (_ for _ in ()).throw(AssertionError("browser lookup should not run")),
    )
    monkeypatch.setattr(
        smoke,
        "_start_server",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("server should not start")),
    )
    monkeypatch.setattr(smoke, "verify_evidence_manifest", lambda path: verified.append(path))

    exit_code = smoke.main(["--verify-manifest", str(manifest_path)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert verified == [manifest_path]
    assert f"manifest replay passed: {manifest_path}" in output


def test_control_center_browser_smoke_can_verify_error_manifest_without_browser(
    monkeypatch, tmp_path, capsys
):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    manifest_path = tmp_path / "error-manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")
    verified = []

    monkeypatch.setattr(
        smoke,
        "find_system_browser",
        lambda: (_ for _ in ()).throw(AssertionError("browser lookup should not run")),
    )
    monkeypatch.setattr(
        smoke,
        "_start_server",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("server should not start")),
    )
    monkeypatch.setattr(smoke, "verify_error_evidence_manifest", lambda path: verified.append(path))

    exit_code = smoke.main(["--verify-error-manifest", str(manifest_path)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert verified == [manifest_path]
    assert f"error manifest replay passed: {manifest_path}" in output


def test_control_center_browser_smoke_can_verify_all_manifests_without_browser(
    monkeypatch, tmp_path, capsys
):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    normal_manifest = tmp_path / "normal-manifest.json"
    error_manifest = tmp_path / "error-manifest.json"
    frontend_error_manifest = tmp_path / "frontend-error-manifest.json"
    normal_manifest.write_text("{}", encoding="utf-8")
    error_manifest.write_text("{}", encoding="utf-8")
    frontend_error_manifest.write_text("{}", encoding="utf-8")
    verified = []

    monkeypatch.setattr(
        smoke,
        "find_system_browser",
        lambda: (_ for _ in ()).throw(AssertionError("browser lookup should not run")),
    )
    monkeypatch.setattr(
        smoke,
        "_start_server",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("server should not start")),
    )
    monkeypatch.setattr(smoke, "verify_evidence_manifest", lambda path: verified.append(("normal", path)))
    monkeypatch.setattr(smoke, "verify_error_evidence_manifest", lambda path: verified.append(("error", path)))
    monkeypatch.setattr(
        smoke,
        "verify_frontend_error_evidence_manifest",
        lambda path: verified.append(("frontend-error", path)),
    )

    exit_code = smoke.main(
        [
            "--verify-all-manifests",
            "--manifest",
            str(normal_manifest),
            "--error-manifest",
            str(error_manifest),
            "--frontend-error-manifest",
            str(frontend_error_manifest),
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert verified == [
        ("normal", normal_manifest),
        ("error", error_manifest),
        ("frontend-error", frontend_error_manifest),
    ]
    assert f"all manifests replay passed: {normal_manifest} + {error_manifest} + {frontend_error_manifest}" in output


def test_build_evidence_report_summarizes_normal_and_error_manifests(tmp_path):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    normal = tmp_path / "normal.json"
    error = tmp_path / "error.json"
    frontend_error = tmp_path / "frontend-error.json"
    normal.write_text(
        json.dumps(
            {
                "contract": {"version": "control-center.v1", "api_path": "/api/control-center"},
                "api_snapshot": {"path": "api.json"},
                "summary": {"ticks": 12, "timeline_rows": 12, "events_total": 23},
                "frontend_response": {"api_url": "/api/control-center"},
                "health_response": {"payload": {"status": "ok"}},
                "viewports": [
                    {
                        "name": "desktop",
                        "screenshot": {"png": {"width": 1440, "height": 960, "blank": False}},
                        "dom_dump": {"bytes": 100},
                    },
                    {
                        "name": "mobile",
                        "screenshot": {"png": {"width": 390, "height": 844, "blank": False}},
                        "dom_dump": {"bytes": 90},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "api.json").write_text(
        json.dumps(
            {
                "frontend_contract": {
                    "top_level_required_fields": ["summary", "timeline", "series"],
                    "object_required_fields": {
                        "summary": ["ticks", "current_replicas"],
                        "series": ["replicas"],
                    },
                    "array_item_required_fields": {
                        "events.kinds": ["kind", "count"],
                        "timeline.event_details": ["tick"],
                    },
                    "timeline_required_fields": ["tick", "observed_rps", "alloc_shares", "event_details"],
                }
            }
        ),
        encoding="utf-8",
    )
    error.write_text(
        json.dumps(
            {
                "mode": "contract-error",
                "viewport": {"name": "desktop", "width": 1440, "height": 960},
                "screenshot": {"png": {"width": 1440, "height": 960, "blank": False}},
                "dom_dump": {"bytes": 80},
            }
        ),
        encoding="utf-8",
    )
    frontend_error.write_text(
        json.dumps(
            {
                "mode": "frontend-contract-error",
                "viewport": {"name": "desktop", "width": 1440, "height": 960},
                "screenshot": {"png": {"width": 1440, "height": 960, "blank": False}},
                "dom_dump": {"bytes": 70},
            }
        ),
        encoding="utf-8",
    )

    report = smoke.build_evidence_report(normal, error, frontend_error)

    assert report == {
        "contract": "control-center.v1 @ /api/control-center",
        "manifest_paths": {
            "normal": str(normal),
            "backend_error": str(error),
            "frontend_error": str(frontend_error),
        },
        "manifest_records": {
            "normal": smoke._artifact_record(normal, base_dir=normal.parent),
            "backend_error": smoke._artifact_record(error, base_dir=normal.parent),
            "frontend_error": smoke._artifact_record(frontend_error, base_dir=normal.parent),
        },
        "frontend_api_url": "/api/control-center",
        "health_status": "ok",
        "timeline": "12 rows / 12 ticks / 23 events",
        "normal_viewports": ["desktop:1440x960:dom100", "mobile:390x844:dom90"],
        "error_viewport": "desktop:1440x960:dom80",
        "frontend_error_viewport": "desktop:1440x960:dom70",
        "contract_depth": {
            "top_level": 3,
            "object_groups": 2,
            "object_fields": 3,
            "array_item_groups": 2,
            "array_item_fields": 3,
            "timeline_fields": 4,
        },
    }


def test_control_center_browser_smoke_reports_all_manifest_summary(monkeypatch, tmp_path, capsys):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    normal_manifest = tmp_path / "normal-manifest.json"
    error_manifest = tmp_path / "error-manifest.json"
    report_path = tmp_path / "report.json"
    normal_manifest.write_text("{}", encoding="utf-8")
    error_manifest.write_text("{}", encoding="utf-8")
    report = {
        "contract": "control-center.v1 @ /api/control-center",
        "manifest_paths": {
            "normal": "analysis/artifacts/control-center-browser-smoke-manifest.json",
            "backend_error": "analysis/artifacts/control-center-browser-error-smoke-manifest.json",
            "frontend_error": "analysis/artifacts/control-center-browser-frontend-error-smoke-manifest.json",
        },
        "manifest_records": {
            "normal": {"path": "analysis/artifacts/control-center-browser-smoke-manifest.json", "bytes": 1000, "sha256": "0" * 64},
            "backend_error": {"path": "analysis/artifacts/control-center-browser-error-smoke-manifest.json", "bytes": 500, "sha256": "1" * 64},
            "frontend_error": {"path": "analysis/artifacts/control-center-browser-frontend-error-smoke-manifest.json", "bytes": 600, "sha256": "2" * 64},
        },
        "frontend_api_url": "/api/control-center",
        "health_status": "ok",
        "timeline": "12 rows / 12 ticks / 23 events",
        "normal_viewports": ["desktop:1440x960:dom100"],
        "error_viewport": "desktop:1440x960:dom80",
        "frontend_error_viewport": "desktop:1440x960:dom70",
        "contract_depth": {"top_level": 3, "object_groups": 2, "object_fields": 3, "array_item_groups": 2, "array_item_fields": 3, "timeline_fields": 4},
    }

    monkeypatch.setattr(smoke, "verify_evidence_manifest", lambda path: None)
    monkeypatch.setattr(smoke, "verify_error_evidence_manifest", lambda path: None)
    monkeypatch.setattr(smoke, "verify_frontend_error_evidence_manifest", lambda path: None)
    monkeypatch.setattr(smoke, "build_evidence_report", lambda normal, error, frontend_error: report)
    monkeypatch.setattr(
        smoke,
        "find_system_browser",
        lambda: (_ for _ in ()).throw(AssertionError("browser lookup should not run")),
    )

    exit_code = smoke.main(
        [
            "--report-manifests",
            "--manifest",
            str(normal_manifest),
            "--error-manifest",
            str(error_manifest),
            "--frontend-error-manifest",
            str(tmp_path / "frontend-error-manifest.json"),
            "--report-json",
            str(report_path),
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "evidence report:" in output
    assert "control-center.v1 @ /api/control-center" in output
    assert "desktop:1440x960:dom100" in output
    assert "error=desktop:1440x960:dom80" in output
    assert "frontend_error=desktop:1440x960:dom70" in output
    assert "manifest_paths=normal:analysis/artifacts/control-center-browser-smoke-manifest.json backend_error:analysis/artifacts/control-center-browser-error-smoke-manifest.json frontend_error:analysis/artifacts/control-center-browser-frontend-error-smoke-manifest.json" in output
    assert "manifest_records=normal:1000:000000000000 backend_error:500:111111111111 frontend_error:600:222222222222" in output
    assert "manifest_replay=normal+backend_error+frontend_error" in output
    assert "contract_depth=top_level:3 object_groups:2 object_fields:3 array_item_groups:2 array_item_fields:3 timeline_fields:4" in output


def test_control_center_browser_smoke_writes_json_report_after_replay(monkeypatch, tmp_path, capsys):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    normal_manifest = tmp_path / "normal-manifest.json"
    error_manifest = tmp_path / "error-manifest.json"
    frontend_error_manifest = tmp_path / "frontend-error-manifest.json"
    report_path = tmp_path / "report.json"
    normal_manifest.write_text("{}", encoding="utf-8")
    error_manifest.write_text("{}", encoding="utf-8")
    frontend_error_manifest.write_text("{}", encoding="utf-8")
    report = {
        "contract": "control-center.v1 @ /api/control-center",
        "manifest_paths": {
            "normal": "analysis/artifacts/control-center-browser-smoke-manifest.json",
            "backend_error": "analysis/artifacts/control-center-browser-error-smoke-manifest.json",
            "frontend_error": "analysis/artifacts/control-center-browser-frontend-error-smoke-manifest.json",
        },
        "manifest_records": {
            "normal": {"path": "analysis/artifacts/control-center-browser-smoke-manifest.json", "bytes": 1000, "sha256": "0" * 64},
            "backend_error": {"path": "analysis/artifacts/control-center-browser-error-smoke-manifest.json", "bytes": 500, "sha256": "1" * 64},
            "frontend_error": {"path": "analysis/artifacts/control-center-browser-frontend-error-smoke-manifest.json", "bytes": 600, "sha256": "2" * 64},
        },
        "frontend_api_url": "/api/control-center",
        "health_status": "ok",
        "timeline": "12 rows / 12 ticks / 23 events",
        "normal_viewports": ["desktop:1440x960:dom100"],
        "error_viewport": "desktop:1440x960:dom80",
        "frontend_error_viewport": "desktop:1440x960:dom70",
        "contract_depth": {"top_level": 3, "object_groups": 2, "object_fields": 3, "array_item_groups": 2, "array_item_fields": 3, "timeline_fields": 4},
    }

    monkeypatch.setattr(smoke, "verify_evidence_manifest", lambda path: None)
    monkeypatch.setattr(smoke, "verify_error_evidence_manifest", lambda path: None)
    monkeypatch.setattr(smoke, "verify_frontend_error_evidence_manifest", lambda path: None)
    monkeypatch.setattr(smoke, "build_evidence_report", lambda normal, error, frontend_error: report)
    monkeypatch.setattr(
        smoke,
        "find_system_browser",
        lambda: (_ for _ in ()).throw(AssertionError("browser lookup should not run")),
    )

    exit_code = smoke.main(
        [
            "--report-manifests",
            "--report-json",
            str(report_path),
            "--manifest",
            str(normal_manifest),
            "--error-manifest",
            str(error_manifest),
            "--frontend-error-manifest",
            str(frontend_error_manifest),
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert json.loads(report_path.read_text(encoding="utf-8")) == report
    assert f"evidence report json: {report_path}" in output
