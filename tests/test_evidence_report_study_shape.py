from __future__ import annotations

import json

from analysis import evidence_manifest, evidence_report


def test_event_evidence_report_rejects_missing_study_artifact_paths(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["studies"][0].pop("artifact_paths")
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
        "missing_study_field=artifact_paths"
    ) in output
    assert "artifact_check failed studies=3 invalid_manifest=1" in output


def test_event_evidence_report_rejects_missing_study_specific_field(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["studies"][0].pop("event_count_total")
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
        "missing_study_field=event_count_total"
    ) in output
    assert "artifact_check failed studies=3 invalid_manifest=1" in output


def test_event_evidence_report_rejects_unknown_study_id(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["studies"][0] = {
        "study": "s99_unreviewed_study",
        "section": 99,
        "artifact_paths": {"unreviewed_json": "s11_catch_sre_wrapper_diagnostics.json"},
    }
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
    assert "invalid_manifest unknown_study=s99_unreviewed_study" in output
    assert "invalid_manifest missing_study=s10_failure_trace" in output
    assert "artifact_check failed studies=3 invalid_manifest=2" in output


def test_event_evidence_report_rejects_duplicate_and_missing_study_entries(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["studies"][2] = dict(manifest["studies"][0])
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
    assert "invalid_manifest duplicate_study=s10_failure_trace" in output
    assert "invalid_manifest missing_study=s12_sre_replay" in output
    assert "artifact_check failed studies=3 invalid_manifest=2" in output


def test_event_evidence_report_rejects_invalid_study_field_type(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["studies"][0]["event_count_total"] = "16"
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
        "invalid_study_field_type=event_count_total"
    ) in output
    assert "artifact_check failed studies=3 invalid_manifest=1" in output


def test_event_evidence_report_rejects_boolean_numeric_study_field(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["studies"][0]["background_event_fraction"] = False
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
        "invalid_study_field_type=background_event_fraction"
    ) in output
    assert "artifact_check failed studies=3 invalid_manifest=1" in output


def test_event_evidence_report_rejects_unexpected_study_field_value(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["studies"][0]["evidence_label"] = "production_trace"
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
        "invalid_study_field_value=evidence_label"
    ) in output
    assert "artifact_check failed studies=3 invalid_manifest=1" in output


def test_event_evidence_report_rejects_out_of_range_fraction_field(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["studies"][1]["event_visible_fraction"] = 1.5
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
        "invalid_manifest study=s11_catch_sre_wrapper "
        "invalid_study_field_range=event_visible_fraction"
    ) in output
    assert "artifact_check failed studies=3 invalid_manifest=1" in output


def test_event_evidence_report_rejects_invalid_s11_case_counts_shape(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["studies"][1]["case_counts"] = {
        "feasible": "40",
        "total_overload": 40,
        "unreviewed_case": 40,
    }
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
        "invalid_manifest study=s11_catch_sre_wrapper "
        "missing_case_count=placement_infeasible"
    ) in output
    assert (
        "invalid_manifest study=s11_catch_sre_wrapper "
        "unexpected_case_count=unreviewed_case"
    ) in output
    assert (
        "invalid_manifest study=s11_catch_sre_wrapper "
        "invalid_case_count=feasible"
    ) in output
    assert "artifact_check failed studies=3 invalid_manifest=3" in output


def test_event_evidence_report_rejects_boolean_s11_case_count(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["studies"][1]["case_counts"]["feasible"] = True
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
        "invalid_manifest study=s11_catch_sre_wrapper "
        "invalid_case_count=feasible"
    ) in output
    assert "artifact_check failed studies=3 invalid_manifest=1" in output


def test_event_evidence_report_rejects_negative_count_field(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["studies"][2]["replay_tick_count"] = -1
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
        "invalid_manifest study=s12_sre_replay "
        "invalid_study_field_range=replay_tick_count"
    ) in output
    assert "artifact_check failed studies=3 invalid_manifest=1" in output
