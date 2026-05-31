from __future__ import annotations

import json

from analysis import evidence_manifest, evidence_report


def test_event_evidence_report_rejects_absolute_artifact_path(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    absolute_path = tmp_path / "s10_trace_full.jsonl"
    manifest["studies"][0]["artifact_paths"]["full_trace_jsonl"] = str(absolute_path)
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
    assert f"nonportable_artifact_path {absolute_path}" in output
    assert "artifact_check failed studies=3 nonportable=1" in output


def test_event_evidence_report_rejects_parent_directory_artifact_path(
    tmp_path, capsys
) -> None:
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    result = evidence_manifest.main(artifacts_dir=artifact_dir)
    outside_trace = tmp_path / "outside_trace.jsonl"
    outside_trace.write_text(
        (artifact_dir / "s10_trace_full.jsonl").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["studies"][0]["artifact_paths"]["full_trace_jsonl"] = (
        "../outside_trace.jsonl"
    )
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=manifest_path,
        repo_root=artifact_dir,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert "nonportable_artifact_path ../outside_trace.jsonl" in output
    assert "artifact_check failed studies=3 nonportable=1" in output


def test_event_evidence_report_rejects_non_string_artifact_path(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["studies"][0]["artifact_paths"]["full_trace_jsonl"] = 123
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
        "invalid_artifact_path=full_trace_jsonl"
    ) in output
    assert "artifact_check failed studies=3 invalid_manifest=1" in output


def test_event_evidence_report_rejects_missing_required_artifact_key(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["studies"][0]["artifact_paths"]["renamed_trace_jsonl"] = manifest[
        "studies"
    ][0]["artifact_paths"].pop("full_trace_jsonl")
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
        "missing_artifact_key=full_trace_jsonl"
    ) in output
    assert (
        "invalid_manifest study=s10_failure_trace "
        "unexpected_artifact_key=renamed_trace_jsonl"
    ) in output
    assert "artifact_check failed studies=3 invalid_manifest=2" in output


def test_event_evidence_report_rejects_missing_required_contract_artifact_key(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["contracts"][0]["artifact_paths"]["renamed_contract_json"] = manifest[
        "contracts"
    ][0]["artifact_paths"].pop("contract_json")
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
        "invalid_manifest contract=sre_stack_data_contract "
        "missing_artifact_key=contract_json"
    ) in output
    assert (
        "invalid_manifest contract=sre_stack_data_contract "
        "unexpected_artifact_key=renamed_contract_json"
    ) in output
    assert "artifact_check failed studies=3 invalid_manifest=2" in output


def test_event_evidence_report_rejects_wrong_artifact_extension(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    wrong_suffix_path = tmp_path / "s11_catch_sre_wrapper.txt"
    wrong_suffix_path.write_bytes((tmp_path / "s11_catch_sre_wrapper.png").read_bytes())
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["studies"][1]["artifact_paths"]["summary_png"] = wrong_suffix_path.name
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
        "invalid_artifact_extension=summary_png expected=.png actual=.txt"
    ) in output
    assert "artifact_check failed studies=3 invalid_manifest=1" in output


def test_event_evidence_report_rejects_wrong_contract_artifact_extension(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    wrong_suffix_path = tmp_path / "sre_stack_data_contract.txt"
    wrong_suffix_path.write_text(
        (tmp_path / "sre_stack_data_contract.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["contracts"][0]["artifact_paths"]["contract_json"] = wrong_suffix_path.name
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
        "invalid_manifest contract=sre_stack_data_contract "
        "invalid_artifact_extension=contract_json expected=.json actual=.txt"
    ) in output
    assert "artifact_check failed studies=3 invalid_manifest=1" in output
