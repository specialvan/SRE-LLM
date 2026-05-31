from __future__ import annotations

import hashlib
import subprocess
import sys
import json
from pathlib import Path

import pytest

from scripts import package_smoke
from scripts.package_smoke import build_wheel_and_smoke_imports


def _manifest_records() -> dict[str, dict[str, object]]:
    return {
        "normal": {
            "path": "analysis/artifacts/control-center-browser-smoke-manifest.json",
            "bytes": 1000,
            "sha256": "0" * 64,
        },
        "backend_error": {
            "path": "analysis/artifacts/control-center-browser-error-smoke-manifest.json",
            "bytes": 500,
            "sha256": "1" * 64,
        },
        "frontend_error": {
            "path": "analysis/artifacts/control-center-browser-frontend-error-smoke-manifest.json",
            "bytes": 600,
            "sha256": "2" * 64,
        },
    }


def _control_center_report(manifest_records: dict[str, dict[str, object]] | None = None) -> dict[str, object]:
    return {
        "contract": "control-center.v1 @ /api/control-center",
        "frontend_api_url": "/api/control-center",
        "health_status": "ok",
        "timeline": "12 rows / 12 ticks / 23 events",
        "manifest_paths": {
            "normal": "analysis/artifacts/control-center-browser-smoke-manifest.json",
            "backend_error": "analysis/artifacts/control-center-browser-error-smoke-manifest.json",
            "frontend_error": "analysis/artifacts/control-center-browser-frontend-error-smoke-manifest.json",
        },
        "manifest_records": manifest_records if manifest_records is not None else _manifest_records(),
        "normal_viewports": ["desktop:1440x960:dom93856", "mobile:390x844:dom93856"],
        "error_viewport": "desktop:1440x960:dom59890",
        "frontend_error_viewport": "desktop:1440x960:dom63261",
        "contract_depth": {
            "top_level": 11,
            "object_groups": 5,
            "object_fields": 22,
            "array_item_groups": 7,
            "array_item_fields": 42,
            "timeline_fields": 14,
        },
    }


def _artifact_record(path: Path, root: Path) -> dict[str, object]:
    data = path.read_bytes()
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _write_manifest_artifacts(root: Path) -> dict[str, dict[str, object]]:
    artifacts = {
        "normal": root / "analysis" / "artifacts" / "control-center-browser-smoke-manifest.json",
        "backend_error": root / "analysis" / "artifacts" / "control-center-browser-error-smoke-manifest.json",
        "frontend_error": root / "analysis" / "artifacts" / "control-center-browser-frontend-error-smoke-manifest.json",
    }
    artifacts["normal"].parent.mkdir(parents=True, exist_ok=True)
    artifacts["normal"].write_text("normal manifest", encoding="utf-8")
    artifacts["backend_error"].write_text("backend manifest", encoding="utf-8")
    artifacts["frontend_error"].write_text("frontend manifest", encoding="utf-8")
    return {key: _artifact_record(path, root) for key, path in artifacts.items()}


def test_built_wheel_contains_and_imports_public_packages(tmp_path: Path):
    result = build_wheel_and_smoke_imports(tmp_path)

    assert result.wheel_path.exists()
    assert result.package_imports == ("starship", "sre_control")
    assert "starship/__init__.py" in result.wheel_members
    assert "sre_control/__init__.py" in result.wheel_members


def test_package_smoke_run_fails_loudly_on_timeout(monkeypatch: pytest.MonkeyPatch):
    def fake_run(*args: object, **kwargs: object):
        raise subprocess.TimeoutExpired(cmd=["python"], timeout=1)

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="command timed out"):
        package_smoke._run(["python"], Path("/repo"))


def test_package_smoke_run_decodes_subprocess_output_as_utf8(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict[str, object] = {}

    def fake_run(*args: object, **kwargs: object):
        captured.update(kwargs)
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="星舰", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    package_smoke._run(["python"], Path("/repo"))

    assert captured["encoding"] == "utf-8"
    assert captured["errors"] == "replace"


def test_build_wheel_uses_current_environment_without_build_isolation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    commands: list[list[str]] = []
    envs: list[dict[str, str] | None] = []

    def fake_run(command: list[str], cwd: Path, env: dict[str, str] | None = None):
        commands.append(command)
        envs.append(env)
        wheel_dir = Path(command[command.index("--wheel-dir") + 1])
        wheel_dir.mkdir(parents=True, exist_ok=True)
        (wheel_dir / "starship_recovery-0.1.0-py3-none-any.whl").write_bytes(b"")

    monkeypatch.setattr(package_smoke, "_run", fake_run)

    package_smoke._build_wheel(Path("/repo"), tmp_path)

    assert commands == [
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            ".",
            "--no-index",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(tmp_path / "wheelhouse"),
        ]
    ]
    assert envs[0] is not None
    assert envs[0]["PIP_DISABLE_PIP_VERSION_CHECK"] == "1"
    assert envs[0]["PIP_USE_DEPRECATED"] == "legacy-certs"


