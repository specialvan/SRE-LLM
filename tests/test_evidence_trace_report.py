from __future__ import annotations

import json

import pytest

from analysis import evidence_manifest, evidence_report


def test_event_evidence_report_rejects_s10_background_fraction_mismatch(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["studies"][0]["background_event_fraction"] = 0.5
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
        "inconsistent_artifact s10_trace_full.jsonl "
        "background_event_fraction_mismatch"
    ) in output
    assert "artifact_check failed studies=3 inconsistent=1" in output


def test_event_evidence_report_rejects_s10_sample_trace_prefix_mismatch(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    full_path = tmp_path / "s10_trace_full.jsonl"
    sample_path = tmp_path / "s10_trace_sample.jsonl"
    full_rows = full_path.read_text(encoding="utf-8").splitlines()
    sample_rows = sample_path.read_text(encoding="utf-8").splitlines()
    sample_rows[0] = full_rows[-1]
    sample_path.write_text("\n".join(sample_rows) + "\n", encoding="utf-8")

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "inconsistent_artifact s10_trace_sample.jsonl "
        "sample_trace_prefix_mismatch"
    ) in output
    assert "artifact_check failed studies=3 inconsistent=1" in output


def test_event_evidence_report_rejects_empty_s10_sample_trace(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    sample_path = tmp_path / "s10_trace_sample.jsonl"
    sample_path.write_text("", encoding="utf-8")

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert "inconsistent_artifact s10_trace_sample.jsonl sample_trace_empty" in output
    assert "artifact_check failed studies=3 inconsistent=1" in output


@pytest.mark.parametrize("field", ["tick", "t_seconds"])
def test_event_evidence_report_rejects_invalid_s10_trace_time_field(
    tmp_path, capsys, field
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    trace_path = tmp_path / "s10_trace_full.jsonl"
    rows = [
        json.loads(line)
        for line in trace_path.read_text(encoding="utf-8").splitlines()
    ]
    rows[0].pop(field)
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
        "invalid_artifact s10_trace_full.jsonl line=1 "
        f"invalid_trace_field={field}"
    ) in output
    assert "artifact_check failed studies=3 invalid=1" in output


def test_event_evidence_report_rejects_s10_trace_time_mismatch(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    trace_path = tmp_path / "s10_trace_full.jsonl"
    sample_path = tmp_path / "s10_trace_sample.jsonl"
    rows = [
        json.loads(line)
        for line in trace_path.read_text(encoding="utf-8").splitlines()
    ]
    sample_rows = [
        json.loads(line)
        for line in sample_path.read_text(encoding="utf-8").splitlines()
    ]
    rows[0]["t_seconds"] = rows[0]["t_seconds"] + 1.0
    sample_rows[0]["t_seconds"] = sample_rows[0]["t_seconds"] + 1.0
    trace_path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )
    sample_path.write_text(
        "\n".join(json.dumps(row) for row in sample_rows) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "invalid_artifact s10_trace_full.jsonl line=1 "
        "trace_time_mismatch"
    ) in output
    assert "artifact_check failed studies=3 invalid=1" in output


def test_event_evidence_report_rejects_schema_invalid_event_artifact(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    trace_path = tmp_path / "s10_trace_full.jsonl"
    rows = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    rows[0].pop("safe_action")
    trace_path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )
    sample_path = tmp_path / "s10_trace_sample.jsonl"
    sample_rows = [
        json.loads(line)
        for line in sample_path.read_text(encoding="utf-8").splitlines()
    ]
    sample_rows[0].pop("safe_action")
    sample_path.write_text(
        "\n".join(json.dumps(row) for row in sample_rows) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert "schema_invalid_event s10_trace_full.jsonl line=1" in output
    assert "artifact_check failed studies=3 schema_invalid=1" in output
