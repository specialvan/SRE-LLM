"""Reviewer-facing summary for the event evidence manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Iterable

from analysis.evidence_manifest import REPO_ROOT
from analysis import s10_failure_trace
from sre_control.events import EVENT_COUNTEREXAMPLES, validate_event
from sre_control.stack_contract import stack_data_contract


def _resolve_artifact(path_text: str, repo_root: Path) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    candidate = repo_root / path
    if candidate.exists():
        return candidate
    return path


def _study_line(entry: dict) -> str:
    study = entry["study"]
    section = entry["section"]
    if study == "s10_failure_trace":
        return f"{study} section={section} events={entry['event_count_total']}"
    if study == "s11_catch_sre_wrapper":
        return f"{study} section={section} visible={entry['event_visible_fraction']}"
    if study == "s12_sre_replay":
        return (
            f"{study} section={section} events={entry['event_count_total']} "
            f"ticks={entry['replay_tick_count']}"
        )
    return f"{study} section={section}"


def _artifact_paths(manifest: dict) -> Iterable[str]:
    for entry in manifest["studies"]:
        yield from entry["artifact_paths"].values()
    for entry in manifest.get("contracts", []):
        yield from entry["artifact_paths"].values()


def _artifact_metadata(path: Path) -> dict:
    data = path.read_bytes()
    return {
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value.lower())
    )


def _is_size_bytes(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _valid_artifact_metadata(value: object) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"sha256", "size_bytes"}
        and _is_sha256(value["sha256"])
        and _is_size_bytes(value["size_bytes"])
    )


def _artifact_metadata_shape_errors(
    entry: dict,
    *,
    entry_kind: str,
    entry_id: str,
    expected_artifact_keys: set[str] | None = None,
) -> list[str]:
    field_label = "study" if entry_kind == "study" else "contract"
    errors: list[str] = []
    if "artifact_metadata" in entry and not isinstance(
        entry["artifact_metadata"], dict
    ):
        errors.append(
            f"invalid_manifest {field_label}={entry_id} "
            f"invalid_{entry_kind}_field=artifact_metadata"
        )
        return errors
    if not isinstance(entry.get("artifact_paths"), dict) or not isinstance(
        entry.get("artifact_metadata"), dict
    ):
        return errors

    path_keys = set(entry["artifact_paths"])
    if expected_artifact_keys is not None and path_keys != expected_artifact_keys:
        return errors

    metadata_keys = set(entry["artifact_metadata"])
    for key in sorted(path_keys - metadata_keys):
        errors.append(
            f"invalid_manifest {field_label}={entry_id} "
            f"missing_artifact_metadata_key={key}"
        )
    for key in sorted(metadata_keys - path_keys):
        errors.append(
            f"invalid_manifest {field_label}={entry_id} "
            f"unexpected_artifact_metadata_key={key}"
        )
    for key in sorted(path_keys & metadata_keys):
        if not _valid_artifact_metadata(entry["artifact_metadata"][key]):
            errors.append(
                f"invalid_manifest {field_label}={entry_id} "
                f"invalid_artifact_metadata={key}"
            )
    return errors


def _matches_manifest_type(value: object, expected_type: type | tuple[type, ...]) -> bool:
    if expected_type is bool:
        return isinstance(value, bool)
    if expected_type is int:
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type is float:
        return isinstance(value, float)
    if isinstance(expected_type, tuple):
        numeric_types = {int, float}
        if set(expected_type).issubset(numeric_types):
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        return any(_matches_manifest_type(value, item) for item in expected_type)
    return isinstance(value, expected_type)


def _manifest_shape_errors(manifest: object) -> list[str]:
    if not isinstance(manifest, dict):
        return ["invalid_manifest top_level_must_be_object"]
    required_fields = {
        "evidence_scope": str,
        "studies": list,
        "contracts": list,
    }
    errors = []
    for field, expected_type in required_fields.items():
        if field not in manifest:
            errors.append(f"invalid_manifest missing_top_level_field={field}")
        elif not isinstance(manifest[field], expected_type):
            errors.append(f"invalid_manifest invalid_top_level_field={field}")
    if errors:
        return errors
    if manifest["evidence_scope"] != "synthetic_sre_event_evidence":
        errors.append("invalid_manifest evidence_scope_mismatch")
    study_required_fields = {
        "s10_failure_trace": {
            "study",
            "section",
            "evidence_label",
            "event_count_total",
            "background_event_fraction",
            "artifact_paths",
            "artifact_metadata",
        },
        "s11_catch_sre_wrapper": {
            "study",
            "section",
            "evidence_label",
            "event_visible_fraction",
            "case_counts",
            "artifact_paths",
            "artifact_metadata",
        },
        "s12_sre_replay": {
            "study",
            "section",
            "evidence_label",
            "event_count_total",
            "replay_tick_count",
            "multi_signal_window_coverage",
            "artifact_paths",
            "artifact_metadata",
        },
    }
    study_field_types = {
        "s10_failure_trace": {
            "study": str,
            "section": int,
            "evidence_label": str,
            "event_count_total": (int, float),
            "background_event_fraction": (int, float),
        },
        "s11_catch_sre_wrapper": {
            "study": str,
            "section": int,
            "evidence_label": str,
            "event_visible_fraction": (int, float),
            "case_counts": dict,
        },
        "s12_sre_replay": {
            "study": str,
            "section": int,
            "evidence_label": str,
            "event_count_total": (int, float),
            "replay_tick_count": int,
            "multi_signal_window_coverage": (int, float),
        },
    }
    study_field_values = {
        "s10_failure_trace": {
            "section": 10,
            "evidence_label": "synthetic_fault_window_trace",
        },
        "s11_catch_sre_wrapper": {
            "section": 11,
            "evidence_label": "synthetic_wrapper_boundary",
        },
        "s12_sre_replay": {
            "section": 12,
            "evidence_label": "synthetic_replay_fixture",
        },
    }
    study_field_ranges = {
        "s10_failure_trace": {
            "event_count_total": (0, None),
            "background_event_fraction": (0, 1),
        },
        "s11_catch_sre_wrapper": {
            "event_visible_fraction": (0, 1),
        },
        "s12_sre_replay": {
            "event_count_total": (0, None),
            "replay_tick_count": (0, None),
            "multi_signal_window_coverage": (0, 1),
        },
    }
    s11_case_count_keys = {"feasible", "total_overload", "placement_infeasible"}
    study_artifact_keys = {
        "s10_failure_trace": {"full_trace_jsonl", "sample_trace_jsonl"},
        "s11_catch_sre_wrapper": {"summary_png", "diagnostics_json"},
        "s12_sre_replay": {
            "fixture_jsonl",
            "trace_jsonl",
            "diagnostics_json",
        },
    }
    study_artifact_extensions = {
        "s10_failure_trace": {
            "full_trace_jsonl": ".jsonl",
            "sample_trace_jsonl": ".jsonl",
        },
        "s11_catch_sre_wrapper": {
            "summary_png": ".png",
            "diagnostics_json": ".json",
        },
        "s12_sre_replay": {
            "fixture_jsonl": ".jsonl",
            "trace_jsonl": ".jsonl",
            "diagnostics_json": ".json",
        },
    }
    expected_studies = set(study_required_fields)
    observed_studies = [
        entry.get("study")
        for entry in manifest["studies"]
        if isinstance(entry, dict) and isinstance(entry.get("study"), str)
    ]
    for study in sorted(set(observed_studies) - expected_studies):
        errors.append(f"invalid_manifest unknown_study={study}")
    for study in sorted(expected_studies - set(observed_studies)):
        errors.append(f"invalid_manifest missing_study={study}")
    seen_studies = set()
    duplicate_studies = set()
    for study in observed_studies:
        if study in seen_studies:
            duplicate_studies.add(study)
        seen_studies.add(study)
    for study in sorted(duplicate_studies):
        errors.append(f"invalid_manifest duplicate_study={study}")
    for index, entry in enumerate(manifest["studies"]):
        if not isinstance(entry, dict):
            errors.append(f"invalid_manifest invalid_study_entry_index={index}")
            continue
        study = entry.get("study", f"<index:{index}>")
        if study not in study_required_fields:
            continue
        required = study_required_fields.get(study, {"study", "section", "artifact_paths"})
        for field in sorted(required):
            if field not in entry:
                errors.append(
                    f"invalid_manifest study={study} missing_study_field={field}"
                )
        for field, expected_type in study_field_types.get(study, {}).items():
            if field in entry and not _matches_manifest_type(
                entry[field], expected_type
            ):
                errors.append(
                    f"invalid_manifest study={study} "
                    f"invalid_study_field_type={field}"
                )
        for field, expected_value in study_field_values.get(study, {}).items():
            expected_type = study_field_types.get(study, {}).get(field)
            if (
                field in entry
                and (
                    expected_type is None
                    or _matches_manifest_type(entry[field], expected_type)
                )
                and entry[field] != expected_value
            ):
                errors.append(
                    f"invalid_manifest study={study} "
                    f"invalid_study_field_value={field}"
                )
        for field, (lower, upper) in study_field_ranges.get(study, {}).items():
            expected_type = study_field_types.get(study, {}).get(field)
            if field not in entry or (
                expected_type is not None
                and not _matches_manifest_type(entry[field], expected_type)
            ):
                continue
            value = float(entry[field])
            if value < lower or (upper is not None and value > upper):
                errors.append(
                    f"invalid_manifest study={study} "
                    f"invalid_study_field_range={field}"
                )
        if study == "s11_catch_sre_wrapper" and isinstance(
            entry.get("case_counts"), dict
        ):
            actual_case_counts = set(entry["case_counts"])
            for key in sorted(s11_case_count_keys - actual_case_counts):
                errors.append(
                    f"invalid_manifest study={study} missing_case_count={key}"
                )
            for key in sorted(actual_case_counts - s11_case_count_keys):
                errors.append(
                    f"invalid_manifest study={study} unexpected_case_count={key}"
                )
            for key in sorted(actual_case_counts & s11_case_count_keys):
                value = entry["case_counts"][key]
                if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    errors.append(
                        f"invalid_manifest study={study} invalid_case_count={key}"
                    )
        if "artifact_paths" in entry and not isinstance(entry["artifact_paths"], dict):
            errors.append(
                f"invalid_manifest study={study} invalid_study_field=artifact_paths"
            )
        elif isinstance(entry.get("artifact_paths"), dict):
            expected_keys = study_artifact_keys.get(study)
            if expected_keys is not None:
                actual_keys = set(entry["artifact_paths"])
                for key in sorted(expected_keys - actual_keys):
                    errors.append(
                        f"invalid_manifest study={study} "
                        f"missing_artifact_key={key}"
                    )
                for key in sorted(actual_keys - expected_keys):
                    errors.append(
                        f"invalid_manifest study={study} "
                        f"unexpected_artifact_key={key}"
                    )
            for key, path_text in entry["artifact_paths"].items():
                if not isinstance(path_text, str):
                    errors.append(
                        f"invalid_manifest study={study} "
                        f"invalid_artifact_path={key}"
                    )
                    continue
                expected_extension = study_artifact_extensions.get(study, {}).get(key)
                if expected_extension is not None:
                    actual_extension = Path(path_text).suffix or "<none>"
                    if actual_extension != expected_extension:
                        errors.append(
                            f"invalid_manifest study={study} "
                            f"invalid_artifact_extension={key} "
                            f"expected={expected_extension} actual={actual_extension}"
                        )
        errors.extend(
            _artifact_metadata_shape_errors(
                entry,
                entry_kind="study",
                entry_id=study,
                expected_artifact_keys=study_artifact_keys.get(study),
            )
        )
    contract_required_fields = {
        "sre_stack_data_contract": {
            "contract",
            "evidence_scope",
            "production_claim",
            "orchestration_model",
            "artifact_paths",
            "artifact_metadata",
        },
    }
    contract_field_types = {
        "sre_stack_data_contract": {
            "contract": str,
            "evidence_scope": str,
            "production_claim": bool,
            "orchestration_model": str,
        },
    }
    contract_field_values = {
        "sre_stack_data_contract": {
            "evidence_scope": "research_stack_data_contract",
            "production_claim": False,
            "orchestration_model": "single_process_research_loop",
        },
    }
    contract_artifact_keys = {
        "sre_stack_data_contract": {"contract_json"},
    }
    contract_artifact_extensions = {
        "sre_stack_data_contract": {"contract_json": ".json"},
    }
    expected_contracts = set(contract_required_fields)
    observed_contracts = [
        entry.get("contract")
        for entry in manifest["contracts"]
        if isinstance(entry, dict) and isinstance(entry.get("contract"), str)
    ]
    for contract in sorted(set(observed_contracts) - expected_contracts):
        errors.append(f"invalid_manifest unknown_contract={contract}")
    for contract in sorted(expected_contracts - set(observed_contracts)):
        errors.append(f"invalid_manifest missing_contract={contract}")
    seen_contracts = set()
    duplicate_contracts = set()
    for contract in observed_contracts:
        if contract in seen_contracts:
            duplicate_contracts.add(contract)
        seen_contracts.add(contract)
    for contract in sorted(duplicate_contracts):
        errors.append(f"invalid_manifest duplicate_contract={contract}")
    for index, entry in enumerate(manifest["contracts"]):
        if not isinstance(entry, dict):
            errors.append(f"invalid_manifest invalid_contract_entry_index={index}")
            continue
        contract = entry.get("contract", f"<index:{index}>")
        if contract not in contract_required_fields:
            continue
        required = contract_required_fields.get(contract, {"contract", "artifact_paths"})
        for field in sorted(required):
            if field not in entry:
                errors.append(
                    f"invalid_manifest contract={contract} missing_contract_field={field}"
                )
        for field, expected_type in contract_field_types.get(contract, {}).items():
            if field in entry and not _matches_manifest_type(
                entry[field], expected_type
            ):
                errors.append(
                    f"invalid_manifest contract={contract} "
                    f"invalid_contract_field_type={field}"
                )
        for field, expected_value in contract_field_values.get(contract, {}).items():
            expected_type = contract_field_types.get(contract, {}).get(field)
            if (
                field in entry
                and (
                    expected_type is None
                    or _matches_manifest_type(entry[field], expected_type)
                )
                and entry[field] != expected_value
            ):
                errors.append(
                    f"invalid_manifest contract={contract} "
                    f"invalid_contract_field_value={field}"
                )
        if "artifact_paths" in entry and not isinstance(entry["artifact_paths"], dict):
            errors.append(
                f"invalid_manifest contract={contract} "
                "invalid_contract_field=artifact_paths"
            )
        elif isinstance(entry.get("artifact_paths"), dict):
            expected_keys = contract_artifact_keys.get(contract)
            if expected_keys is not None:
                actual_keys = set(entry["artifact_paths"])
                for key in sorted(expected_keys - actual_keys):
                    errors.append(
                        f"invalid_manifest contract={contract} "
                        f"missing_artifact_key={key}"
                    )
                for key in sorted(actual_keys - expected_keys):
                    errors.append(
                        f"invalid_manifest contract={contract} "
                        f"unexpected_artifact_key={key}"
                    )
            for key, path_text in entry["artifact_paths"].items():
                if not isinstance(path_text, str):
                    errors.append(
                        f"invalid_manifest contract={contract} "
                        f"invalid_artifact_path={key}"
                    )
                    continue
                expected_extension = contract_artifact_extensions.get(contract, {}).get(
                    key
                )
                if expected_extension is not None:
                    actual_extension = Path(path_text).suffix or "<none>"
                    if actual_extension != expected_extension:
                        errors.append(
                            f"invalid_manifest contract={contract} "
                            f"invalid_artifact_extension={key} "
                            f"expected={expected_extension} actual={actual_extension}"
                        )
        errors.extend(
            _artifact_metadata_shape_errors(
                entry,
                entry_kind="contract",
                entry_id=contract,
                expected_artifact_keys=contract_artifact_keys.get(contract),
            )
        )
    return errors


def _nonportable_artifact_paths(manifest: dict, repo_root: Path) -> list[str]:
    root = repo_root.resolve()
    nonportable = []
    for path_text in _artifact_paths(manifest):
        path = Path(path_text)
        if path.is_absolute():
            nonportable.append(path_text)
            continue
        try:
            (root / path).resolve().relative_to(root)
        except ValueError:
            nonportable.append(path_text)
    return nonportable


def _jsonl_line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def _invalid_jsonl_errors(path: Path, path_text: str) -> list[str]:
    errors: list[str] = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            errors.append(f"invalid_artifact {path_text} line={index}")
            continue
        if not isinstance(value, dict):
            errors.append(
                f"invalid_artifact {path_text} line={index} "
                "top_level_must_be_object"
            )
            continue
    return errors


def _s10_trace_shape_errors(path: Path, path_text: str) -> list[str]:
    errors: list[str] = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        row = json.loads(line)
        tick = row.get("tick")
        if not isinstance(tick, int) or isinstance(tick, bool) or tick < 0:
            errors.append(
                f"invalid_artifact {path_text} line={index} "
                "invalid_trace_field=tick"
            )
            continue
        t_seconds = row.get("t_seconds")
        if not _is_number(t_seconds) or float(t_seconds) < 0:
            errors.append(
                f"invalid_artifact {path_text} line={index} "
                "invalid_trace_field=t_seconds"
            )
            continue
        time_tolerance = 1e-6 * max(1.0, float(tick))
        if abs(float(t_seconds) - tick * s10_failure_trace.DT) > time_tolerance:
            errors.append(
                f"invalid_artifact {path_text} line={index} "
                "trace_time_mismatch"
            )
            continue
    return errors


def _s12_trace_shape_errors(path: Path, path_text: str) -> list[str]:
    errors: list[str] = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        row = json.loads(line)
        runtime = row.get("runtime")
        if runtime is not None and not isinstance(runtime, dict):
            errors.append(
                f"invalid_artifact {path_text} line={index} "
                "invalid_runtime_field=runtime"
            )
            continue
        if isinstance(runtime, dict) and "events" in runtime and not isinstance(
            runtime["events"], list
        ):
            errors.append(
                f"invalid_artifact {path_text} line={index} "
                "invalid_runtime_field=events"
            )
            continue
        if isinstance(runtime, dict) and isinstance(runtime.get("events"), list):
            for event_index, event in enumerate(runtime["events"]):
                if not isinstance(event, dict):
                    errors.append(
                        f"invalid_artifact {path_text} line={index} "
                        f"invalid_runtime_event={event_index}"
                    )
                    continue
    return errors


def _s12_fixture_shape_errors(path: Path, path_text: str) -> list[str]:
    errors: list[str] = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        row = json.loads(line)
        if "expected_kind" in row and "expected_kinds" in row:
            errors.append(
                f"invalid_artifact {path_text} line={index} "
                "invalid_fixture_field=expected_kind_conflict"
            )
            continue
        if "expected_kinds" in row:
            expected_kinds = row["expected_kinds"]
            if (
                not isinstance(expected_kinds, list)
                or not expected_kinds
                or not all(
                    isinstance(kind, str) and kind.strip()
                    for kind in expected_kinds
                )
            ):
                errors.append(
                    f"invalid_artifact {path_text} line={index} "
                    "invalid_fixture_field=expected_kinds"
                )
                continue
        expected_kind = row.get("expected_kind")
        if expected_kind is not None and not (
            isinstance(expected_kind, str) and expected_kind.strip()
        ):
            errors.append(
                f"invalid_artifact {path_text} line={index} "
                "invalid_fixture_field=expected_kind"
            )
            continue
        for kind in _expected_kinds(row):
            if kind not in EVENT_COUNTEREXAMPLES:
                errors.append(
                    f"invalid_artifact {path_text} line={index} "
                    f"unknown_fixture_expected_kind={kind}"
                )
                continue
    return errors


def _invalid_png_errors(path: Path, path_text: str) -> list[str]:
    signature = path.read_bytes()[:8]
    if signature != b"\x89PNG\r\n\x1a\n":
        return [f"invalid_artifact {path_text} invalid_png"]
    return []


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _s11_diagnostics_shape_errors(diagnostics: dict, path_text: str) -> list[str]:
    case_counts = diagnostics.get("case_counts")
    if not isinstance(case_counts, dict):
        return [f"invalid_artifact {path_text} missing_diagnostics_field=case_counts"]
    errors: list[str] = []
    fraction_fields = {
        "feasible_quiet_fraction",
        "placement_infeasible_event_visible_fraction",
        "total_overload_event_visible_fraction",
    }
    expected_case_counts = {"feasible", "total_overload", "placement_infeasible"}
    actual_case_counts = set(case_counts)
    for key in sorted(expected_case_counts - actual_case_counts):
        errors.append(f"invalid_artifact {path_text} missing_case_count={key}")
    for key in sorted(actual_case_counts - expected_case_counts):
        errors.append(f"invalid_artifact {path_text} unexpected_case_count={key}")
    for key in sorted(actual_case_counts & expected_case_counts):
        value = case_counts[key]
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            errors.append(f"invalid_artifact {path_text} invalid_case_count={key}")
    for field in sorted(fraction_fields):
        value = diagnostics.get(field)
        if not _is_number(value) or not 0 <= float(value) <= 1:
            errors.append(
                f"invalid_artifact {path_text} invalid_diagnostics_field={field}"
            )
    return errors


def _s12_diagnostics_shape_errors(diagnostics: dict, path_text: str) -> list[str]:
    errors: list[str] = []
    string_fields = {"evidence_label", "fixture_path"}
    count_fields = {"expected_event_count", "replay_tick_count"}
    nonnegative_number_fields = {
        "event_count_total",
        "max_incident_window_ticks",
        "max_multi_signal_recovery_ticks",
        "max_recovery_ticks",
        "multi_signal_window_count",
        "recovery_window_count",
    }
    fraction_fields = {
        "background_event_fraction",
        "expected_event_visible_fraction",
        "multi_signal_window_recovered_fraction",
        "operator_action_coverage",
        "recovered_window_fraction",
        "stability_event_visible_fraction",
        "multi_signal_window_coverage",
    }
    for field in sorted(string_fields):
        value = diagnostics.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(
                f"invalid_artifact {path_text} invalid_diagnostics_field={field}"
            )
    for field in sorted(count_fields):
        value = diagnostics.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            errors.append(
                f"invalid_artifact {path_text} invalid_diagnostics_field={field}"
            )
    for field in sorted(nonnegative_number_fields):
        value = diagnostics.get(field)
        if not _is_number(value) or float(value) < 0:
            errors.append(
                f"invalid_artifact {path_text} invalid_diagnostics_field={field}"
            )
    for field in sorted(fraction_fields):
        value = diagnostics.get(field)
        if not _is_number(value) or not 0 <= float(value) <= 1:
            errors.append(
                f"invalid_artifact {path_text} invalid_diagnostics_field={field}"
            )
    observed_expected_kinds = diagnostics.get("observed_expected_kinds")
    if not isinstance(observed_expected_kinds, list) or not all(
        isinstance(kind, str) and kind.strip() for kind in observed_expected_kinds
    ):
        errors.append(
            f"invalid_artifact {path_text} "
            "invalid_diagnostics_field=observed_expected_kinds"
        )
    else:
        unknown = sorted(set(observed_expected_kinds) - set(EVENT_COUNTEREXAMPLES))
        if unknown:
            errors.append(
                f"invalid_artifact {path_text} "
                f"unknown_observed_expected_kind={unknown[0]}"
            )
    operator_actions_by_kind = diagnostics.get("operator_actions_by_kind")
    if not isinstance(operator_actions_by_kind, dict):
        errors.append(
            f"invalid_artifact {path_text} "
            "invalid_diagnostics_field=operator_actions_by_kind"
        )
    else:
        for kind, actions in operator_actions_by_kind.items():
            if not isinstance(kind, str) or not kind.strip():
                errors.append(
                    f"invalid_artifact {path_text} "
                    "invalid_operator_action_kind"
                )
                break
            if kind not in EVENT_COUNTEREXAMPLES:
                errors.append(
                    f"invalid_artifact {path_text} "
                    f"unknown_operator_action_kind={kind}"
                )
                break
            if not isinstance(actions, list) or not actions or not all(
                isinstance(action, str) and action.strip() for action in actions
            ):
                errors.append(
                    f"invalid_artifact {path_text} "
                    f"invalid_operator_actions={kind}"
                )
                break
    operator_actions_by_window = diagnostics.get("operator_actions_by_window")
    if not isinstance(operator_actions_by_window, dict):
        errors.append(
            f"invalid_artifact {path_text} "
            "invalid_diagnostics_field=operator_actions_by_window"
        )
    else:
        for incident_id, actions in operator_actions_by_window.items():
            if not isinstance(incident_id, str) or not incident_id.strip():
                errors.append(
                    f"invalid_artifact {path_text} "
                    "invalid_window_operator_action_id"
                )
                break
            if not isinstance(actions, list) or not actions or not all(
                isinstance(action, str) and action.strip() for action in actions
            ):
                errors.append(
                    f"invalid_artifact {path_text} "
                    f"invalid_window_operator_actions={incident_id}"
                )
                break
    return errors


def _s11_event_visible_fraction(diagnostics: dict) -> float:
    case_counts = diagnostics["case_counts"]
    total_overload = case_counts["total_overload"]
    placement_infeasible = case_counts["placement_infeasible"]
    event_bearing_cases = total_overload + placement_infeasible
    if event_bearing_cases == 0:
        return 1.0
    visible = (
        total_overload * float(diagnostics["total_overload_event_visible_fraction"])
        + placement_infeasible
        * float(diagnostics["placement_infeasible_event_visible_fraction"])
    )
    return float(visible / event_bearing_cases)


def _s10_background_event_fraction(trace_path: Path) -> float:
    trace_rows = [
        json.loads(line)
        for line in trace_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    event_ticks = {
        int(row["tick"])
        for row in trace_rows
        if "tick" in row
    }
    total_ticks = int(s10_failure_trace.T_FINAL / s10_failure_trace.DT)
    t_grid = [index * s10_failure_trace.DT for index in range(total_ticks)]
    injected_ticks = {
        index
        for index, timestamp in enumerate(t_grid)
        for window in s10_failure_trace.INJECTION_WINDOWS
        if window.bounds[0] <= timestamp <= window.bounds[1]
    }
    background_ticks = set(range(total_ticks)) - injected_ticks
    if not background_ticks:
        return 0.0
    return float(len(event_ticks & background_ticks) / len(background_ticks))


def _jsonl_rows(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _diagnostics_value(path: Path, key: str):
    return json.loads(path.read_text(encoding="utf-8"))[key]


def _expected_kinds(row: dict) -> list[str]:
    if "expected_kinds" in row:
        return list(row["expected_kinds"])
    expected_kind = row.get("expected_kind")
    return [] if expected_kind is None else [expected_kind]


def _operator_actions_by_kind(rows: list[dict]) -> dict[str, list[str]]:
    actions_by_kind: dict[str, list[str]] = {}
    for row in rows:
        if "expected_kinds" in row:
            continue
        if not _expected_kinds(row):
            continue
        action = row.get("operator_action")
        if not isinstance(action, str) or not action.strip():
            continue
        kind = row["expected_kind"]
        actions_by_kind.setdefault(kind, [])
        if action not in actions_by_kind[kind]:
            actions_by_kind[kind].append(action)
    return {
        kind: sorted(actions) for kind, actions in sorted(actions_by_kind.items())
    }


def _operator_actions_by_window(rows: list[dict]) -> dict[str, list[str]]:
    grouped: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        incident_id = row.get("incident_id")
        if incident_id and _expected_kinds(row):
            grouped.setdefault(incident_id, []).append(index)

    actions_by_window: dict[str, list[str]] = {}
    for incident_id, indices in grouped.items():
        expected = set()
        actions = set()
        for index in indices:
            expected.update(_expected_kinds(rows[index]))
            action = rows[index].get("window_operator_action")
            if isinstance(action, str) and action.strip():
                actions.add(action)
        if len(expected) >= 2 and actions:
            actions_by_window[incident_id] = sorted(actions)
    return dict(sorted(actions_by_window.items()))


def _recovery_diagnostics(
    rows: list[dict], trace_rows: list[dict]
) -> dict[str, float | None]:
    windows: list[tuple[int, int]] = []
    start: int | None = None
    for index, row in enumerate(rows):
        if _expected_kinds(row) and start is None:
            start = index
        elif not _expected_kinds(row) and start is not None:
            windows.append((start, index - 1))
            start = None
    if start is not None:
        windows.append((start, len(rows) - 1))

    recovery_ticks: list[float] = []
    for _, end in windows:
        recovered_at = None
        for index in range(end + 1, len(rows)):
            if _expected_kinds(rows[index]):
                continue
            if not trace_rows[index].get("runtime", {}).get("events", []):
                recovered_at = index
                break
        recovery_ticks.append(
            float("inf") if recovered_at is None else float(recovered_at - end)
        )

    finite = [tick for tick in recovery_ticks if tick != float("inf")]
    return {
        "recovery_window_count": float(len(windows)),
        "recovered_window_fraction": (
            float(len(finite) / len(windows)) if windows else 1.0
        ),
        "max_recovery_ticks": float(max(finite)) if finite else None,
    }


def _multi_signal_window_diagnostics(
    rows: list[dict], trace_rows: list[dict]
) -> dict[str, float]:
    grouped: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        incident_id = row.get("incident_id")
        if incident_id and _expected_kinds(row):
            grouped.setdefault(incident_id, []).append(index)

    windows = []
    for indices in grouped.values():
        expected = set()
        observed = set()
        for index in indices:
            expected.update(_expected_kinds(rows[index]))
            observed.update(
                event["kind"]
                for event in trace_rows[index].get("runtime", {}).get("events", [])
            )
        if len(expected) < 2:
            continue
        end = max(indices)
        recovered_at = None
        for index in range(end + 1, len(rows)):
            if _expected_kinds(rows[index]):
                continue
            if not trace_rows[index].get("runtime", {}).get("events", []):
                recovered_at = index
                break
        windows.append(
            {
                "length": len(indices),
                "covered": expected.issubset(observed),
                "recovery_ticks": (
                    float("inf") if recovered_at is None else float(recovered_at - end)
                ),
            }
        )

    finite_recovery = [
        window["recovery_ticks"]
        for window in windows
        if window["recovery_ticks"] != float("inf")
    ]
    return {
        "multi_signal_window_count": float(len(windows)),
        "max_incident_window_ticks": float(
            max((window["length"] for window in windows), default=0)
        ),
        "multi_signal_window_coverage": (
            float(sum(window["covered"] for window in windows) / len(windows))
            if windows
            else 1.0
        ),
        "multi_signal_window_recovered_fraction": (
            float(len(finite_recovery) / len(windows)) if windows else 1.0
        ),
        "max_multi_signal_recovery_ticks": (
            float(max(finite_recovery)) if finite_recovery else None
        ),
    }


def _mean_bool(values: list[bool], default: float) -> float:
    if not values:
        return default
    return float(sum(values) / len(values))


def _visibility_diagnostics(rows: list[dict], trace_rows: list[dict]) -> dict[str, float]:
    visible_expected: list[bool] = []
    background_clean: list[bool] = []
    visible_stability: list[bool] = []
    for index, row in enumerate(rows):
        expected = set(_expected_kinds(row))
        event_kinds = {
            event["kind"]
            for event in trace_rows[index].get("runtime", {}).get("events", [])
        }
        if not expected:
            background_clean.append(not event_kinds)
            continue
        visible = expected.issubset(event_kinds)
        visible_expected.append(visible)
        if "stability_violation" in expected:
            visible_stability.append(visible)

    return {
        "expected_event_visible_fraction": _mean_bool(visible_expected, 1.0),
        "background_event_fraction": 1.0 - _mean_bool(background_clean, 1.0),
        "stability_event_visible_fraction": _mean_bool(visible_stability, 1.0),
    }


def _s12_replay_consistency(
    fixture_path: Path,
    trace_path: Path,
    diagnostics: dict,
    expected_evidence_label: str,
    expected_fixture_path: str,
) -> list[str]:
    fixture_rows = [
        json.loads(line)
        for line in fixture_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    trace_rows = [
        json.loads(line)
        for line in trace_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    expected_rows = [row for row in fixture_rows if _expected_kinds(row)]
    observed_expected_kinds = sorted(
        {kind for row in expected_rows for kind in _expected_kinds(row)}
    )
    annotated = [
        row
        for row in expected_rows
        if isinstance(row.get("operator_action"), str)
        and row["operator_action"].strip()
    ]
    expected_event_count = len(expected_rows)
    operator_action_coverage = (
        float(len(annotated) / expected_event_count) if expected_event_count else 1.0
    )
    observed_event_count = sum(
        len(row.get("runtime", {}).get("events", [])) for row in trace_rows
    )
    recovery = _recovery_diagnostics(fixture_rows, trace_rows)
    multi_signal = _multi_signal_window_diagnostics(fixture_rows, trace_rows)
    visibility = _visibility_diagnostics(fixture_rows, trace_rows)

    errors = []
    if diagnostics["evidence_label"] != expected_evidence_label:
        errors.append("evidence_label_mismatch")
    if diagnostics["fixture_path"] != expected_fixture_path:
        errors.append("fixture_path_mismatch")
    if int(diagnostics["expected_event_count"]) != expected_event_count:
        errors.append("expected_event_count_mismatch")
    if diagnostics["observed_expected_kinds"] != observed_expected_kinds:
        errors.append("observed_expected_kinds_mismatch")
    if int(diagnostics["replay_tick_count"]) != len(trace_rows):
        errors.append("replay_tick_count_mismatch")
    if float(diagnostics["event_count_total"]) != float(observed_event_count):
        errors.append("event_count_total_mismatch")
    if abs(float(diagnostics["operator_action_coverage"]) - operator_action_coverage) > 1e-9:
        errors.append("operator_action_coverage_mismatch")
    if diagnostics["operator_actions_by_kind"] != _operator_actions_by_kind(fixture_rows):
        errors.append("operator_actions_by_kind_mismatch")
    if diagnostics["operator_actions_by_window"] != _operator_actions_by_window(fixture_rows):
        errors.append("operator_actions_by_window_mismatch")
    for field, expected_value in recovery.items():
        if float(diagnostics[field]) != expected_value:
            errors.append(f"{field}_mismatch")
    for field, expected_value in multi_signal.items():
        if float(diagnostics[field]) != expected_value:
            errors.append(f"{field}_mismatch")
    for field, expected_value in visibility.items():
        if float(diagnostics[field]) != expected_value:
            errors.append(f"{field}_mismatch")
    return errors


def _consistency_errors(entry: dict, root: Path) -> list[str]:
    artifacts = {
        key: _resolve_artifact(path_text, root)
        for key, path_text in entry["artifact_paths"].items()
    }
    study = entry["study"]
    errors: list[str] = []
    if study == "s10_failure_trace":
        actual = _jsonl_line_count(artifacts["full_trace_jsonl"])
        expected = int(entry["event_count_total"])
        if actual != expected:
            errors.append(
                f"inconsistent_artifact {entry['artifact_paths']['full_trace_jsonl']} "
                f"expected_lines={expected} actual_lines={actual}"
            )
        if (
            float(entry["background_event_fraction"])
            != _s10_background_event_fraction(artifacts["full_trace_jsonl"])
        ):
            errors.append(
                f"inconsistent_artifact {entry['artifact_paths']['full_trace_jsonl']} "
                "background_event_fraction_mismatch"
            )
        full_rows = _jsonl_rows(artifacts["full_trace_jsonl"])
        sample_rows = _jsonl_rows(artifacts["sample_trace_jsonl"])
        if full_rows and not sample_rows:
            errors.append(
                f"inconsistent_artifact {entry['artifact_paths']['sample_trace_jsonl']} "
                "sample_trace_empty"
            )
        if sample_rows != full_rows[: len(sample_rows)]:
            errors.append(
                f"inconsistent_artifact {entry['artifact_paths']['sample_trace_jsonl']} "
                "sample_trace_prefix_mismatch"
            )
    elif study == "s11_catch_sre_wrapper":
        diagnostics_path = artifacts["diagnostics_json"]
        diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
        if diagnostics["case_counts"] != entry["case_counts"]:
            errors.append(
                f"inconsistent_artifact {entry['artifact_paths']['diagnostics_json']} "
                "case_counts_mismatch"
            )
        if (
            float(entry["event_visible_fraction"])
            != _s11_event_visible_fraction(diagnostics)
        ):
            errors.append(
                f"inconsistent_artifact {entry['artifact_paths']['diagnostics_json']} "
                "event_visible_fraction_mismatch"
            )
    elif study == "s12_sre_replay":
        actual = _jsonl_line_count(artifacts["trace_jsonl"])
        expected = int(entry["replay_tick_count"])
        if actual != expected:
            errors.append(
                f"inconsistent_artifact {entry['artifact_paths']['trace_jsonl']} "
                f"expected_lines={expected} actual_lines={actual}"
            )
            return errors
        diagnostics_path = artifacts["diagnostics_json"]
        diagnostic_event_count = _diagnostics_value(diagnostics_path, "event_count_total")
        if float(diagnostic_event_count) != float(entry["event_count_total"]):
            errors.append(
                f"inconsistent_artifact {entry['artifact_paths']['diagnostics_json']} "
                "event_count_total_mismatch"
            )
        diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
        for mismatch in _s12_replay_consistency(
            artifacts["fixture_jsonl"],
            artifacts["trace_jsonl"],
            diagnostics,
            entry["evidence_label"],
            entry["artifact_paths"]["fixture_jsonl"],
        ):
            errors.append(
                f"inconsistent_artifact {entry['artifact_paths']['diagnostics_json']} "
                f"{mismatch}"
            )
    return errors


def _contract_consistency_errors(entry: dict, root: Path) -> list[str]:
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
        errors.append(
            f"inconsistent_artifact {entry['artifact_paths']['contract_json']} "
            "evidence_scope_mismatch"
        )
    if contract.get("production_claim") is not False:
        errors.append(
            f"inconsistent_artifact {entry['artifact_paths']['contract_json']} "
            "production_claim_must_be_false"
        )
    if contract.get("orchestration_model") != "single_process_research_loop":
        errors.append(
            f"inconsistent_artifact {entry['artifact_paths']['contract_json']} "
            "orchestration_model_mismatch"
        )
    split_ready_boundaries = contract.get("split_ready_boundaries")
    if not isinstance(split_ready_boundaries, list) or not all(
        isinstance(boundary, str) for boundary in split_ready_boundaries
    ):
        errors.append(
            f"inconsistent_artifact {entry['artifact_paths']['contract_json']} "
            "split_ready_boundaries_invalid"
        )
    else:
        expected_split_ready_boundaries = {
            "observe_to_plan",
            "plan_to_guard",
            "guard_to_allocate",
            "allocate_to_execute",
        }
        observed_split_ready_boundaries = set(split_ready_boundaries)
        for boundary in sorted(
            expected_split_ready_boundaries - observed_split_ready_boundaries
        ):
            errors.append(
                f"inconsistent_artifact {entry['artifact_paths']['contract_json']} "
                f"missing_split_ready_boundary={boundary}"
            )
        for boundary in sorted(
            observed_split_ready_boundaries - expected_split_ready_boundaries
        ):
            errors.append(
                f"inconsistent_artifact {entry['artifact_paths']['contract_json']} "
                f"unexpected_split_ready_boundary={boundary}"
            )
    stages = contract.get("stages")
    declared_stage_names: set[str] = set()
    if isinstance(stages, list):
        for index, stage in enumerate(stages):
            if not isinstance(stage, dict):
                errors.append(
                    f"inconsistent_artifact {entry['artifact_paths']['contract_json']} "
                    f"stage_entry_invalid={index}"
                )
                return errors
    if not isinstance(stages, list) or [stage.get("stage") for stage in stages] != [
        "observe",
        "stability",
        "plan",
        "guard",
        "allocate",
        "execute",
    ]:
        errors.append(
            f"inconsistent_artifact {entry['artifact_paths']['contract_json']} "
            "stage_order_mismatch"
        )
    else:
        declared_stage_names = {stage["stage"] for stage in stages}
        if any("event_kinds" not in stage for stage in stages):
            errors.append(
                f"inconsistent_artifact {entry['artifact_paths']['contract_json']} "
                "stage_event_kinds_missing"
            )
        for stage in stages:
            stage_name = stage["stage"]
            if not isinstance(stage.get("producer"), str):
                errors.append(
                    f"inconsistent_artifact {entry['artifact_paths']['contract_json']} "
                    f"stage_interface_invalid={stage_name}.producer"
                )
                break
            for field in ("inputs", "outputs", "fallback_modes"):
                values = stage.get(field)
                if not isinstance(values, list) or not all(
                    isinstance(value, str) for value in values
                ):
                    errors.append(
                        f"inconsistent_artifact {entry['artifact_paths']['contract_json']} "
                        f"stage_interface_invalid={stage_name}.{field}"
                    )
                    break
            if errors and errors[-1].endswith((".inputs", ".outputs", ".producer")):
                break
            if "event_kinds" not in stage:
                break
            event_kinds = stage["event_kinds"]
            if not isinstance(event_kinds, list) or not all(
                isinstance(kind, str) for kind in event_kinds
            ):
                errors.append(
                    f"inconsistent_artifact {entry['artifact_paths']['contract_json']} "
                    f"stage_event_kinds_invalid={stage.get('stage')}"
                )
                break
            unknown = sorted(set(event_kinds) - set(EVENT_COUNTEREXAMPLES))
            if unknown:
                errors.append(
                    f"inconsistent_artifact {entry['artifact_paths']['contract_json']} "
                    f"unknown_stage_event_kind={unknown[0]}"
                )
                break
    routes = contract.get("event_stage_routes")
    if not isinstance(routes, dict):
        errors.append(
            f"inconsistent_artifact {entry['artifact_paths']['contract_json']} "
            "event_stage_routes_missing"
        )
    else:
        expected_route_keys = set(stack_data_contract()["event_stage_routes"])
        observed_route_keys = set(routes)
        for route_key in sorted(expected_route_keys - observed_route_keys):
            errors.append(
                f"inconsistent_artifact {entry['artifact_paths']['contract_json']} "
                f"missing_event_stage_route={route_key}"
            )
        for route_key in sorted(observed_route_keys - expected_route_keys):
            errors.append(
                f"inconsistent_artifact {entry['artifact_paths']['contract_json']} "
                f"unexpected_event_stage_route={route_key}"
            )
        for route_key, contract_stage in routes.items():
            if not isinstance(route_key, str) or not isinstance(contract_stage, str):
                errors.append(
                    f"inconsistent_artifact {entry['artifact_paths']['contract_json']} "
                    f"event_stage_route_invalid={route_key}"
                )
                break
            if declared_stage_names and contract_stage not in declared_stage_names:
                errors.append(
                    f"inconsistent_artifact {entry['artifact_paths']['contract_json']} "
                    f"event_stage_route_unknown_stage={route_key}"
                )
                break
    return errors


def _invalid_artifact_errors(entry: dict, root: Path) -> list[str]:
    artifacts = {
        key: _resolve_artifact(path_text, root)
        for key, path_text in entry["artifact_paths"].items()
    }
    path_texts = entry["artifact_paths"]
    errors: list[str] = []
    for key, path in artifacts.items():
        path_text = path_texts[key]
        if path.suffix == ".json":
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                errors.append(f"invalid_artifact {path_text}")
                continue
            if not isinstance(value, dict):
                errors.append(f"invalid_artifact {path_text} top_level_must_be_object")
            elif key == "diagnostics_json":
                if entry.get("study") == "s11_catch_sre_wrapper":
                    errors.extend(_s11_diagnostics_shape_errors(value, path_text))
                elif entry.get("study") == "s12_sre_replay":
                    errors.extend(_s12_diagnostics_shape_errors(value, path_text))
        elif path.suffix == ".jsonl":
            errors.extend(_invalid_jsonl_errors(path, path_text))
            if (
                not errors
                and entry.get("study") == "s10_failure_trace"
                and key in {"full_trace_jsonl", "sample_trace_jsonl"}
            ):
                errors.extend(_s10_trace_shape_errors(path, path_text))
            if (
                not errors
                and entry.get("study") == "s12_sre_replay"
                and key == "trace_jsonl"
            ):
                errors.extend(_s12_trace_shape_errors(path, path_text))
            if (
                not errors
                and entry.get("study") == "s12_sre_replay"
                and key == "fixture_jsonl"
            ):
                errors.extend(_s12_fixture_shape_errors(path, path_text))
        elif path.suffix == ".png":
            errors.extend(_invalid_png_errors(path, path_text))
    return errors


def _artifact_identity_errors(manifest: dict, root: Path) -> list[str]:
    errors: list[str] = []
    for entry in [*manifest["studies"], *manifest.get("contracts", [])]:
        for key, path_text in entry["artifact_paths"].items():
            actual = _artifact_metadata(_resolve_artifact(path_text, root))
            expected = entry["artifact_metadata"][key]
            if actual != expected:
                errors.append(
                    f"artifact_identity_mismatch {path_text} "
                    f"expected_sha256={expected['sha256']} "
                    f"actual_sha256={actual['sha256']} "
                    f"expected_size_bytes={expected['size_bytes']} "
                    f"actual_size_bytes={actual['size_bytes']}"
                )
    return errors


def _schema_invalid_event_errors(entry: dict, root: Path) -> list[str]:
    artifacts = {
        key: _resolve_artifact(path_text, root)
        for key, path_text in entry["artifact_paths"].items()
    }
    path_texts = entry["artifact_paths"]
    errors: list[str] = []
    study = entry["study"]
    if study == "s10_failure_trace":
        path_text = path_texts["full_trace_jsonl"]
        for index, line in enumerate(
            artifacts["full_trace_jsonl"].read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            row = json.loads(line)
            event = {
                key: value
                for key, value in row.items()
                if key not in {"tick", "t_seconds"}
            }
            if not validate_event(event):
                errors.append(f"schema_invalid_event {path_text} line={index}")
                continue
    elif study == "s12_sre_replay":
        path_text = path_texts["trace_jsonl"]
        for index, line in enumerate(
            artifacts["trace_jsonl"].read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            row = json.loads(line)
            for event in row.get("runtime", {}).get("events", []):
                if not validate_event(event):
                    errors.append(f"schema_invalid_event {path_text} line={index}")
                    continue
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


def _contract_event_errors(manifest: dict, root: Path) -> list[str]:
    contracts = {
        entry["contract"]: entry for entry in manifest.get("contracts", [])
    }
    contract_entry = contracts.get("sre_stack_data_contract")
    if contract_entry is None:
        return []

    contract_path_text = contract_entry["artifact_paths"]["contract_json"]
    contract_path = _resolve_artifact(contract_path_text, root)
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    routes = contract.get("event_stage_routes")
    stages = contract.get("stages")
    if not isinstance(routes, dict) or not isinstance(stages, list):
        return [
            f"inconsistent_artifact {contract_path_text} "
            "event_stage_routes_missing"
        ]

    allowed_by_stage = {
        stage["stage"]: set(stage["event_kinds"])
        for stage in stages
        if isinstance(stage, dict)
        and isinstance(stage.get("stage"), str)
        and isinstance(stage.get("event_kinds"), list)
    }
    fallback_modes_by_stage = {
        stage['stage']: set(stage['fallback_modes'])
        for stage in stages
        if isinstance(stage, dict)
        and isinstance(stage.get('stage'), str)
        and isinstance(stage.get('fallback_modes'), list)
    }
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
            if (
                event['kind'] == 'adapter_exception'
                and event['adapter_family'] != contract_stage
            ):
                errors.append(
                    f'contract_adapter_family_mismatch {path_text} '
                    f'stage={event_stage} contract_stage={contract_stage} '
                    + 'adapter_family='
                    + str(event['adapter_family'])
                )
                return errors
            if (
                event['kind'] == 'adapter_exception'
                and event['exception_type'] == 'AdapterInputError'
                and event['cause_type'] != 'adapter_input'
            ):
                errors.append(
                    f'contract_exception_cause_mismatch {path_text} '
                    f'stage={event_stage} '
                    + 'exception_type='
                    + str(event['exception_type'])
                    + ' cause_type='
                    + str(event['cause_type'])
                )
                return errors
            if (
                event['kind'] == 'adapter_exception'
                and event['fault_family'] != event['cause_type']
            ):
                errors.append(
                    f'contract_fault_family_mismatch {path_text} '
                    f'stage={event_stage} '
                    + 'cause_type='
                    + str(event['cause_type'])
                    + ' fault_family='
                    + str(event['fault_family'])
                )
                return errors
            if (
                event['kind'] == 'adapter_exception'
                and event['fallback_mode']
                not in fallback_modes_by_stage.get(contract_stage, set())
            ):
                errors.append(
                    f'contract_unrouted_fallback_mode {path_text} '
                    f'stage={event_stage} contract_stage={contract_stage} '
                    + 'fallback_mode='
                    + str(event['fallback_mode'])
                )
                return errors
    return errors


def main(
    manifest_path: Path | str | None = None,
    repo_root: Path | str | None = None,
) -> bool:
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    manifest_file = (
        Path(manifest_path)
        if manifest_path is not None
        else root / "analysis" / "artifacts" / "event_evidence_manifest.json"
    )
    try:
        manifest_text = manifest_file.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"invalid_manifest missing_manifest {manifest_file}")
        print("artifact_check failed studies=0 invalid_manifest=1")
        return False

    try:
        manifest = json.loads(manifest_text)
    except json.JSONDecodeError:
        print("invalid_manifest malformed_json")
        print("artifact_check failed studies=0 invalid_manifest=1")
        return False

    shape_errors = _manifest_shape_errors(manifest)
    if shape_errors:
        for error in shape_errors:
            print(error)
        studies_count = len(manifest.get("studies", [])) if isinstance(manifest, dict) else 0
        print(
            f"artifact_check failed studies={studies_count} "
            f"invalid_manifest={len(shape_errors)}"
        )
        return False

    print(f"evidence_scope {manifest['evidence_scope']}")
    for entry in manifest["studies"]:
        print(_study_line(entry))

    nonportable = _nonportable_artifact_paths(manifest, root)
    if nonportable:
        for path_text in nonportable:
            print(f"nonportable_artifact_path {path_text}")
        print(
            f"artifact_check failed studies={len(manifest['studies'])} "
            f"nonportable={len(nonportable)}"
        )
        return False

    missing = [
        path_text
        for path_text in _artifact_paths(manifest)
        if not _resolve_artifact(path_text, root).exists()
    ]
    if missing:
        for path_text in missing:
            print(f"missing_artifact {path_text}")
        print(
            f"artifact_check failed studies={len(manifest['studies'])} "
            f"missing={len(missing)}"
        )
        return False

    artifact_identity = _artifact_identity_errors(manifest, root)
    for error in artifact_identity:
        print(error)

    invalid = [
        error
        for entry in manifest["studies"]
        for error in _invalid_artifact_errors(entry, root)
    ]
    invalid.extend(
        error
        for entry in manifest.get("contracts", [])
        for error in _invalid_artifact_errors(entry, root)
    )
    if invalid:
        for error in invalid:
            print(error)
        print(
            f"artifact_check failed studies={len(manifest['studies'])} "
            f"invalid={len(invalid)}"
        )
        return False

    inconsistent = [
        error
        for entry in manifest["studies"]
        for error in _consistency_errors(entry, root)
    ]
    inconsistent.extend(
        error
        for entry in manifest.get("contracts", [])
        for error in _contract_consistency_errors(entry, root)
    )
    if inconsistent:
        for error in inconsistent:
            print(error)
        print(
            f"artifact_check failed studies={len(manifest['studies'])} "
            f"inconsistent={len(inconsistent)}"
        )
        return False

    schema_invalid = [
        error
        for entry in manifest["studies"]
        for error in _schema_invalid_event_errors(entry, root)
    ]
    if schema_invalid:
        for error in schema_invalid:
            print(error)
        print(
            f"artifact_check failed studies={len(manifest['studies'])} "
            f"schema_invalid={len(schema_invalid)}"
        )
        return False

    contract_events = _contract_event_errors(manifest, root)
    if contract_events:
        for error in contract_events:
            print(error)
        print(
            f"artifact_check failed studies={len(manifest['studies'])} "
            f"contract_events={len(contract_events)}"
        )
        return False

    if artifact_identity:
        print(
            f"artifact_check failed studies={len(manifest['studies'])} "
            f"artifact_identity={len(artifact_identity)}"
        )
        return False

    file_count = sum(1 for _ in _artifact_paths(manifest))
    print(f"artifact_check ok studies={len(manifest['studies'])} files={file_count}")
    return True


def _cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "manifest",
        nargs="?",
        default=REPO_ROOT / "analysis" / "artifacts" / "event_evidence_manifest.json",
        help="Path to event_evidence_manifest.json",
    )
    args = parser.parse_args()
    raise SystemExit(0 if main(manifest_path=args.manifest) else 1)


if __name__ == "__main__":
    _cli()
