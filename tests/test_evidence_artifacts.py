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


def test_s10_trace_shape_allows_float_accumulation_drift(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(evidence_artifacts.s10_failure_trace, "DT", 0.1)
    tick = 1_000
    accumulated_time = tick * 0.1 + 2e-9
    trace_path = tmp_path / "s10_trace_full.jsonl"
    trace_path.write_text(
        json.dumps({"tick": tick, "t_seconds": accumulated_time}) + "\n",
        encoding="utf-8",
    )

    errors = evidence_artifacts._s10_trace_shape_errors(
        trace_path,
        "s10_trace_full.jsonl",
    )

    assert errors == []


def test_s10_trace_shape_collects_all_invalid_rows(tmp_path) -> None:
    trace_path = tmp_path / "s10_trace_full.jsonl"
    trace_path.write_text(
        "\n".join(
            [
                json.dumps({"tick": -1, "t_seconds": 0.0}),
                json.dumps({"tick": 1, "t_seconds": -0.1}),
                json.dumps({"tick": 2, "t_seconds": 999.0}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    errors = evidence_artifacts._s10_trace_shape_errors(
        trace_path,
        "s10_trace_full.jsonl",
    )

    assert errors == [
        "invalid_artifact s10_trace_full.jsonl line=1 invalid_trace_field=tick",
        "invalid_artifact s10_trace_full.jsonl line=2 invalid_trace_field=t_seconds",
        "invalid_artifact s10_trace_full.jsonl line=3 trace_time_mismatch",
    ]


def test_jsonl_validation_collects_all_invalid_rows(tmp_path) -> None:
    trace_path = tmp_path / "bad.jsonl"
    trace_path.write_text(
        "\n".join(
            [
                "{not-json",
                json.dumps(["not", "object"]),
                json.dumps({"valid": True}),
                json.dumps(5),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    errors = evidence_artifacts._invalid_jsonl_errors(trace_path, "bad.jsonl")

    assert errors == [
        "invalid_artifact bad.jsonl line=1",
        "invalid_artifact bad.jsonl line=2 top_level_must_be_object",
        "invalid_artifact bad.jsonl line=4 top_level_must_be_object",
    ]


def test_s12_fixture_shape_collects_all_invalid_rows(tmp_path) -> None:
    fixture_path = tmp_path / "sre_replay.jsonl"
    fixture_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "expected_kind": "missing_sensor",
                        "expected_kinds": ["missing_sensor"],
                    }
                ),
                json.dumps({"expected_kinds": []}),
                json.dumps({"expected_kind": ""}),
                json.dumps({"expected_kind": "not_registered"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    errors = evidence_artifacts._s12_fixture_shape_errors(
        fixture_path,
        "sre_replay.jsonl",
    )

    assert errors == [
        (
            "invalid_artifact sre_replay.jsonl line=1 "
            "invalid_fixture_field=expected_kind_conflict"
        ),
        "invalid_artifact sre_replay.jsonl line=2 invalid_fixture_field=expected_kinds",
        "invalid_artifact sre_replay.jsonl line=3 invalid_fixture_field=expected_kind",
        (
            "invalid_artifact sre_replay.jsonl line=4 "
            "unknown_fixture_expected_kind=not_registered"
        ),
    ]


def test_schema_validation_collects_all_invalid_s10_events(tmp_path) -> None:
    trace_path = tmp_path / "s10_trace_full.jsonl"
    trace_path.write_text(
        "\n".join(
            [
                json.dumps({"tick": 0, "t_seconds": 0.0}),
                json.dumps({"tick": 1, "t_seconds": 5.0, "kind": "missing_sensor"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    entry = {
        "study": "s10_failure_trace",
        "artifact_paths": {"full_trace_jsonl": "s10_trace_full.jsonl"},
    }

    errors = evidence_artifacts.schema_invalid_event_errors(entry, tmp_path)

    assert errors == [
        "schema_invalid_event s10_trace_full.jsonl line=1",
        "schema_invalid_event s10_trace_full.jsonl line=2",
    ]
