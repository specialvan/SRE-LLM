from __future__ import annotations

import json

from analysis import evidence_manifest, evidence_report


def test_event_evidence_report_rejects_missing_contract_artifact_paths(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["contracts"][0].pop("artifact_paths")
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
        "missing_contract_field=artifact_paths"
    ) in output
    assert "artifact_check failed studies=3 invalid_manifest=1" in output


def test_event_evidence_report_rejects_missing_contract_specific_field(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["contracts"][0].pop("production_claim")
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
        "missing_contract_field=production_claim"
    ) in output
    assert "artifact_check failed studies=3 invalid_manifest=1" in output


def test_event_evidence_report_rejects_unknown_contract_id(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["contracts"][0] = {
        "contract": "unreviewed_contract",
        "artifact_paths": {"contract_json": "sre_stack_data_contract.json"},
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
    assert "invalid_manifest unknown_contract=unreviewed_contract" in output
    assert "invalid_manifest missing_contract=sre_stack_data_contract" in output
    assert "artifact_check failed studies=3 invalid_manifest=2" in output


def test_event_evidence_report_rejects_duplicate_contract_entries(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["contracts"].append(dict(manifest["contracts"][0]))
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
    assert "invalid_manifest duplicate_contract=sre_stack_data_contract" in output
    assert "artifact_check failed studies=3 invalid_manifest=1" in output


def test_event_evidence_report_rejects_invalid_contract_field_type(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["contracts"][0]["production_claim"] = "false"
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
        "invalid_contract_field_type=production_claim"
    ) in output
    assert "artifact_check failed studies=3 invalid_manifest=1" in output


def test_event_evidence_report_rejects_unexpected_contract_field_value(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["contracts"][0]["production_claim"] = True
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
        "invalid_contract_field_value=production_claim"
    ) in output
    assert "artifact_check failed studies=3 invalid_manifest=1" in output
