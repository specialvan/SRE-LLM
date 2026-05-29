from __future__ import annotations

import json

from analysis import evidence_contracts, evidence_manifest


def test_contract_consistency_errors_rejects_fallback_mode_map_drift(tmp_path):
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest = json.loads(result["manifest_path"].read_text(encoding="utf-8"))
    contract_entry = manifest["contracts"][0]
    contract_path = tmp_path / "sre_stack_data_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["stages"][0]["fallback_action_modes"] = {
        "use_forecast_rps_for_observed_load": "keep_current_value",
    }
    contract_path.write_text(
        json.dumps(contract, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    errors = evidence_contracts.contract_consistency_errors(contract_entry, tmp_path)

    assert errors == [
        "inconsistent_artifact sre_stack_data_contract.json "
        "stage_fallback_action_mode_unknown=observe"
    ]


def test_contract_event_errors_rejects_adapter_family_drift(tmp_path):
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest = json.loads(result["manifest_path"].read_text(encoding="utf-8"))
    trace_path = tmp_path / "s10_trace_full.jsonl"
    rows = [
        json.loads(line)
        for line in trace_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    rows[0] = {
        **rows[0],
        "adapter_family": "guard",
        "cause_type": "adapter_input",
        "detail": "observe adapter reported the wrong adapter family",
        "exception_type": "AdapterInputError",
        "fallback_action": "use_forecast_rps_for_observed_load",
        "fallback_mode": "substitute_observed_rps",
        "fault_family": "adapter_input",
        "kind": "adapter_exception",
        "recoverable": True,
        "safe_action": "use validated fallback",
        "stage": "SignalFusion",
    }
    trace_path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )

    errors = evidence_contracts.contract_event_errors(manifest, tmp_path)

    assert errors == [
        "contract_adapter_family_mismatch s10_trace_full.jsonl "
        "stage=SignalFusion contract_stage=observe adapter_family=guard"
    ]
