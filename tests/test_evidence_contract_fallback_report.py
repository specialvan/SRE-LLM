from __future__ import annotations

import json

import pytest

from analysis import evidence_manifest, evidence_report


@pytest.mark.parametrize(
    ("field", "bad_value", "expected_error"),
    [
        (
            "fallback_actions",
            "keep_current_replicas",
            "stage_interface_invalid=observe.fallback_actions",
        ),
        (
            "fallback_modes",
            "keep_current_value",
            "stage_interface_invalid=observe.fallback_modes",
        ),
        (
            "fallback_action_modes",
            ["use_forecast_rps_for_observed_load"],
            "stage_interface_invalid=observe.fallback_action_modes",
        ),
    ],
)
def test_event_evidence_report_rejects_malformed_stack_contract_fallback_fields(
    tmp_path, capsys, field, bad_value, expected_error
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    contract_path = tmp_path / "sre_stack_data_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["stages"][0][field] = bad_value
    contract_path.write_text(
        json.dumps(contract, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    try:
        ok = evidence_report.main(
            manifest_path=result["manifest_path"],
            repo_root=tmp_path,
        )
    except TypeError as exc:
        pytest.fail(f"report crashed instead of rejecting fallback field shape: {exc}")
    output = capsys.readouterr().out

    assert ok is False
    assert f"inconsistent_artifact sre_stack_data_contract.json {expected_error}" in output
    assert "artifact_check failed studies=3 inconsistent=1" in output


@pytest.mark.parametrize(
    ("fallback_action_modes", "expected_error"),
    [
        (
            {"wrong_observe_fallback": "substitute_observed_rps"},
            "stage_fallback_action_modes_mismatch=observe",
        ),
        (
            {"use_forecast_rps_for_observed_load": "keep_current_value"},
            "stage_fallback_action_mode_unknown=observe",
        ),
    ],
)
def test_event_evidence_report_rejects_stack_contract_fallback_action_mode_map_drift(
    tmp_path, capsys, fallback_action_modes, expected_error
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    contract_path = tmp_path / "sre_stack_data_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["stages"][0]["fallback_action_modes"] = fallback_action_modes
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
    assert f"inconsistent_artifact sre_stack_data_contract.json {expected_error}" in output
    assert "artifact_check failed studies=3 inconsistent=1" in output
