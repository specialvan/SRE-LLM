from __future__ import annotations

import json

import pytest

from analysis import evidence_manifest, evidence_report


def test_event_evidence_report_rejects_missing_top_level_studies(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("studies")
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=manifest_path,
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert "invalid_manifest missing_top_level_field=studies" in output
    assert "artifact_check failed studies=0 invalid_manifest=1" in output


def test_event_evidence_report_rejects_malformed_manifest_json(
    tmp_path, capsys
) -> None:
    manifest_path = tmp_path / "event_evidence_manifest.json"
    manifest_path.write_text("{not-json", encoding="utf-8")

    try:
        ok = evidence_report.main(
            manifest_path=manifest_path,
            repo_root=tmp_path,
        )
    except json.JSONDecodeError as exc:
        pytest.fail(f"report crashed instead of rejecting malformed manifest: {exc}")
    output = capsys.readouterr().out

    assert ok is False
    assert "invalid_manifest malformed_json" in output
    assert "artifact_check failed studies=0 invalid_manifest=1" in output


def test_event_evidence_report_rejects_missing_manifest_file(
    tmp_path, capsys
) -> None:
    manifest_path = tmp_path / "event_evidence_manifest.json"

    try:
        ok = evidence_report.main(
            manifest_path=manifest_path,
            repo_root=tmp_path,
        )
    except FileNotFoundError as exc:
        pytest.fail(f"report crashed instead of rejecting missing manifest: {exc}")
    output = capsys.readouterr().out

    assert ok is False
    assert f"invalid_manifest missing_manifest {manifest_path}" in output
    assert "artifact_check failed studies=0 invalid_manifest=1" in output
