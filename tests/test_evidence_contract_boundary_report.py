from __future__ import annotations

import json

from analysis import evidence_manifest, evidence_report


def test_event_evidence_report_rejects_invalid_stack_contract_split_boundaries(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    contract_path = tmp_path / "sre_stack_data_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["split_ready_boundaries"] = ["observe_to_plan", 123]
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
        "split_ready_boundaries_invalid"
    ) in output
    assert "artifact_check failed studies=3 inconsistent=1" in output


def test_event_evidence_report_rejects_unexpected_stack_contract_split_boundary_set(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    contract_path = tmp_path / "sre_stack_data_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["split_ready_boundaries"] = [
        "observe_to_plan",
        "plan_to_guard",
        "unexpected_boundary",
    ]
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
        "missing_split_ready_boundary=allocate_to_execute"
    ) in output
    assert (
        "inconsistent_artifact sre_stack_data_contract.json "
        "unexpected_split_ready_boundary=unexpected_boundary"
    ) in output
    assert "artifact_check failed studies=3 inconsistent=3" in output


def test_event_evidence_report_rejects_trace_event_not_allowed_by_stack_contract(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    contract_path = tmp_path / "sre_stack_data_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    for stage in contract["stages"]:
        if stage["stage"] == "guard":
            stage["event_kinds"].remove("unsafe_proposal_projected")
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
        "contract_unrouted_event s10_trace_full.jsonl "
        "stage=SLOGuardrail kind=unsafe_proposal_projected contract_stage=guard"
    ) in output
    assert "artifact_check failed studies=3 contract_events=1" in output
