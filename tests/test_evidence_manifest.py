from __future__ import annotations

import json

from analysis import (
    evidence_manifest,
    evidence_report,
)


def _fake_artifact_metadata(entry: dict) -> dict:
    return {
        key: {"sha256": "0" * 64, "size_bytes": 0}
        for key in entry["artifact_paths"]
    }


def _fill_fake_artifact_metadata(manifest: dict) -> None:
    for entry in manifest["studies"]:
        entry["artifact_metadata"] = _fake_artifact_metadata(entry)
    for entry in manifest["contracts"]:
        entry["artifact_metadata"] = _fake_artifact_metadata(entry)


def test_event_evidence_report_validates_manifest_artifacts(tmp_path, capsys) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is True
    assert "evidence_scope synthetic_sre_event_evidence" in output
    assert "s10_failure_trace section=10 events=16" in output
    assert "s11_catch_sre_wrapper section=11 visible=1.0" in output
    assert "s12_sre_replay section=12 events=11.0 ticks=19" in output
    assert "artifact_check ok studies=3 files=8" in output


def test_event_evidence_report_rejects_artifact_byte_identity_mismatch(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    diagnostics_path = tmp_path / "s11_catch_sre_wrapper_diagnostics.json"
    diagnostics_path.write_text(
        diagnostics_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "artifact_identity_mismatch s11_catch_sre_wrapper_diagnostics.json"
    ) in output
    assert "expected_sha256=" in output
    assert "actual_sha256=" in output
    assert "expected_size_bytes=" in output
    assert "actual_size_bytes=" in output
    assert "artifact_check failed studies=3 artifact_identity=1" in output


def test_event_evidence_report_rejects_missing_artifact_metadata(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _fill_fake_artifact_metadata(manifest)
    manifest["studies"][0].pop("artifact_metadata", None)
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
    assert (
        "invalid_manifest study=s10_failure_trace "
        "missing_study_field=artifact_metadata"
    ) in output
    assert "artifact_check failed studies=3 invalid_manifest=1" in output


def test_event_evidence_report_rejects_artifact_metadata_key_mismatch(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _fill_fake_artifact_metadata(manifest)
    manifest["studies"][0]["artifact_metadata"].pop("full_trace_jsonl")
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
    assert (
        "invalid_manifest study=s10_failure_trace "
        "missing_artifact_metadata_key=full_trace_jsonl"
    ) in output
    assert "artifact_check failed studies=3 invalid_manifest=1" in output


def test_event_evidence_report_rejects_malformed_artifact_metadata(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _fill_fake_artifact_metadata(manifest)
    manifest["studies"][0]["artifact_metadata"]["full_trace_jsonl"][
        "sha256"
    ] = "not-a-sha256"
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
    assert (
        "invalid_manifest study=s10_failure_trace "
        "invalid_artifact_metadata=full_trace_jsonl"
    ) in output
    assert "artifact_check failed studies=3 invalid_manifest=1" in output


def test_event_evidence_report_rejects_missing_artifact(tmp_path, capsys) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    missing_path = tmp_path / "s12_replay_trace.jsonl"
    missing_path.unlink()

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert "missing_artifact s12_replay_trace.jsonl" in output
    assert "artifact_check failed studies=3 missing=1" in output
