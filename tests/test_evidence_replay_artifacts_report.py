from __future__ import annotations

import json
from pathlib import Path

import pytest

from analysis import evidence_manifest, evidence_report

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_event_evidence_report_rejects_inconsistent_artifact_content(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    (tmp_path / "s12_replay_trace.jsonl").write_text("{}\n", encoding="utf-8")

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert "inconsistent_artifact s12_replay_trace.jsonl expected_lines=19 actual_lines=1" in output
    assert "artifact_check failed studies=3 inconsistent=1" in output


def test_event_evidence_report_rejects_malformed_jsonl_artifact(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    trace_path = tmp_path / "s12_replay_trace.jsonl"
    lines = trace_path.read_text(encoding="utf-8").splitlines()
    lines[0] = "{not-json"
    trace_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert "invalid_artifact s12_replay_trace.jsonl line=1" in output
    assert "artifact_check failed studies=3 invalid=1" in output


def test_event_evidence_report_rejects_non_object_jsonl_row(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    trace_path = tmp_path / "s12_replay_trace.jsonl"
    lines = trace_path.read_text(encoding="utf-8").splitlines()
    lines[0] = "[]"
    trace_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    try:
        ok = evidence_report.main(
            manifest_path=result["manifest_path"],
            repo_root=tmp_path,
        )
    except AttributeError as exc:
        pytest.fail(f"report crashed instead of rejecting JSONL row shape: {exc}")
    output = capsys.readouterr().out

    assert ok is False
    assert "invalid_artifact s12_replay_trace.jsonl line=1 top_level_must_be_object" in output
    assert "artifact_check failed studies=3 invalid=1" in output


def test_event_evidence_report_rejects_invalid_s12_trace_runtime_shape(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    trace_path = tmp_path / "s12_replay_trace.jsonl"
    rows = [
        json.loads(line)
        for line in trace_path.read_text(encoding="utf-8").splitlines()
    ]
    rows[0]["runtime"] = "not-a-runtime-object"
    trace_path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )

    try:
        ok = evidence_report.main(
            manifest_path=result["manifest_path"],
            repo_root=tmp_path,
        )
    except AttributeError as exc:
        pytest.fail(f"report crashed instead of rejecting runtime shape: {exc}")
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "invalid_artifact s12_replay_trace.jsonl line=1 "
        "invalid_runtime_field=runtime"
    ) in output
    assert "artifact_check failed studies=3 invalid=1" in output


def test_event_evidence_report_rejects_non_object_s12_runtime_event(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    trace_path = tmp_path / "s12_replay_trace.jsonl"
    rows = [
        json.loads(line)
        for line in trace_path.read_text(encoding="utf-8").splitlines()
    ]
    for row_index, row in enumerate(rows, start=1):
        events = row.get("runtime", {}).get("events", [])
        if events:
            events[0] = "not-an-event-object"
            trace_path.write_text(
                "\n".join(json.dumps(row) for row in rows) + "\n",
                encoding="utf-8",
            )

            ok = evidence_report.main(
                manifest_path=result["manifest_path"],
                repo_root=tmp_path,
            )
            output = capsys.readouterr().out

            assert ok is False
            assert (
                f"invalid_artifact s12_replay_trace.jsonl line={row_index} "
                "invalid_runtime_event=0"
            ) in output
            assert "artifact_check failed studies=3 invalid=1" in output
            return

    raise AssertionError("fixture did not emit runtime events")


def test_event_evidence_report_rejects_invalid_s12_fixture_expected_kinds_shape(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    fixture_path = REPO_ROOT / "analysis" / "fixtures" / "sre_replay.jsonl"
    rows = [
        json.loads(line)
        for line in fixture_path.read_text(encoding="utf-8").splitlines()
    ]
    rows[15]["expected_kinds"] = "missing_sensor"
    fixture_copy = tmp_path / "sre_replay_bad_expected_kinds.jsonl"
    fixture_copy.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["studies"][2]["artifact_paths"]["fixture_jsonl"] = fixture_copy.name
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    diagnostics_path = tmp_path / "s12_replay_diagnostics.json"
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    diagnostics["fixture_path"] = fixture_copy.name
    diagnostics_path.write_text(
        json.dumps(diagnostics, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=manifest_path,
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "invalid_artifact sre_replay_bad_expected_kinds.jsonl line=16 "
        "invalid_fixture_field=expected_kinds"
    ) in output
    assert "artifact_check failed studies=3 invalid=1" in output


def test_event_evidence_report_rejects_empty_s12_fixture_expected_kinds(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    fixture_path = REPO_ROOT / "analysis" / "fixtures" / "sre_replay.jsonl"
    rows = [
        json.loads(line)
        for line in fixture_path.read_text(encoding="utf-8").splitlines()
    ]
    rows[15]["expected_kinds"] = []
    fixture_copy = tmp_path / "sre_replay_empty_expected_kinds.jsonl"
    fixture_copy.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["studies"][2]["artifact_paths"]["fixture_jsonl"] = fixture_copy.name
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
        "invalid_artifact sre_replay_empty_expected_kinds.jsonl line=16 "
        "invalid_fixture_field=expected_kinds"
    ) in output
    assert "artifact_check failed studies=3 invalid=1" in output


def test_event_evidence_report_rejects_unknown_s12_fixture_expected_kind(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    fixture_path = REPO_ROOT / "analysis" / "fixtures" / "sre_replay.jsonl"
    rows = [
        json.loads(line)
        for line in fixture_path.read_text(encoding="utf-8").splitlines()
    ]
    rows[4]["expected_kind"] = "unknown_runtime_event"
    fixture_copy = tmp_path / "sre_replay_unknown_expected_kind.jsonl"
    fixture_copy.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["studies"][2]["artifact_paths"]["fixture_jsonl"] = fixture_copy.name
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
        "invalid_artifact sre_replay_unknown_expected_kind.jsonl line=5 "
        "unknown_fixture_expected_kind=unknown_runtime_event"
    ) in output
    assert "artifact_check failed studies=3 invalid=1" in output


def test_event_evidence_report_rejects_blank_s12_fixture_expected_kind(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    fixture_path = REPO_ROOT / "analysis" / "fixtures" / "sre_replay.jsonl"
    rows = [
        json.loads(line)
        for line in fixture_path.read_text(encoding="utf-8").splitlines()
    ]
    rows[4]["expected_kind"] = "   "
    fixture_copy = tmp_path / "sre_replay_blank_expected_kind.jsonl"
    fixture_copy.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["studies"][2]["artifact_paths"]["fixture_jsonl"] = fixture_copy.name
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
        "invalid_artifact sre_replay_blank_expected_kind.jsonl line=5 "
        "invalid_fixture_field=expected_kind"
    ) in output
    assert "artifact_check failed studies=3 invalid=1" in output


def test_event_evidence_report_rejects_conflicting_s12_fixture_expected_fields(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    fixture_path = REPO_ROOT / "analysis" / "fixtures" / "sre_replay.jsonl"
    rows = [
        json.loads(line)
        for line in fixture_path.read_text(encoding="utf-8").splitlines()
    ]
    rows[15]["expected_kind"] = "missing_sensor"
    fixture_copy = tmp_path / "sre_replay_conflicting_expected_fields.jsonl"
    fixture_copy.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["studies"][2]["artifact_paths"]["fixture_jsonl"] = fixture_copy.name
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
        "invalid_artifact sre_replay_conflicting_expected_fields.jsonl line=16 "
        "invalid_fixture_field=expected_kind_conflict"
    ) in output
    assert "artifact_check failed studies=3 invalid=1" in output


def test_event_evidence_report_rejects_bounded_residual_without_sufficiency_fields(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    trace_path = tmp_path / "s12_replay_trace.jsonl"
    rows = [
        json.loads(line)
        for line in trace_path.read_text(encoding="utf-8").splitlines()
    ]
    for row in rows:
        for event in row.get("runtime", {}).get("events", []):
            if event["kind"] == "bounded_ls_residual":
                event.pop("rps_residual_fraction")
                trace_path.write_text(
                    "\n".join(json.dumps(row) for row in rows) + "\n",
                    encoding="utf-8",
                )

                ok = evidence_report.main(
                    manifest_path=result["manifest_path"],
                    repo_root=tmp_path,
                )
                output = capsys.readouterr().out

                assert ok is False
                assert "schema_invalid_event s12_replay_trace.jsonl line=" in output
                assert "artifact_check failed studies=3 schema_invalid=1" in output
                return

    raise AssertionError("fixture did not emit bounded_ls_residual")
