from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

import pytest

from analysis import _common, evidence_manifest, s10_failure_trace

REPO_ROOT = Path(__file__).resolve().parents[1]


def _resolve_manifest_artifact(path_text: str, repo_root: Path) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    candidate = repo_root / path
    if candidate.exists():
        return candidate
    repo_candidate = REPO_ROOT / path
    if repo_candidate.exists():
        return repo_candidate
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_markdown_table_rows(text: str, header: str) -> list[list[str]]:
    start = text.index(header)
    lines = text[start:].splitlines()
    rows: list[list[str]] = []
    in_table = False
    for line in lines[1:]:
        if not line.startswith("|"):
            if in_table:
                break
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not in_table:
            in_table = True
            continue
        if cells and all(re.fullmatch(r"-+", cell) for cell in cells):
            continue
        rows.append(cells)
    return rows


def test_evidence_manifest_json_writers_reject_non_standard_floats(tmp_path) -> None:
    with pytest.raises(ValueError, match="Out of range float"):
        evidence_manifest._write_json(tmp_path / "bad.json", {"value": float("nan")})

    with pytest.raises(ValueError, match="Out of range float"):
        evidence_manifest._write_jsonl(
            tmp_path / "bad.jsonl",
            [{"value": float("inf")}],
        )


def test_event_evidence_manifest_exports_stable_review_artifacts(tmp_path) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)

    manifest_path = tmp_path / "event_evidence_manifest.json"
    s11_diagnostics_path = tmp_path / "s11_catch_sre_wrapper_diagnostics.json"
    s12_trace_path = tmp_path / "s12_replay_trace.jsonl"
    s12_diagnostics_path = tmp_path / "s12_replay_diagnostics.json"
    stack_contract_path = tmp_path / "sre_stack_data_contract.json"

    assert manifest_path.exists()
    assert s11_diagnostics_path.exists()
    assert s12_trace_path.exists()
    assert s12_diagnostics_path.exists()
    assert stack_contract_path.exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    studies = {entry["study"]: entry for entry in manifest["studies"]}

    assert manifest["evidence_scope"] == "synthetic_sre_event_evidence"
    assert set(studies) == {
        "s10_failure_trace",
        "s11_catch_sre_wrapper",
        "s12_sre_replay",
    }
    contracts = {entry["contract"]: entry for entry in manifest["contracts"]}
    assert set(contracts) == {"sre_stack_data_contract"}
    for study in studies.values():
        for artifact_path in study["artifact_paths"].values():
            assert not Path(artifact_path).is_absolute()
    for contract in contracts.values():
        for artifact_path in contract["artifact_paths"].values():
            assert not Path(artifact_path).is_absolute()
    assert studies["s10_failure_trace"]["artifact_paths"]["full_trace_jsonl"].endswith(
        "s10_trace_full.jsonl"
    )
    assert studies["s10_failure_trace"]["event_count_total"] == 16
    assert studies["s11_catch_sre_wrapper"]["artifact_paths"]["diagnostics_json"].endswith(
        "s11_catch_sre_wrapper_diagnostics.json"
    )
    assert studies["s11_catch_sre_wrapper"]["event_visible_fraction"] == 1.0
    assert studies["s12_sre_replay"]["artifact_paths"]["trace_jsonl"].endswith(
        "s12_replay_trace.jsonl"
    )
    assert studies["s12_sre_replay"]["evidence_label"] == "synthetic_replay_fixture"
    assert studies["s12_sre_replay"]["event_count_total"] == 11
    assert studies["s12_sre_replay"]["multi_signal_window_coverage"] == 1.0
    assert contracts["sre_stack_data_contract"]["evidence_scope"] == (
        "research_stack_data_contract"
    )
    assert contracts["sre_stack_data_contract"]["production_claim"] is False
    assert contracts["sre_stack_data_contract"]["artifact_paths"][
        "contract_json"
    ].endswith("sre_stack_data_contract.json")

    s12_trace_lines = s12_trace_path.read_text(encoding="utf-8").splitlines()
    s12_diagnostics = json.loads(s12_diagnostics_path.read_text(encoding="utf-8"))
    stack_contract = json.loads(stack_contract_path.read_text(encoding="utf-8"))
    assert len(s12_trace_lines) == result["s12"]["diagnostics"]["replay_tick_count"]
    assert s12_diagnostics["event_count_total"] == studies["s12_sre_replay"][
        "event_count_total"
    ]
    assert stack_contract["production_claim"] is False
    assert [stage["stage"] for stage in stack_contract["stages"]] == [
        "observe",
        "stability",
        "plan",
        "guard",
        "allocate",
        "execute",
    ]


