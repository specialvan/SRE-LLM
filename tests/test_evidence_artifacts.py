from __future__ import annotations

import json

from analysis import evidence_artifacts, evidence_manifest


def test_artifact_identity_errors_reports_stale_metadata(tmp_path):
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest = json.loads(result["manifest_path"].read_text(encoding="utf-8"))
    manifest["studies"][0]["artifact_metadata"]["full_trace_jsonl"] = {
        "sha256": "0" * 64,
        "size_bytes": 0,
    }

    errors = evidence_artifacts.artifact_identity_errors(manifest, tmp_path)

    assert len(errors) == 1
    assert errors[0].startswith(
        "artifact_identity_mismatch s10_trace_full.jsonl "
        "expected_sha256=0000000000000000000000000000000000000000000000000000000000000000 "
    )
    assert "expected_size_bytes=0" in errors[0]
    assert "actual_size_bytes=" in errors[0]


def test_invalid_artifact_errors_rejects_malformed_s12_fixture(tmp_path):
    fixture_path = tmp_path / "sre_replay.jsonl"
    fixture_path.write_text(
        json.dumps({"expected_kind": "not_registered"}) + "\n",
        encoding="utf-8",
    )
    entry = {
        "study": "s12_sre_replay",
        "artifact_paths": {"fixture_jsonl": "sre_replay.jsonl"},
    }

    errors = evidence_artifacts.invalid_artifact_errors(entry, tmp_path)

    assert errors == [
        "invalid_artifact sre_replay.jsonl line=1 "
        "unknown_fixture_expected_kind=not_registered"
    ]


def test_schema_invalid_event_errors_rejects_runtime_event_shape(tmp_path):
    trace_path = tmp_path / "s10_trace_full.jsonl"
    trace_path.write_text(
        json.dumps({"tick": 0, "t_seconds": 0.0, "kind": "missing_sensor"})
        + "\n",
        encoding="utf-8",
    )
    entry = {
        "study": "s10_failure_trace",
        "artifact_paths": {"full_trace_jsonl": "s10_trace_full.jsonl"},
    }

    errors = evidence_artifacts.schema_invalid_event_errors(entry, tmp_path)

    assert errors == ["schema_invalid_event s10_trace_full.jsonl line=1"]