def test_package_smoke_verifies_control_center_evidence_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    report = tmp_path / "control-center-browser-evidence-report.json"
    manifest_records = _write_manifest_artifacts(tmp_path)
    monkeypatch.setattr(package_smoke.control_center_browser_smoke, "verify_evidence_manifest", lambda path: None)
    monkeypatch.setattr(package_smoke.control_center_browser_smoke, "verify_error_evidence_manifest", lambda path: None)
    monkeypatch.setattr(package_smoke.control_center_browser_smoke, "verify_frontend_error_evidence_manifest", lambda path: None)
    report.write_text(
        json.dumps(
            {
                "contract": "control-center.v1 @ /api/control-center",
                "frontend_api_url": "/api/control-center",
                "health_status": "ok",
                "timeline": "12 rows / 12 ticks / 23 events",
                "manifest_paths": {
                    "normal": "analysis/artifacts/control-center-browser-smoke-manifest.json",
                    "backend_error": "analysis/artifacts/control-center-browser-error-smoke-manifest.json",
                    "frontend_error": "analysis/artifacts/control-center-browser-frontend-error-smoke-manifest.json",
                },
                "manifest_records": manifest_records,
                "normal_viewports": ["desktop:1440x960:dom93856", "mobile:390x844:dom93856"],
                "error_viewport": "desktop:1440x960:dom59890",
                "frontend_error_viewport": "desktop:1440x960:dom63261",
                "contract_depth": {
                    "top_level": 11,
                    "object_groups": 5,
                    "object_fields": 22,
                    "array_item_groups": 7,
                    "array_item_fields": 42,
                    "timeline_fields": 14,
                },
            }
        ),
        encoding="utf-8",
    )

    summary = package_smoke.verify_control_center_evidence_report(report, repo_root=tmp_path)

    assert summary == "control-center.v1 @ /api/control-center; desktop+mobile; error=desktop:1440x960:dom59890; frontend_error=desktop:1440x960:dom63261; manifest_records=normal+backend_error+frontend_error; manifest_replay=normal+backend_error+frontend_error; contract_depth=top_level:11 object_groups:5 object_fields:22 array_item_groups:7 array_item_fields:42 timeline_fields:14"


def test_package_smoke_replays_control_center_browser_manifests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    report = tmp_path / "control-center-browser-evidence-report.json"
    manifest_records = _write_manifest_artifacts(tmp_path)
    report.write_text(json.dumps(_control_center_report(manifest_records)), encoding="utf-8")
    verified: list[tuple[str, Path]] = []

    monkeypatch.setattr(
        package_smoke.control_center_browser_smoke,
        "verify_evidence_manifest",
        lambda path: verified.append(("normal", path)),
    )
    monkeypatch.setattr(
        package_smoke.control_center_browser_smoke,
        "verify_error_evidence_manifest",
        lambda path: verified.append(("backend_error", path)),
    )
    monkeypatch.setattr(
        package_smoke.control_center_browser_smoke,
        "verify_frontend_error_evidence_manifest",
        lambda path: verified.append(("frontend_error", path)),
    )

    package_smoke.verify_control_center_evidence_report(report, repo_root=tmp_path)

    assert verified == [
        ("normal", tmp_path / "analysis" / "artifacts" / "control-center-browser-smoke-manifest.json"),
        ("backend_error", tmp_path / "analysis" / "artifacts" / "control-center-browser-error-smoke-manifest.json"),
        ("frontend_error", tmp_path / "analysis" / "artifacts" / "control-center-browser-frontend-error-smoke-manifest.json"),
    ]