def test_event_evidence_manifest_exports_artifact_byte_metadata(tmp_path) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest = json.loads(result["manifest_path"].read_text(encoding="utf-8"))

    for entry in [*manifest["studies"], *manifest["contracts"]]:
        assert set(entry["artifact_metadata"]) == set(entry["artifact_paths"])
        for key, path_text in entry["artifact_paths"].items():
            artifact_path = _resolve_manifest_artifact(path_text, tmp_path)
            metadata = entry["artifact_metadata"][key]
            assert set(metadata) == {"sha256", "size_bytes"}
            assert re.fullmatch(r"[0-9a-f]{64}", metadata["sha256"])
            assert isinstance(metadata["size_bytes"], int)
            assert not isinstance(metadata["size_bytes"], bool)
            assert metadata["size_bytes"] == artifact_path.stat().st_size
            assert metadata["sha256"] == _sha256(artifact_path)


def test_event_evidence_manifest_does_not_patch_artifact_globals(
    tmp_path, monkeypatch
) -> None:
    original_common_artifacts = _common.ARTIFACTS
    original_s10_artifacts = s10_failure_trace.ARTIFACTS

    def assert_artifact_globals_unchanged() -> None:
        assert _common.ARTIFACTS == original_common_artifacts
        assert s10_failure_trace.ARTIFACTS == original_s10_artifacts

    def fake_s10_main(*, artifacts_dir=None):
        assert_artifact_globals_unchanged()
        artifacts = Path(artifacts_dir)
        (artifacts / "s10_trace_full.jsonl").write_text("{}\n", encoding="utf-8")
        (artifacts / "s10_trace_sample.jsonl").write_text("{}\n", encoding="utf-8")
        return {
            "after": {
                "event_count_total": 1,
                "background_event_fraction": 0.0,
            }
        }

    def fake_s11_main(*, artifacts_dir=None):
        assert_artifact_globals_unchanged()
        artifacts = Path(artifacts_dir)
        (artifacts / "s11_catch_sre_wrapper.png").write_bytes(b"png")
        return {
            "after": {"event_visible_fraction": 1.0},
            "diagnostics": {"case_counts": {"feasible": 1}},
        }

    def fake_s12_main():
        assert_artifact_globals_unchanged()
        return {
            "diagnostics": {
                "evidence_label": "synthetic_replay_fixture",
                "event_count_total": 1,
                "replay_tick_count": 1,
                "multi_signal_window_coverage": 1.0,
                "fixture_path": "analysis/fixtures/sre_replay.jsonl",
            },
            "trace": [{"runtime": {"events": []}}],
        }

    monkeypatch.setattr(evidence_manifest.s10_failure_trace, "main", fake_s10_main)
    monkeypatch.setattr(evidence_manifest.s11_catch_sre_wrapper, "main", fake_s11_main)
    monkeypatch.setattr(evidence_manifest.s12_sre_replay, "main", fake_s12_main)
    monkeypatch.setattr(
        evidence_manifest,
        "stack_data_contract",
        lambda: {
            "evidence_scope": "research_stack_data_contract",
            "production_claim": False,
            "orchestration_model": "single_process_research_loop",
        },
    )

    evidence_manifest.main(artifacts_dir=tmp_path)

    assert_artifact_globals_unchanged()


def test_event_evidence_manifest_doc_matches_generated_manifest(tmp_path) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest = result["manifest"]
    doc = (REPO_ROOT / "docs" / "EVENT_EVIDENCE_MANIFEST.md").read_text(
        encoding="utf-8"
    )

    assert "`synthetic_sre_event_evidence`" in doc
    assert "`artifact_metadata`" in doc
    assert "`sha256`" in doc
    assert "`size_bytes`" in doc
    assert "`missing_manifest`" in doc
    study_rows = _parse_markdown_table_rows(doc, "## 2. Study Entries")
    documented_studies = {
        row[0].strip("`"): {
            "required_fields": {
                field.strip().strip("`") for field in row[3].split(",") if field.strip()
            },
            "artifact_keys": {
                field.strip().strip("`") for field in row[4].split(",") if field.strip()
            },
        }
        for row in study_rows
    }

    for entry in manifest["studies"]:
        contract = documented_studies[entry["study"]]
        assert "artifact_metadata" in contract["required_fields"]
        assert contract["required_fields"].issubset(entry)
        assert contract["artifact_keys"] == set(entry["artifact_paths"])

    contract_rows = _parse_markdown_table_rows(doc, "## 3. Contract Entries")
    documented_contracts = {
        row[0].strip("`"): {
            "required_fields": {
                field.strip().strip("`") for field in row[2].split(",") if field.strip()
            },
            "artifact_keys": {
                field.strip().strip("`") for field in row[3].split(",") if field.strip()
            },
        }
        for row in contract_rows
    }

    for entry in manifest["contracts"]:
        contract = documented_contracts[entry["contract"]]
        assert "artifact_metadata" in contract["required_fields"]
        assert contract["required_fields"].issubset(entry)
        assert contract["artifact_keys"] == set(entry["artifact_paths"])


