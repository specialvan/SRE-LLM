"""Stack-contract checks used by the event evidence report."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from sre_control.events import EVENT_COUNTEREXAMPLES
from sre_control.stack_contract import stack_data_contract


EXPECTED_STAGE_ORDER = [
    "observe",
    "stability",
    "plan",
    "guard",
    "allocate",
    "execute",
]
EXPECTED_SPLIT_READY_BOUNDARIES = {
    "observe_to_plan",
    "plan_to_guard",
    "guard_to_allocate",
    "allocate_to_execute",
}
ADAPTER_EXCEPTION_CAUSE_TYPES = {
    "AdapterInputError": "adapter_input",
    "RecoverableControlError": "control_domain",
}


def _resolve_artifact(path_text: str, repo_root: Path) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    candidate = repo_root / path
    if candidate.exists():
        return candidate
    return path


def _contract_path_text(entry: dict) -> str:
    return entry["artifact_paths"]["contract_json"]


def _artifact_error(entry: dict, reason: str) -> str:
    return f"inconsistent_artifact {_contract_path_text(entry)} {reason}"


def _string_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _validate_split_ready_boundaries(entry: dict, contract: dict) -> list[str]:
    boundaries = contract.get("split_ready_boundaries")
    if not _string_list(boundaries):
        return [_artifact_error(entry, "split_ready_boundaries_invalid")]

    observed = set(boundaries)
    errors = [
        _artifact_error(entry, f"missing_split_ready_boundary={boundary}")
        for boundary in sorted(EXPECTED_SPLIT_READY_BOUNDARIES - observed)
    ]
    errors.extend(
        _artifact_error(entry, f"unexpected_split_ready_boundary={boundary}")
        for boundary in sorted(observed - EXPECTED_SPLIT_READY_BOUNDARIES)
    )
    return errors


def _stage_interface_error(entry: dict, stage_name: str, field: str) -> str:
    return _artifact_error(entry, f"stage_interface_invalid={stage_name}.{field}")


def _validate_stage_interface(entry: dict, stage: dict) -> str | None:
    stage_name = stage["stage"]
    if not isinstance(stage.get("producer"), str):
        return _stage_interface_error(entry, stage_name, "producer")
    for field in ("inputs", "outputs", "fallback_actions", "fallback_modes"):
        if not _string_list(stage.get(field)):
            return _stage_interface_error(entry, stage_name, field)

    fallback_action_modes = stage.get("fallback_action_modes")
    if not isinstance(fallback_action_modes, dict) or not all(
        isinstance(action, str) and isinstance(mode, str)
        for action, mode in fallback_action_modes.items()
    ):
        return _stage_interface_error(entry, stage_name, "fallback_action_modes")
    if set(fallback_action_modes) != set(stage.get("fallback_actions", [])):
        return _artifact_error(entry, f"stage_fallback_action_modes_mismatch={stage_name}")
    if not set(fallback_action_modes.values()).issubset(
        set(stage.get("fallback_modes", []))
    ):
        return _artifact_error(entry, f"stage_fallback_action_mode_unknown={stage_name}")
    return None


def _validate_stage_event_kinds(entry: dict, stage: dict) -> str | None:
    if "event_kinds" not in stage:
        return None
    event_kinds = stage["event_kinds"]
    if not _string_list(event_kinds):
        return _artifact_error(entry, f"stage_event_kinds_invalid={stage.get('stage')}")
    unknown = sorted(set(event_kinds) - set(EVENT_COUNTEREXAMPLES))
    if unknown:
        return _artifact_error(entry, f"unknown_stage_event_kind={unknown[0]}")
    return None


def _validate_stages(entry: dict, contract: dict) -> tuple[list[str], set[str]]:
    stages = contract.get("stages")
    errors: list[str] = []
    declared_stage_names: set[str] = set()
    if isinstance(stages, list):
        for index, stage in enumerate(stages):
            if not isinstance(stage, dict):
                return [_artifact_error(entry, f"stage_entry_invalid={index}")], set()
    if not isinstance(stages, list) or [stage.get("stage") for stage in stages] != EXPECTED_STAGE_ORDER:
        return [_artifact_error(entry, "stage_order_mismatch")], set()

    declared_stage_names = {stage["stage"] for stage in stages}
    if any("event_kinds" not in stage for stage in stages):
        errors.append(_artifact_error(entry, "stage_event_kinds_missing"))
    for stage in stages:
        interface_error = _validate_stage_interface(entry, stage)
        if interface_error is not None:
            errors.append(interface_error)
            break
        event_kind_error = _validate_stage_event_kinds(entry, stage)
        if event_kind_error is not None:
            errors.append(event_kind_error)
            break
    return errors, declared_stage_names


def _validate_routes(
    entry: dict, contract: dict, declared_stage_names: set[str]
) -> list[str]:
    routes = contract.get("event_stage_routes")
    errors: list[str] = []
    if not isinstance(routes, dict):
        return [_artifact_error(entry, "event_stage_routes_missing")]

    expected_route_keys = set(stack_data_contract()["event_stage_routes"])
    observed_route_keys = set(routes)
    errors.extend(
        _artifact_error(entry, f"missing_event_stage_route={route_key}")
        for route_key in sorted(expected_route_keys - observed_route_keys)
    )
    errors.extend(
        _artifact_error(entry, f"unexpected_event_stage_route={route_key}")
        for route_key in sorted(observed_route_keys - expected_route_keys)
    )
    for route_key, contract_stage in routes.items():
        if not isinstance(route_key, str) or not isinstance(contract_stage, str):
            errors.append(_artifact_error(entry, f"event_stage_route_invalid={route_key}"))
            break
        if declared_stage_names and contract_stage not in declared_stage_names:
            errors.append(
                _artifact_error(entry, f"event_stage_route_unknown_stage={route_key}")
            )
            break
    return errors


def contract_consistency_errors(entry: dict, root: Path) -> list[str]:
    artifacts = {
        key: _resolve_artifact(path_text, root)
        for key, path_text in entry["artifact_paths"].items()
    }
    errors: list[str] = []
    if entry["contract"] != "sre_stack_data_contract":
        return errors
    contract_path = artifacts["contract_json"]
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if contract.get("evidence_scope") != "research_stack_data_contract":
        errors.append(_artifact_error(entry, "evidence_scope_mismatch"))
    if contract.get("production_claim") is not False:
        errors.append(_artifact_error(entry, "production_claim_must_be_false"))
    if contract.get("orchestration_model") != "single_process_research_loop":
        errors.append(_artifact_error(entry, "orchestration_model_mismatch"))
    errors.extend(_validate_split_ready_boundaries(entry, contract))
    stage_errors, declared_stage_names = _validate_stages(entry, contract)
    errors.extend(stage_errors)
    errors.extend(_validate_routes(entry, contract, declared_stage_names))
    return errors


def _iter_entry_events(entry: dict, root: Path) -> Iterable[tuple[str, dict]]:
    artifacts = {
        key: _resolve_artifact(path_text, root)
        for key, path_text in entry["artifact_paths"].items()
    }
    path_texts = entry["artifact_paths"]
    study = entry["study"]
    if study == "s10_failure_trace":
        for line in artifacts["full_trace_jsonl"].read_text(encoding="utf-8").splitlines():
            yield path_texts["full_trace_jsonl"], json.loads(line)
    elif study == "s12_sre_replay":
        for line in artifacts["trace_jsonl"].read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            for event in row.get("runtime", {}).get("events", []):
                yield path_texts["trace_jsonl"], event


def _stage_maps(stages: list) -> tuple[dict, dict, dict, dict]:
    allowed_by_stage = {
        stage["stage"]: set(stage["event_kinds"])
        for stage in stages
        if isinstance(stage, dict)
        and isinstance(stage.get("stage"), str)
        and isinstance(stage.get("event_kinds"), list)
    }
    fallback_modes_by_stage = {
        stage["stage"]: set(stage["fallback_modes"])
        for stage in stages
        if isinstance(stage, dict)
        and isinstance(stage.get("stage"), str)
        and isinstance(stage.get("fallback_modes"), list)
    }
    fallback_actions_by_stage = {
        stage["stage"]: set(stage["fallback_actions"])
        for stage in stages
        if isinstance(stage, dict)
        and isinstance(stage.get("stage"), str)
        and isinstance(stage.get("fallback_actions"), list)
    }
    fallback_action_modes_by_stage = {
        stage["stage"]: dict(stage["fallback_action_modes"])
        for stage in stages
        if isinstance(stage, dict)
        and isinstance(stage.get("stage"), str)
        and isinstance(stage.get("fallback_action_modes"), dict)
    }
    return (
        allowed_by_stage,
        fallback_modes_by_stage,
        fallback_actions_by_stage,
        fallback_action_modes_by_stage,
    )


def _adapter_exception_error(
    path_text: str,
    event: dict,
    event_stage: str,
    contract_stage: str,
    fallback_modes_by_stage: dict,
    fallback_actions_by_stage: dict,
    fallback_action_modes_by_stage: dict,
) -> str | None:
    if event["adapter_family"] != contract_stage:
        return (
            f"contract_adapter_family_mismatch {path_text} "
            f"stage={event_stage} contract_stage={contract_stage} "
            + "adapter_family="
            + str(event["adapter_family"])
        )
    if event["recoverable"] is not True:
        return (
            f"contract_unrecoverable_adapter_exception {path_text} "
            f"stage={event_stage} "
            + "recoverable="
            + str(event["recoverable"])
        )
    expected_cause_type = ADAPTER_EXCEPTION_CAUSE_TYPES.get(event["exception_type"])
    if expected_cause_type is not None and event["cause_type"] != expected_cause_type:
        return (
            f"contract_exception_cause_mismatch {path_text} "
            f"stage={event_stage} "
            + "exception_type="
            + str(event["exception_type"])
            + " cause_type="
            + str(event["cause_type"])
        )
    if event["fault_family"] != event["cause_type"]:
        return (
            f"contract_fault_family_mismatch {path_text} "
            f"stage={event_stage} "
            + "cause_type="
            + str(event["cause_type"])
            + " fault_family="
            + str(event["fault_family"])
        )
    if event["fallback_mode"] not in fallback_modes_by_stage.get(contract_stage, set()):
        return (
            f"contract_unrouted_fallback_mode {path_text} "
            f"stage={event_stage} contract_stage={contract_stage} "
            + "fallback_mode="
            + str(event["fallback_mode"])
        )
    if event["fallback_action"] not in fallback_actions_by_stage.get(contract_stage, set()):
        return (
            f"contract_unrouted_fallback_action {path_text} "
            f"stage={event_stage} contract_stage={contract_stage} "
            + "fallback_action="
            + str(event["fallback_action"])
        )
    expected_mode = fallback_action_modes_by_stage.get(contract_stage, {}).get(
        event["fallback_action"]
    )
    if expected_mode is not None and event["fallback_mode"] != expected_mode:
        return (
            f"contract_fallback_mode_mismatch {path_text} "
            f"stage={event_stage} contract_stage={contract_stage} "
            + "fallback_action="
            + str(event["fallback_action"])
            + " fallback_mode="
            + str(event["fallback_mode"])
            + " expected_mode="
            + str(expected_mode)
        )
    return None


def contract_event_errors(manifest: dict, root: Path) -> list[str]:
    contracts = {entry["contract"]: entry for entry in manifest.get("contracts", [])}
    contract_entry = contracts.get("sre_stack_data_contract")
    if contract_entry is None:
        return []

    contract_path_text = contract_entry["artifact_paths"]["contract_json"]
    contract_path = _resolve_artifact(contract_path_text, root)
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    routes = contract.get("event_stage_routes")
    stages = contract.get("stages")
    if not isinstance(routes, dict) or not isinstance(stages, list):
        return [f"inconsistent_artifact {contract_path_text} event_stage_routes_missing"]

    (
        allowed_by_stage,
        fallback_modes_by_stage,
        fallback_actions_by_stage,
        fallback_action_modes_by_stage,
    ) = _stage_maps(stages)
    errors: list[str] = []
    for entry in manifest["studies"]:
        for path_text, event in _iter_entry_events(entry, root):
            event_stage = str(event["stage"])
            route_key = event_stage.split("/", 1)[0]
            contract_stage = routes.get(route_key)
            if not isinstance(contract_stage, str):
                errors.append(
                    f"contract_unrouted_event {path_text} "
                    f"stage={event_stage} kind={event['kind']} contract_stage=<missing>"
                )
                return errors
            if event["kind"] not in allowed_by_stage.get(contract_stage, set()):
                errors.append(
                    f"contract_unrouted_event {path_text} "
                    f"stage={event_stage} kind={event['kind']} "
                    f"contract_stage={contract_stage}"
                )
                return errors
            if event["kind"] != "adapter_exception":
                continue
            adapter_error = _adapter_exception_error(
                path_text,
                event,
                event_stage,
                contract_stage,
                fallback_modes_by_stage,
                fallback_actions_by_stage,
                fallback_action_modes_by_stage,
            )
            if adapter_error is not None:
                errors.append(adapter_error)
                return errors
    return errors
