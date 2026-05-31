from __future__ import annotations

import json

from analysis import evidence_consistency, evidence_manifest


def _generated_manifest(tmp_path) -> dict:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    return json.loads(result["manifest_path"].read_text(encoding="utf-8"))


def test_study_consistency_errors_accept_generated_studies(tmp_path):
    manifest = _generated_manifest(tmp_path)

    errors = [
        error
        for entry in manifest["studies"]
        for error in evidence_consistency.study_consistency_errors(entry, tmp_path)
    ]

    assert errors == []


def test_recovery_diagnostics_uses_strict_json_null_for_unrecovered_window():
    rows = [{"expected_kind": "missing_sensor"}]
    trace_rows = [{"runtime": {"events": [{"kind": "missing_sensor"}]}}]

    diagnostics = evidence_consistency._recovery_diagnostics(rows, trace_rows)

    assert diagnostics["recovered_window_fraction"] == 0.0
    assert diagnostics["max_recovery_ticks"] is None
    json.dumps(diagnostics, allow_nan=False)


def test_multi_signal_diagnostics_uses_strict_json_null_for_unrecovered_window():
    rows = [
        {
            "incident_id": "compound",
            "expected_kinds": ["missing_sensor", "replica_bound_active"],
        }
    ]
    trace_rows = [
        {
            "runtime": {
                "events": [
                    {"kind": "missing_sensor"},
                    {"kind": "replica_bound_active"},
                ]
            }
        }
    ]

    diagnostics = evidence_consistency._multi_signal_window_diagnostics(
        rows,
        trace_rows,
    )

    assert diagnostics["multi_signal_window_recovered_fraction"] == 0.0
    assert diagnostics["max_multi_signal_recovery_ticks"] is None
    json.dumps(diagnostics, allow_nan=False)


def test_study_consistency_errors_rejects_s10_sample_trace_prefix_drift(tmp_path):
    manifest = _generated_manifest(tmp_path)
    s10_entry = next(
        entry for entry in manifest["studies"] if entry["study"] == "s10_failure_trace"
    )
    sample_path = tmp_path / "s10_trace_sample.jsonl"
    sample_rows = [
        json.loads(line)
        for line in sample_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    sample_rows[0]["tick"] = sample_rows[0]["tick"] + 1
    sample_path.write_text(
        chr(10).join(json.dumps(row, sort_keys=True) for row in sample_rows)
        + chr(10),
        encoding="utf-8",
    )

    errors = evidence_consistency.study_consistency_errors(s10_entry, tmp_path)

    assert errors == [
        "inconsistent_artifact s10_trace_sample.jsonl "
        "sample_trace_prefix_mismatch"
    ]


def test_study_consistency_errors_rejects_s12_operator_action_coverage_drift(
    tmp_path,
):
    manifest = _generated_manifest(tmp_path)
    s12_entry = next(
        entry for entry in manifest["studies"] if entry["study"] == "s12_sre_replay"
    )
    diagnostics_path = tmp_path / "s12_replay_diagnostics.json"
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    diagnostics["operator_action_coverage"] = 0.0
    diagnostics_path.write_text(
        json.dumps(diagnostics, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    errors = evidence_consistency.study_consistency_errors(s12_entry, tmp_path)

    assert errors == [
        "inconsistent_artifact s12_replay_diagnostics.json "
        "operator_action_coverage_mismatch"
    ]
