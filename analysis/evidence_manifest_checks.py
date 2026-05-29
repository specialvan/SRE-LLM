"""Manifest-shape checks used by the event evidence report."""

from __future__ import annotations

from pathlib import Path


STUDY_REQUIRED_FIELDS = {
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

STUDY_FIELD_TYPES = {
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

STUDY_FIELD_VALUES = {
    "s10_failure_trace": {"section": 10, "evidence_label": "synthetic_fault_window_trace"},
    "s11_catch_sre_wrapper": {"section": 11, "evidence_label": "synthetic_wrapper_boundary"},
    "s12_sre_replay": {"section": 12, "evidence_label": "synthetic_replay_fixture"},
}

STUDY_FIELD_RANGES = {
    "s10_failure_trace": {"event_count_total": (0, None), "background_event_fraction": (0, 1)},
    "s11_catch_sre_wrapper": {"event_visible_fraction": (0, 1)},
    "s12_sre_replay": {
        "event_count_total": (0, None),
        "replay_tick_count": (0, None),
        "multi_signal_window_coverage": (0, 1),
    },
}

STUDY_ARTIFACT_KEYS = {
    "s10_failure_trace": {"full_trace_jsonl", "sample_trace_jsonl"},
    "s11_catch_sre_wrapper": {"summary_png", "diagnostics_json"},
    "s12_sre_replay": {"fixture_jsonl", "trace_jsonl", "diagnostics_json"},
}

STUDY_ARTIFACT_EXTENSIONS = {
    "s10_failure_trace": {"full_trace_jsonl": ".jsonl", "sample_trace_jsonl": ".jsonl"},
    "s11_catch_sre_wrapper": {"summary_png": ".png", "diagnostics_json": ".json"},
    "s12_sre_replay": {
        "fixture_jsonl": ".jsonl",
        "trace_jsonl": ".jsonl",
        "diagnostics_json": ".json",
    },
}

CONTRACT_REQUIRED_FIELDS = {
    "sre_stack_data_contract": {
        "contract",
        "evidence_scope",
        "production_claim",
        "orchestration_model",
        "artifact_paths",
        "artifact_metadata",
    },
}

CONTRACT_FIELD_TYPES = {
    "sre_stack_data_contract": {
        "contract": str,
        "evidence_scope": str,
        "production_claim": bool,
        "orchestration_model": str,
    },
}

CONTRACT_FIELD_VALUES = {
    "sre_stack_data_contract": {
        "evidence_scope": "research_stack_data_contract",
        "production_claim": False,
        "orchestration_model": "single_process_research_loop",
    },
}

CONTRACT_ARTIFACT_KEYS = {"sre_stack_data_contract": {"contract_json"}}
CONTRACT_ARTIFACT_EXTENSIONS = {"sre_stack_data_contract": {"contract_json": ".json"}}
S11_CASE_COUNT_KEYS = {"feasible", "total_overload", "placement_infeasible"}


def is_sha256(value: object) -> bool:
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
        and is_sha256(value["sha256"])
        and _is_size_bytes(value["size_bytes"])
    )


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


def _artifact_metadata_shape_errors(
    entry: dict,
    *,
    entry_kind: str,
    entry_id: str,
    expected_artifact_keys: set[str] | None = None,
) -> list[str]:
    field_label = "study" if entry_kind == "study" else "contract"
    errors: list[str] = []
    if "artifact_metadata" in entry and not isinstance(entry["artifact_metadata"], dict):
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


def _validate_study_entry(entry: dict, errors: list[str]) -> None:
    study = entry.get("study", "<unknown>")
    if study not in STUDY_REQUIRED_FIELDS:
        return
    for field in sorted(STUDY_REQUIRED_FIELDS[study]):
        if field not in entry:
            errors.append(f"invalid_manifest study={study} missing_study_field={field}")
    for field, expected_type in STUDY_FIELD_TYPES.get(study, {}).items():
        if field in entry and not _matches_manifest_type(entry[field], expected_type):
            errors.append(f"invalid_manifest study={study} invalid_study_field_type={field}")
    for field, expected_value in STUDY_FIELD_VALUES.get(study, {}).items():
        expected_type = STUDY_FIELD_TYPES.get(study, {}).get(field)
        if (
            field in entry
            and (expected_type is None or _matches_manifest_type(entry[field], expected_type))
            and entry[field] != expected_value
        ):
            errors.append(f"invalid_manifest study={study} invalid_study_field_value={field}")
    for field, (lower, upper) in STUDY_FIELD_RANGES.get(study, {}).items():
        expected_type = STUDY_FIELD_TYPES.get(study, {}).get(field)
        if field not in entry or (
            expected_type is not None and not _matches_manifest_type(entry[field], expected_type)
        ):
            continue
        value = float(entry[field])
        if value < lower or (upper is not None and value > upper):
            errors.append(f"invalid_manifest study={study} invalid_study_field_range={field}")

    if study == "s11_catch_sre_wrapper" and isinstance(entry.get("case_counts"), dict):
        actual_case_counts = set(entry["case_counts"])
        for key in sorted(S11_CASE_COUNT_KEYS - actual_case_counts):
            errors.append(f"invalid_manifest study={study} missing_case_count={key}")
        for key in sorted(actual_case_counts - S11_CASE_COUNT_KEYS):
            errors.append(f"invalid_manifest study={study} unexpected_case_count={key}")
        for key in sorted(actual_case_counts & S11_CASE_COUNT_KEYS):
            value = entry["case_counts"][key]
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                errors.append(f"invalid_manifest study={study} invalid_case_count={key}")
    _validate_artifact_paths(
        entry,
        errors,
        entry_kind="study",
        entry_id=study,
        expected_keys=STUDY_ARTIFACT_KEYS.get(study),
        expected_extensions=STUDY_ARTIFACT_EXTENSIONS.get(study, {}),
    )
    errors.extend(
        _artifact_metadata_shape_errors(
            entry,
            entry_kind="study",
            entry_id=study,
            expected_artifact_keys=STUDY_ARTIFACT_KEYS.get(study),
        )
    )


def _validate_artifact_paths(
    entry: dict,
    errors: list[str],
    *,
    entry_kind: str,
    entry_id: str,
    expected_keys: set[str] | None,
    expected_extensions: dict[str, str],
) -> None:
    field_prefix = "study" if entry_kind == "study" else "contract"
    field_label = "study_field" if entry_kind == "study" else "contract_field"
    if "artifact_paths" in entry and not isinstance(entry["artifact_paths"], dict):
        errors.append(
            f"invalid_manifest {field_prefix}={entry_id} "
            f"invalid_{field_label}=artifact_paths"
        )
        return
    if not isinstance(entry.get("artifact_paths"), dict):
        return
    if expected_keys is not None:
        actual_keys = set(entry["artifact_paths"])
        for key in sorted(expected_keys - actual_keys):
            errors.append(f"invalid_manifest {field_prefix}={entry_id} missing_artifact_key={key}")
        for key in sorted(actual_keys - expected_keys):
            errors.append(f"invalid_manifest {field_prefix}={entry_id} unexpected_artifact_key={key}")
    for key, path_text in entry["artifact_paths"].items():
        if not isinstance(path_text, str):
            errors.append(f"invalid_manifest {field_prefix}={entry_id} invalid_artifact_path={key}")
            continue
        expected_extension = expected_extensions.get(key)
        if expected_extension is not None:
            actual_extension = Path(path_text).suffix or "<none>"
            if actual_extension != expected_extension:
                errors.append(
                    f"invalid_manifest {field_prefix}={entry_id} "
                    f"invalid_artifact_extension={key} "
                    f"expected={expected_extension} actual={actual_extension}"
                )


def _validate_contract_entry(entry: dict, errors: list[str]) -> None:
    contract = entry.get("contract", "<unknown>")
    if contract not in CONTRACT_REQUIRED_FIELDS:
        return
    for field in sorted(CONTRACT_REQUIRED_FIELDS[contract]):
        if field not in entry:
            errors.append(
                f"invalid_manifest contract={contract} missing_contract_field={field}"
            )
    for field, expected_type in CONTRACT_FIELD_TYPES.get(contract, {}).items():
        if field in entry and not _matches_manifest_type(entry[field], expected_type):
            errors.append(
                f"invalid_manifest contract={contract} invalid_contract_field_type={field}"
            )
    for field, expected_value in CONTRACT_FIELD_VALUES.get(contract, {}).items():
        expected_type = CONTRACT_FIELD_TYPES.get(contract, {}).get(field)
        if (
            field in entry
            and (expected_type is None or _matches_manifest_type(entry[field], expected_type))
            and entry[field] != expected_value
        ):
            errors.append(
                f"invalid_manifest contract={contract} invalid_contract_field_value={field}"
            )
    _validate_artifact_paths(
        entry,
        errors,
        entry_kind="contract",
        entry_id=contract,
        expected_keys=CONTRACT_ARTIFACT_KEYS.get(contract),
        expected_extensions=CONTRACT_ARTIFACT_EXTENSIONS.get(contract, {}),
    )
    errors.extend(
        _artifact_metadata_shape_errors(
            entry,
            entry_kind="contract",
            entry_id=contract,
            expected_artifact_keys=CONTRACT_ARTIFACT_KEYS.get(contract),
        )
    )


def _observed_ids(entries: list, key: str) -> list[str]:
    return [
        entry.get(key)
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get(key), str)
    ]