def test_package_smoke_rejects_stale_control_center_evidence_report(tmp_path: Path):
    report = tmp_path / "control-center-browser-evidence-report.json"
    report.write_text(
        json.dumps(
            {
                "contract": "control-center.v1 @ /api/control-center",
                "frontend_api_url": "/api/stale",
                "health_status": "ok",
                "timeline": "12 rows / 12 ticks / 23 events",
                "manifest_paths": {
                    "normal": "analysis/artifacts/control-center-browser-smoke-manifest.json",
                    "backend_error": "analysis/artifacts/control-center-browser-error-smoke-manifest.json",
                    "frontend_error": "analysis/artifacts/control-center-browser-frontend-error-smoke-manifest.json",
                },
                "manifest_records": _manifest_records(),
                "normal_viewports": ["desktop:1440x960:dom93856", "mobile:390x844:dom93856"],
                "error_viewport": "desktop:1440x960:dom59890",
                "frontend_error_viewport": "desktop:1440x960:dom63261",
                "contract_depth": {
                    "top_level": 11,
                    "object_groups": 5,
                    "object_fields": 22,
                    "array_item_groups": 7,
                    "array_item_fields": 42,
                    "timeline_fields": 14,
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="control-center evidence report mismatch"):
        package_smoke.verify_control_center_evidence_report(report)


def test_package_smoke_rejects_control_center_report_without_contract_depth(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    report = tmp_path / "control-center-browser-evidence-report.json"
    manifest_records = _write_manifest_artifacts(tmp_path)
    monkeypatch.setattr(package_smoke.control_center_browser_smoke, "verify_evidence_manifest", lambda path: None)
    monkeypatch.setattr(package_smoke.control_center_browser_smoke, "verify_error_evidence_manifest", lambda path: None)
    monkeypatch.setattr(package_smoke.control_center_browser_smoke, "verify_frontend_error_evidence_manifest", lambda path: None)
    report.write_text(
        json.dumps(
            {
                "contract": "control-center.v1 @ /api/control-center",
                "frontend_api_url": "/api/control-center",
                "health_status": "ok",
                "timeline": "12 rows / 12 ticks / 23 events",
                "manifest_paths": {
                    "normal": "analysis/artifacts/control-center-browser-smoke-manifest.json",
                    "backend_error": "analysis/artifacts/control-center-browser-error-smoke-manifest.json",
                    "frontend_error": "analysis/artifacts/control-center-browser-frontend-error-smoke-manifest.json",
                },
                "manifest_records": manifest_records,
                "normal_viewports": ["desktop:1440x960:dom93856", "mobile:390x844:dom93856"],
                "error_viewport": "desktop:1440x960:dom59890",
                "frontend_error_viewport": "desktop:1440x960:dom63261",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="contract-depth evidence"):
        package_smoke.verify_control_center_evidence_report(report, repo_root=tmp_path)


def test_package_smoke_rejects_control_center_report_without_manifest_provenance(tmp_path: Path):
    report = tmp_path / "control-center-browser-evidence-report.json"
    report.write_text(
        json.dumps(
            {
                "contract": "control-center.v1 @ /api/control-center",
                "frontend_api_url": "/api/control-center",
                "health_status": "ok",
                "timeline": "12 rows / 12 ticks / 23 events",
                "normal_viewports": ["desktop:1440x960:dom93856", "mobile:390x844:dom93856"],
                "error_viewport": "desktop:1440x960:dom59890",
                "frontend_error_viewport": "desktop:1440x960:dom63261",
                "contract_depth": {
                    "top_level": 11,
                    "object_groups": 5,
                    "object_fields": 22,
                    "array_item_groups": 7,
                    "array_item_fields": 42,
                    "timeline_fields": 14,
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="manifest provenance"):
        package_smoke.verify_control_center_evidence_report(report)


def test_package_smoke_rejects_control_center_report_without_manifest_records(tmp_path: Path):
    report = tmp_path / "control-center-browser-evidence-report.json"
    report.write_text(
        json.dumps(
            {
                "contract": "control-center.v1 @ /api/control-center",
                "frontend_api_url": "/api/control-center",
                "health_status": "ok",
                "timeline": "12 rows / 12 ticks / 23 events",
                "manifest_paths": {
                    "normal": "analysis/artifacts/control-center-browser-smoke-manifest.json",
                    "backend_error": "analysis/artifacts/control-center-browser-error-smoke-manifest.json",
                    "frontend_error": "analysis/artifacts/control-center-browser-frontend-error-smoke-manifest.json",
                },
                "normal_viewports": ["desktop:1440x960:dom93856", "mobile:390x844:dom93856"],
                "error_viewport": "desktop:1440x960:dom59890",
                "frontend_error_viewport": "desktop:1440x960:dom63261",
                "contract_depth": {
                    "top_level": 11,
                    "object_groups": 5,
                    "object_fields": 22,
                    "array_item_groups": 7,
                    "array_item_fields": 42,
                    "timeline_fields": 14,
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="manifest record"):
        package_smoke.verify_control_center_evidence_report(report)


def test_package_smoke_rejects_control_center_report_with_stale_manifest_record(tmp_path: Path):
    report = tmp_path / "control-center-browser-evidence-report.json"
    records = _write_manifest_artifacts(tmp_path)
    records["normal"]["sha256"] = "0" * 64
    report.write_text(json.dumps(_control_center_report(records)), encoding="utf-8")

    with pytest.raises(RuntimeError, match="stale manifest record"):
        package_smoke.verify_control_center_evidence_report(report, repo_root=tmp_path)


def test_package_smoke_main_reports_control_center_evidence(monkeypatch: pytest.MonkeyPatch, capsys):
    wheel = Path("starship_recovery-0.1.0-py3-none-any.whl")
    monkeypatch.setattr(
        package_smoke,
        "build_wheel_and_smoke_imports",
        lambda work_dir: package_smoke.PackageSmokeResult(
            wheel_path=wheel,
            wheel_members=frozenset({"starship/__init__.py", "sre_control/__init__.py"}),
            package_imports=("starship", "sre_control"),
        ),
    )
    monkeypatch.setattr(
        package_smoke,
        "verify_control_center_evidence_report",
        lambda: "control-center.v1 @ /api/control-center; desktop+mobile; error=desktop:1440x960:dom59890; frontend_error=desktop:1440x960:dom63261; manifest_records=normal+backend_error+frontend_error; manifest_replay=normal+backend_error+frontend_error; contract_depth=top_level:11 object_groups:5 object_fields:22 array_item_groups:7 array_item_fields:42 timeline_fields:14",
    )

    package_smoke.main()
    output = capsys.readouterr().out

    assert "package smoke ok: starship_recovery-0.1.0-py3-none-any.whl" in output
    assert "control-center evidence ok: control-center.v1 @ /api/control-center" in output
