from __future__ import annotations

import json

import pytest

from analysis import evidence_manifest, evidence_report


def test_event_evidence_report_rejects_stack_contract_production_claim(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    contract_path = tmp_path / "sre_stack_data_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["production_claim"] = True
    contract_path.write_text(
        json.dumps(contract, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "inconsistent_artifact sre_stack_data_contract.json "
        "production_claim_must_be_false"
    ) in output
    assert "artifact_check failed studies=3 inconsistent=1" in output


def test_event_evidence_report_rejects_unknown_stack_contract_event_kind(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    contract_path = tmp_path / "sre_stack_data_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["stages"][0]["event_kinds"].append("not_a_runtime_event")
    contract_path.write_text(
        json.dumps(contract, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "inconsistent_artifact sre_stack_data_contract.json "
        "unknown_stage_event_kind=not_a_runtime_event"
    ) in output
    assert "artifact_check failed studies=3 inconsistent=1" in output


def test_event_evidence_report_rejects_invalid_stack_contract_route_value(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    contract_path = tmp_path / "sre_stack_data_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["event_stage_routes"]["SignalFusion"] = ["observe"]
    contract_path.write_text(
        json.dumps(contract, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "inconsistent_artifact sre_stack_data_contract.json "
        "event_stage_route_invalid=SignalFusion"
    ) in output
    assert "artifact_check failed studies=3 inconsistent=1" in output


def test_event_evidence_report_rejects_unexpected_stack_contract_route_key(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    contract_path = tmp_path / "sre_stack_data_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["event_stage_routes"]["ShadowProducer"] = "observe"
    contract_path.write_text(
        json.dumps(contract, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "inconsistent_artifact sre_stack_data_contract.json "
        "unexpected_event_stage_route=ShadowProducer"
    ) in output
    assert "artifact_check failed studies=3 inconsistent=1" in output


def test_event_evidence_report_rejects_missing_stack_contract_route_key(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    contract_path = tmp_path / "sre_stack_data_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    del contract["event_stage_routes"]["CanaryScheduler"]
    contract_path.write_text(
        json.dumps(contract, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "inconsistent_artifact sre_stack_data_contract.json "
        "missing_event_stage_route=CanaryScheduler"
    ) in output
    assert "artifact_check failed studies=3 inconsistent=1" in output


def test_event_evidence_report_rejects_non_object_stack_contract_stage_entry(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    contract_path = tmp_path / "sre_stack_data_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["stages"][0] = "observe"
    contract_path.write_text(
        json.dumps(contract, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    try:
        ok = evidence_report.main(
            manifest_path=result["manifest_path"],
            repo_root=tmp_path,
        )
    except AttributeError as exc:
        pytest.fail(f"report crashed instead of rejecting stage entry shape: {exc}")
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "inconsistent_artifact sre_stack_data_contract.json "
        "stage_entry_invalid=0"
    ) in output
    assert "artifact_check failed studies=3 inconsistent=1" in output


def test_event_evidence_report_rejects_invalid_stack_contract_stage_interface(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    contract_path = tmp_path / "sre_stack_data_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["stages"][0]["inputs"] = "dt"
    contract_path.write_text(
        json.dumps(contract, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "inconsistent_artifact sre_stack_data_contract.json "
        "stage_interface_invalid=observe.inputs"
    ) in output
    assert "artifact_check failed studies=3 inconsistent=1" in output
