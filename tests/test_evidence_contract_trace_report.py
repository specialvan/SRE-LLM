from __future__ import annotations

import hashlib
import json
from pathlib import Path

from analysis import evidence_manifest, evidence_report


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _replace_first_s10_trace_event(result: dict, tmp_path: Path, event: dict) -> None:
    manifest_path = result["manifest_path"]
    full_path = tmp_path / "s10_trace_full.jsonl"
    sample_path = tmp_path / "s10_trace_sample.jsonl"
    full_rows = [
        json.loads(line)
        for line in full_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    sample_rows = [
        json.loads(line)
        for line in sample_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    replacement = {
        **event,
        "t_seconds": full_rows[0]["t_seconds"],
        "tick": full_rows[0]["tick"],
    }
    full_rows[0] = replacement
    sample_rows[0] = replacement
    for path, rows in [(full_path, full_rows), (sample_path, sample_rows)]:
        path.write_text(
            "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
            encoding="utf-8",
        )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest["studies"]:
        if entry["study"] == "s10_failure_trace":
            for key, path in {
                "full_trace_jsonl": full_path,
                "sample_trace_jsonl": sample_path,
            }.items():
                entry["artifact_metadata"][key] = {
                    "sha256": _sha256(path),
                    "size_bytes": path.stat().st_size,
                }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_event_evidence_report_rejects_trace_fallback_mode_not_allowed_by_stage(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    _replace_first_s10_trace_event(
        result,
        tmp_path,
        {
            "adapter_family": "observe",
            "cause_type": "adapter_input",
            "detail": "observe adapter used an undeclared fallback mode",
            "exception_type": "AdapterInputError",
            "fallback_action": "zero_guardrail_action",
            "fallback_mode": "zero_action",
            "fault_family": "adapter_input",
            "kind": "adapter_exception",
            "recoverable": True,
            "safe_action": "use validated fallback",
            "stage": "SignalFusion",
        },
    )

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "contract_unrouted_fallback_mode s10_trace_full.jsonl "
        "stage=SignalFusion contract_stage=observe "
        "fallback_mode=zero_action"
    ) in output
    assert "artifact_check failed studies=3 contract_events=1" in output


def test_event_evidence_report_rejects_trace_fallback_action_not_allowed_by_stage(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    _replace_first_s10_trace_event(
        result,
        tmp_path,
        {
            "adapter_family": "observe",
            "cause_type": "adapter_input",
            "detail": "observe adapter used a fallback action from another stage",
            "exception_type": "AdapterInputError",
            "fallback_action": "zero_guardrail_action",
            "fallback_mode": "substitute_observed_rps",
            "fault_family": "adapter_input",
            "kind": "adapter_exception",
            "recoverable": True,
            "safe_action": "use validated fallback",
            "stage": "SignalFusion",
        },
    )

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "contract_unrouted_fallback_action s10_trace_full.jsonl "
        "stage=SignalFusion contract_stage=observe "
        "fallback_action=zero_guardrail_action"
    ) in output
    assert "artifact_check failed studies=3 contract_events=1" in output


def test_event_evidence_report_rejects_trace_fallback_action_mode_mismatch(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    _replace_first_s10_trace_event(
        result,
        tmp_path,
        {
            "adapter_family": "plan",
            "cause_type": "adapter_input",
            "detail": "plan adapter mixed two valid fallback fields",
            "exception_type": "AdapterInputError",
            "fallback_action": "keep_current_replicas",
            "fallback_mode": "skip_optional_stage",
            "fault_family": "adapter_input",
            "kind": "adapter_exception",
            "recoverable": True,
            "safe_action": "use validated fallback",
            "stage": "PredictiveAutoscaler",
        },
    )

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "contract_fallback_mode_mismatch s10_trace_full.jsonl "
        "stage=PredictiveAutoscaler contract_stage=plan "
        "fallback_action=keep_current_replicas "
        "fallback_mode=skip_optional_stage expected_mode=keep_current_value"
    ) in output
    assert "artifact_check failed studies=3 contract_events=1" in output


def test_event_evidence_report_rejects_trace_adapter_family_not_matching_stage_route(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    _replace_first_s10_trace_event(
        result,
        tmp_path,
        {
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
        },
    )

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "contract_adapter_family_mismatch s10_trace_full.jsonl "
        "stage=SignalFusion contract_stage=observe adapter_family=guard"
    ) in output
    assert "artifact_check failed studies=3 contract_events=1" in output


def test_event_evidence_report_rejects_trace_fault_family_not_matching_cause_type(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    _replace_first_s10_trace_event(
        result,
        tmp_path,
        {
            "adapter_family": "observe",
            "cause_type": "adapter_input",
            "detail": "observe adapter reported the wrong fault family",
            "exception_type": "AdapterInputError",
            "fallback_action": "use_forecast_rps_for_observed_load",
            "fallback_mode": "substitute_observed_rps",
            "fault_family": "control_domain",
            "kind": "adapter_exception",
            "recoverable": True,
            "safe_action": "use validated fallback",
            "stage": "SignalFusion",
        },
    )

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "contract_fault_family_mismatch s10_trace_full.jsonl "
        "stage=SignalFusion cause_type=adapter_input "
        "fault_family=control_domain"
    ) in output
    assert "artifact_check failed studies=3 contract_events=1" in output


def test_event_evidence_report_rejects_trace_exception_type_not_matching_cause_type(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    _replace_first_s10_trace_event(
        result,
        tmp_path,
        {
            "adapter_family": "observe",
            "cause_type": "control_domain",
            "detail": "adapter input error reported as control-domain cause",
            "exception_type": "AdapterInputError",
            "fallback_action": "use_forecast_rps_for_observed_load",
            "fallback_mode": "substitute_observed_rps",
            "fault_family": "control_domain",
            "kind": "adapter_exception",
            "recoverable": True,
            "safe_action": "use validated fallback",
            "stage": "SignalFusion",
        },
    )

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "contract_exception_cause_mismatch s10_trace_full.jsonl "
        "stage=SignalFusion exception_type=AdapterInputError "
        "cause_type=control_domain"
    ) in output
    assert "artifact_check failed studies=3 contract_events=1" in output


def test_event_evidence_report_rejects_trace_recoverable_error_marked_adapter_input(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    _replace_first_s10_trace_event(
        result,
        tmp_path,
        {
            "adapter_family": "observe",
            "cause_type": "adapter_input",
            "detail": "recoverable control-domain error reported as adapter input",
            "exception_type": "RecoverableControlError",
            "fallback_action": "use_forecast_rps_for_observed_load",
            "fallback_mode": "substitute_observed_rps",
            "fault_family": "adapter_input",
            "kind": "adapter_exception",
            "recoverable": True,
            "safe_action": "use validated fallback",
            "stage": "SignalFusion",
        },
    )

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "contract_exception_cause_mismatch s10_trace_full.jsonl "
        "stage=SignalFusion exception_type=RecoverableControlError "
        "cause_type=adapter_input"
    ) in output
    assert "artifact_check failed studies=3 contract_events=1" in output


def test_event_evidence_report_rejects_adapter_exception_marked_unrecoverable(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    _replace_first_s10_trace_event(
        result,
        tmp_path,
        {
            "adapter_family": "observe",
            "cause_type": "adapter_input",
            "detail": "adapter exception was marked unrecoverable",
            "exception_type": "AdapterInputError",
            "fallback_action": "use_forecast_rps_for_observed_load",
            "fallback_mode": "substitute_observed_rps",
            "fault_family": "adapter_input",
            "kind": "adapter_exception",
            "recoverable": False,
            "safe_action": "use validated fallback",
            "stage": "SignalFusion",
        },
    )

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "contract_unrecoverable_adapter_exception s10_trace_full.jsonl "
        "stage=SignalFusion recoverable=False"
    ) in output
    assert "artifact_check failed studies=3 contract_events=1" in output
