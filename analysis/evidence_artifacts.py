"""Artifact-level checks used by the event evidence report."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable

from analysis import s10_failure_trace
from sre_control.events import EVENT_COUNTEREXAMPLES, validate_event


def resolve_artifact(path_text: str, repo_root: Path) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    candidate = repo_root / path
    if candidate.exists():
        return candidate
    return path


def artifact_paths(manifest: dict) -> Iterable[str]:
    for entry in manifest["studies"]:
        yield from entry["artifact_paths"].values()
    for entry in manifest.get("contracts", []):
        yield from entry["artifact_paths"].values()


def artifact_metadata(path: Path) -> dict:
    data = path.read_bytes()
    return {
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }


def nonportable_artifact_paths(manifest: dict, repo_root: Path) -> list[str]:
    root = repo_root.resolve()
    nonportable = []
    for path_text in artifact_paths(manifest):
        path = Path(path_text)
        if path.is_absolute():
            nonportable.append(path_text)
            continue
        try:
            (root / path).resolve().relative_to(root)
        except ValueError:
            nonportable.append(path_text)
    return nonportable


def missing_artifact_paths(manifest: dict, repo_root: Path) -> list[str]:
    return [
        path_text
        for path_text in artifact_paths(manifest)
        if not resolve_artifact(path_text, repo_root).exists()
    ]


def artifact_identity_errors(manifest: dict, root: Path) -> list[str]:
    errors: list[str] = []
    for entry in [*manifest["studies"], *manifest.get("contracts", [])]:
        for key, path_text in entry["artifact_paths"].items():
            actual = artifact_metadata(resolve_artifact(path_text, root))
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


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _expected_kinds(row: dict) -> list[str]:
    if "expected_kinds" in row:
        return list(row["expected_kinds"])
    expected_kind = row.get("expected_kind")
    return [] if expected_kind is None else [expected_kind]


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
                or not all(isinstance(kind, str) and kind.strip() for kind in expected_kinds)
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
            errors.append(f"invalid_artifact {path_text} invalid_diagnostics_field={field}")
    for field in sorted(count_fields):
        value = diagnostics.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            errors.append(f"invalid_artifact {path_text} invalid_diagnostics_field={field}")
    for field in sorted(nonnegative_number_fields):
        value = diagnostics.get(field)
        if not _is_number(value) or float(value) < 0:
            errors.append(f"invalid_artifact {path_text} invalid_diagnostics_field={field}")
    for field in sorted(fraction_fields):
        value = diagnostics.get(field)
        if not _is_number(value) or not 0 <= float(value) <= 1:
            errors.append(f"invalid_artifact {path_text} invalid_diagnostics_field={field}")
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
                errors.append(f"invalid_artifact {path_text} invalid_operator_action_kind")
                break
            if kind not in EVENT_COUNTEREXAMPLES:
                errors.append(f"invalid_artifact {path_text} unknown_operator_action_kind={kind}")
                break
            if not isinstance(actions, list) or not actions or not all(
                isinstance(action, str) and action.strip() for action in actions
            ):
                errors.append(f"invalid_artifact {path_text} invalid_operator_actions={kind}")
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
                errors.append(f"invalid_artifact {path_text} invalid_window_operator_action_id")
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


def invalid_artifact_errors(entry: dict, root: Path) -> list[str]:
    artifacts = {
        key: resolve_artifact(path_text, root)
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


def schema_invalid_event_errors(entry: dict, root: Path) -> list[str]:
    artifacts = {
        key: resolve_artifact(path_text, root)
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