def test_event_evidence_manifest_doc_lists_split_test_ownership() -> None:
    doc = (REPO_ROOT / "docs" / "EVENT_EVIDENCE_MANIFEST.md").read_text(
        encoding="utf-8"
    )
    section = doc.split("## 7. Test Coverage", 1)[1]

    for test_file in [
        "tests/test_evidence_manifest_generation.py",
        "tests/test_evidence_manifest.py",
        "tests/test_evidence_artifacts.py",
        "tests/test_evidence_manifest_checks.py",
        "tests/test_evidence_consistency.py",
        "tests/test_evidence_contracts.py",
        "tests/test_evidence_report_manifest_shape.py",
        "tests/test_evidence_report_study_shape.py",
        "tests/test_evidence_report_contract_shape.py",
        "tests/test_evidence_report_artifact_paths.py",
        "tests/test_evidence_trace_report.py",
        "tests/test_evidence_wrapper_report.py",
        "tests/test_evidence_replay_report.py",
        "tests/test_evidence_replay_consistency_report.py",
        "tests/test_evidence_replay_artifacts_report.py",
        "tests/test_evidence_contract_report.py",
        "tests/test_evidence_contract_fallback_report.py",
        "tests/test_evidence_contract_trace_report.py",
        "tests/test_evidence_contract_boundary_report.py",
    ]:
        assert test_file in section
    assert "tests/test_evidence_manifest.py` verifies that generated manifest entries" not in section


def test_review_backlog_tracks_event_manifest_doc_split_test_ownership() -> None:
    backlog = (REPO_ROOT / "wiki" / "review-backlog.md").read_text(
        encoding="utf-8"
    )
    section = backlog.split("### Cross-Study Event Evidence Manifest", 1)[1].split(
        "### SRE Stack Data Contract", 1
    )[0]

    assert "docs/EVENT_EVIDENCE_MANIFEST.md" in section
    assert "Test Coverage" in section
    assert "split test ownership" in section
    for test_file in [
        "tests/test_evidence_manifest_generation.py",
        "tests/test_evidence_artifacts.py",
        "tests/test_evidence_manifest_checks.py",
        "tests/test_evidence_consistency.py",
        "tests/test_evidence_contracts.py",
        "tests/test_evidence_report_manifest_shape.py",
        "tests/test_evidence_contract_boundary_report.py",
    ]:
        assert test_file in section


def test_stack_data_contract_doc_lists_split_contract_test_ownership() -> None:
    doc = (REPO_ROOT / "docs" / "STACK_DATA_CONTRACT.md").read_text(
        encoding="utf-8"
    )
    section = doc.split("## Test Coverage", 1)[1]

    assert "analysis.evidence_contracts" in section
    for test_file in [
        "tests/test_contracts.py",
        "tests/test_evidence_contracts.py",
        "tests/test_evidence_contract_report.py",
        "tests/test_evidence_contract_fallback_report.py",
        "tests/test_evidence_contract_trace_report.py",
        "tests/test_evidence_contract_boundary_report.py",
    ]:
        assert test_file in section
    assert "analysis.evidence_report` also rejects stack-contract" not in section


def test_review_backlog_tracks_stack_contract_doc_split_test_ownership() -> None:
    backlog = (REPO_ROOT / "wiki" / "review-backlog.md").read_text(
        encoding="utf-8"
    )
    section = backlog.split("### SRE Stack Data Contract", 1)[1].split(
        "### Opus v1.0", 1
    )[0]

    assert "docs/STACK_DATA_CONTRACT.md" in section
    assert "Test Coverage" in section
    assert "split test ownership" in section
    for test_file in [
        "tests/test_contracts.py",
        "tests/test_evidence_contracts.py",
        "tests/test_evidence_contract_report.py",
        "tests/test_evidence_contract_fallback_report.py",
        "tests/test_evidence_contract_trace_report.py",
        "tests/test_evidence_contract_boundary_report.py",
    ]:
        assert test_file in section


def test_current_review_docs_describe_manifest_byte_identity_validation() -> None:
    current_review_docs = [
        "PR-REQUIREMENTS.md",
        "wiki/review-backlog.md",
        "wiki/evidence-ledger.md",
        "docs/V2_Knowledge/knowledge-base.html",
        "docs/codex-review/CODEX_SUMMARY.md",
        "docs/codex-review/ENGINEERING_PACKET.md",
        "docs/codex-review/OPEN_RISKS.md",
        "docs/codex-review/QUALITY_GATES.md",
    ]

    for relative_path in current_review_docs:
        text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert re.search(r"byte[- ]identity", text, re.IGNORECASE), relative_path
        assert re.search(r"sha-?256", text, re.IGNORECASE), relative_path
        assert "size" in text.lower(), relative_path
