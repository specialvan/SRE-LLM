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
    schema_invalid_event_errors,
)
from analysis.evidence_consistency import study_consistency_errors
from analysis.evidence_contracts import (
    contract_consistency_errors,
    contract_event_errors,
)
from analysis.evidence_manifest_checks import manifest_shape_errors


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


def _print_errors(errors: list[str]) -> None:
    for error in errors:
        print(error)


def _fail(studies_count: int, **counts: int) -> bool:
    count_text = " ".join(f"{key}={value}" for key, value in counts.items())
    print(f"artifact_check failed studies={studies_count} {count_text}")
    return False


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
        return _fail(0, invalid_manifest=1)

    try:
        manifest = json.loads(manifest_text)
    except json.JSONDecodeError:
        print("invalid_manifest malformed_json")
        return _fail(0, invalid_manifest=1)

    shape_errors = manifest_shape_errors(manifest)
    if shape_errors:
        _print_errors(shape_errors)
        studies_count = len(manifest.get("studies", [])) if isinstance(manifest, dict) else 0
        return _fail(studies_count, invalid_manifest=len(shape_errors))

    print(f"evidence_scope {manifest['evidence_scope']}")
    for entry in manifest["studies"]:
        print(_study_line(entry))

    nonportable = nonportable_artifact_paths(manifest, root)
    if nonportable:
        for path_text in nonportable:
            print(f"nonportable_artifact_path {path_text}")
        return _fail(len(manifest["studies"]), nonportable=len(nonportable))

    missing = missing_artifact_paths(manifest, root)
    if missing:
        for path_text in missing:
            print(f"missing_artifact {path_text}")
        return _fail(len(manifest["studies"]), missing=len(missing))

    artifact_identity = artifact_identity_errors(manifest, root)
    _print_errors(artifact_identity)

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
        _print_errors(invalid)
        return _fail(len(manifest["studies"]), invalid=len(invalid))

    inconsistent = [
        error
        for entry in manifest["studies"]
        for error in study_consistency_errors(entry, root)
    ]
    inconsistent.extend(
        error
        for entry in manifest.get("contracts", [])
        for error in contract_consistency_errors(entry, root)
    )
    if inconsistent:
        _print_errors(inconsistent)
        return _fail(len(manifest["studies"]), inconsistent=len(inconsistent))

    schema_invalid = [
        error
        for entry in manifest["studies"]
        for error in schema_invalid_event_errors(entry, root)
    ]
    if schema_invalid:
        _print_errors(schema_invalid)
        return _fail(len(manifest["studies"]), schema_invalid=len(schema_invalid))

    contract_events = contract_event_errors(manifest, root)
    if contract_events:
        _print_errors(contract_events)
        return _fail(len(manifest["studies"]), contract_events=len(contract_events))

    if artifact_identity:
        return _fail(len(manifest["studies"]), artifact_identity=len(artifact_identity))

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
