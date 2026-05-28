"""Cross-study machine-readable evidence index for SRE event studies.

This module intentionally covers only the event/replay evidence studies
where reviewers need stable artifacts: Section 10, Section 11, and Section 12.
It does not replace ``analysis.run_all``; it creates a compact manifest and
JSON/JSONL payloads that can be inspected without parsing console banners.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from analysis._common import ARTIFACTS
from analysis import s10_failure_trace, s11_catch_sre_wrapper, s12_sre_replay
from sre_control import stack_data_contract

REPO_ROOT = Path(__file__).resolve().parents[1]


def _json_default(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            default=_json_default,
            allow_nan=False,
        ) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(
                json.dumps(
                    row,
                    sort_keys=True,
                    default=_json_default,
                    allow_nan=False,
                ) + "\n"
            )


def _artifact_ref(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.name


def _resolve_artifact_ref(path_text: str, artifacts_dir: Path) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    repo_candidate = REPO_ROOT / path
    if repo_candidate.exists():
        return repo_candidate
    return artifacts_dir / path


def _artifact_metadata(path: Path) -> dict:
    data = path.read_bytes()
    return {
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }


def _attach_artifact_metadata(entry: dict, artifacts_dir: Path) -> None:
    entry["artifact_metadata"] = {
        key: _artifact_metadata(_resolve_artifact_ref(path_text, artifacts_dir))
        for key, path_text in entry["artifact_paths"].items()
    }


def main(artifacts_dir: Path | str | None = None) -> dict:
    artifacts = Path(artifacts_dir) if artifacts_dir is not None else ARTIFACTS
    artifacts.mkdir(parents=True, exist_ok=True)

    s10_result = s10_failure_trace.main(artifacts_dir=artifacts)
    s11_result = s11_catch_sre_wrapper.main(artifacts_dir=artifacts)
    s12_result = s12_sre_replay.main()

    s11_diagnostics_path = artifacts / "s11_catch_sre_wrapper_diagnostics.json"
    s12_trace_path = artifacts / "s12_replay_trace.jsonl"
    s12_diagnostics_path = artifacts / "s12_replay_diagnostics.json"
    stack_contract_path = artifacts / "sre_stack_data_contract.json"
    manifest_path = artifacts / "event_evidence_manifest.json"

    _write_json(s11_diagnostics_path, s11_result["diagnostics"])
    _write_jsonl(s12_trace_path, s12_result["trace"])
    _write_json(s12_diagnostics_path, s12_result["diagnostics"])
    stack_contract = stack_data_contract()
    _write_json(stack_contract_path, stack_contract)

    manifest = {
        "evidence_scope": "synthetic_sre_event_evidence",
        "studies": [
            {
                "study": "s10_failure_trace",
                "section": 10,
                "evidence_label": "synthetic_fault_window_trace",
                "event_count_total": s10_result["after"]["event_count_total"],
                "background_event_fraction": s10_result["after"][
                    "background_event_fraction"
                ],
                "artifact_paths": {
                    "full_trace_jsonl": _artifact_ref(
                        artifacts / "s10_trace_full.jsonl"
                    ),
                    "sample_trace_jsonl": _artifact_ref(
                        artifacts / "s10_trace_sample.jsonl"
                    ),
                },
            },
            {
                "study": "s11_catch_sre_wrapper",
                "section": 11,
                "evidence_label": "synthetic_wrapper_boundary",
                "event_visible_fraction": s11_result["after"][
                    "event_visible_fraction"
                ],
                "case_counts": s11_result["diagnostics"]["case_counts"],
                "artifact_paths": {
                    "diagnostics_json": _artifact_ref(s11_diagnostics_path),
                    "summary_png": _artifact_ref(
                        artifacts / "s11_catch_sre_wrapper.png"
                    ),
                },
            },
            {
                "study": "s12_sre_replay",
                "section": 12,
                "evidence_label": s12_result["diagnostics"]["evidence_label"],
                "event_count_total": s12_result["diagnostics"]["event_count_total"],
                "replay_tick_count": s12_result["diagnostics"]["replay_tick_count"],
                "multi_signal_window_coverage": s12_result["diagnostics"][
                    "multi_signal_window_coverage"
                ],
                "artifact_paths": {
                    "trace_jsonl": _artifact_ref(s12_trace_path),
                    "diagnostics_json": _artifact_ref(s12_diagnostics_path),
                    "fixture_jsonl": s12_result["diagnostics"]["fixture_path"],
                },
            },
        ],
        "contracts": [
            {
                "contract": "sre_stack_data_contract",
                "evidence_scope": stack_contract["evidence_scope"],
                "production_claim": stack_contract["production_claim"],
                "orchestration_model": stack_contract["orchestration_model"],
                "artifact_paths": {
                    "contract_json": _artifact_ref(stack_contract_path),
                },
            },
        ],
    }
    for entry in manifest["studies"]:
        _attach_artifact_metadata(entry, artifacts)
    for entry in manifest["contracts"]:
        _attach_artifact_metadata(entry, artifacts)

    _write_json(manifest_path, manifest)

    return {
        "manifest": manifest,
        "manifest_path": manifest_path,
        "s10": s10_result,
        "s11": s11_result,
        "s12": s12_result,
        "stack_contract": stack_contract,
    }


if __name__ == "__main__":
    result = main()
    print(f"wrote {result['manifest_path']}")
