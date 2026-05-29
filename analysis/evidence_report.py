"""Reviewer-facing summary for the event evidence manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from analysis.evidence_manifest import REPO_ROOT
from analysis.evidence_artifacts import (
    artifact_identity_errors,
    artifact_paths,
    invalid_artifact_errors,
    missing_artifact_paths,
    nonportable_artifact_paths,
    resolve_artifact,
    schema_invalid_event_errors,
)
from analysis.evidence_contracts import (
    contract_consistency_errors,
    contract_event_errors,
)
from analysis.evidence_manifest_checks import manifest_shape_errors
from analysis import s10_failure_trace


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


def _jsonl_line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


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
        key: resolve_artifact(path_text, root)
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

    shape_errors = manifest_shape_errors(manifest)
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

    nonportable = nonportable_artifact_paths(manifest, root)
    if nonportable:
        for path_text in nonportable:
            print(f"nonportable_artifact_path {path_text}")
        print(
            f"artifact_check failed studies={len(manifest['studies'])} "
            f"nonportable={len(nonportable)}"
        )
        return False

    missing = missing_artifact_paths(manifest, root)
    if missing:
        for path_text in missing:
            print(f"missing_artifact {path_text}")
        print(
            f"artifact_check failed studies={len(manifest['studies'])} "
            f"missing={len(missing)}"
        )
        return False

    artifact_identity = artifact_identity_errors(manifest, root)
    for error in artifact_identity:
        print(error)

    invalid = [
        error
        for entry in manifest["studies"]
        for error in invalid_artifact_errors(entry, root)
    ]
    invalid.extend(
        error
        for entry in manifest.get("contracts", [])
        for error in invalid_artifact_errors(entry, root)
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
        for error in contract_consistency_errors(entry, root)
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
        for error in schema_invalid_event_errors(entry, root)
    ]
    if schema_invalid:
        for error in schema_invalid:
            print(error)
        print(
            f"artifact_check failed studies={len(manifest['studies'])} "
            f"schema_invalid={len(schema_invalid)}"
        )
        return False

    contract_events = contract_event_errors(manifest, root)
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

    file_count = sum(1 for _ in artifact_paths(manifest))
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