def _duplicate_ids(values: list[str]) -> set[str]:
    seen = set()
    duplicates = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates


def _validate_study_collection(manifest: dict, errors: list[str]) -> None:
    expected_studies = set(STUDY_REQUIRED_FIELDS)
    observed_studies = _observed_ids(manifest["studies"], "study")
    for study in sorted(set(observed_studies) - expected_studies):
        errors.append(f"invalid_manifest unknown_study={study}")
    for study in sorted(expected_studies - set(observed_studies)):
        errors.append(f"invalid_manifest missing_study={study}")
    for study in sorted(_duplicate_ids(observed_studies)):
        errors.append(f"invalid_manifest duplicate_study={study}")
    for index, entry in enumerate(manifest["studies"]):
        if not isinstance(entry, dict):
            errors.append(f"invalid_manifest invalid_study_entry_index={index}")
            continue
        _validate_study_entry(entry, errors)


def _validate_contract_collection(manifest: dict, errors: list[str]) -> None:
    expected_contracts = set(CONTRACT_REQUIRED_FIELDS)
    observed_contracts = _observed_ids(manifest["contracts"], "contract")
    for contract in sorted(set(observed_contracts) - expected_contracts):
        errors.append(f"invalid_manifest unknown_contract={contract}")
    for contract in sorted(expected_contracts - set(observed_contracts)):
        errors.append(f"invalid_manifest missing_contract={contract}")
    for contract in sorted(_duplicate_ids(observed_contracts)):
        errors.append(f"invalid_manifest duplicate_contract={contract}")
    for index, entry in enumerate(manifest["contracts"]):
        if not isinstance(entry, dict):
            errors.append(f"invalid_manifest invalid_contract_entry_index={index}")
            continue
        _validate_contract_entry(entry, errors)


def manifest_shape_errors(manifest: object) -> list[str]:
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
    _validate_study_collection(manifest, errors)
    _validate_contract_collection(manifest, errors)
    return errors
