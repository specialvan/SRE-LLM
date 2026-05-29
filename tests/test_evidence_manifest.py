from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

import pytest

from analysis import _common, evidence_manifest, evidence_report, s10_failure_trace

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


def _replace_first_s10_trace_event(result: dict, tmp_path: Path, event: dict) -> None:
    manifest_path = result['manifest_path']
    full_path = tmp_path / 's10_trace_full.jsonl'
    sample_path = tmp_path / 's10_trace_sample.jsonl'
    full_rows = [
        json.loads(line)
        for line in full_path.read_text(encoding='utf-8').splitlines()
        if line.strip()
    ]
    sample_rows = [
        json.loads(line)
        for line in sample_path.read_text(encoding='utf-8').splitlines()
        if line.strip()
    ]
    replacement = {
        **event,
        't_seconds': full_rows[0]['t_seconds'],
        'tick': full_rows[0]['tick'],
    }
    full_rows[0] = replacement
    sample_rows[0] = replacement
    for path, rows in [(full_path, full_rows), (sample_path, sample_rows)]:
        path.write_text(
            '\n'.join(json.dumps(row, sort_keys=True) for row in rows) + '\n',
            encoding='utf-8',
        )

    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    for entry in manifest['studies']:
        if entry['study'] == 's10_failure_trace':
            for key, path in {
                'full_trace_jsonl': full_path,
                'sample_trace_jsonl': sample_path,
            }.items():
                entry['artifact_metadata'][key] = {
                    'sha256': _sha256(path),
                    'size_bytes': path.stat().st_size,
                }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + '\n',
        encoding='utf-8',
    )


def _fake_artifact_metadata(entry: dict) -> dict:
    return {
        key: {"sha256": "0" * 64, "size_bytes": 0}
        for key in entry["artifact_paths"]
    }


def _fill_fake_artifact_metadata(manifest: dict) -> None:
    for entry in manifest["studies"]:
        entry["artifact_metadata"] = _fake_artifact_metadata(entry)
    for entry in manifest["contracts"]:
        entry["artifact_metadata"] = _fake_artifact_metadata(entry)


def test_evidence_report_unrecovered_window_uses_strict_json_null() -> None:
    rows = [{"expected_kind": "missing_sensor"}]
    trace_rows = [{"runtime": {"events": [{"kind": "missing_sensor"}]}}]

    diagnostics = evidence_report._recovery_diagnostics(rows, trace_rows)

    assert diagnostics["recovered_window_fraction"] == 0.0
    assert diagnostics["max_recovery_ticks"] is None
    json.dumps(diagnostics, allow_nan=False)


def test_evidence_report_unrecovered_multi_signal_window_uses_strict_json_null() -> None:
    rows = [
        {
            "incident_id": "compound",
            "expected_kinds": ["missing_sensor", "replica_bound_active"],
        }
    ]
    trace_rows = [
        {
            "runtime": {
                "events": [
                    {"kind": "missing_sensor"},
                    {"kind": "replica_bound_active"},
                ]
            }
        }
    ]

    diagnostics = evidence_report._multi_signal_window_diagnostics(rows, trace_rows)

    assert diagnostics["multi_signal_window_recovered_fraction"] == 0.0
    assert diagnostics["max_multi_signal_recovery_ticks"] is None
    json.dumps(diagnostics, allow_nan=False)


def test_evidence_manifest_json_writers_reject_non_standard_floats(tmp_path) -> None:
    with pytest.raises(ValueError, match="Out of range float"):
        evidence_manifest._write_json(tmp_path / "bad.json", {"value": float("nan")})

    with pytest.raises(ValueError, match="Out of range float"):
        evidence_manifest._write_jsonl(
            tmp_path / "bad.jsonl",
            [{"value": float("inf")}],
        )


def test_evidence_report_accepts_uppercase_sha256_shape() -> None:
    assert evidence_report._is_sha256("A" * 64) is True
    assert evidence_report._is_sha256("F" * 64) is True


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
    assert s12_diagnostics["event_count_total"] == studies["s12_sre_replay"]["event_count_total"]
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


def test_event_evidence_report_validates_manifest_artifacts(tmp_path, capsys) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is True
    assert "evidence_scope synthetic_sre_event_evidence" in output
    assert "s10_failure_trace section=10 events=16" in output
    assert "s11_catch_sre_wrapper section=11 visible=1.0" in output
    assert "s12_sre_replay section=12 events=11.0 ticks=19" in output
    assert "artifact_check ok studies=3 files=8" in output


def test_event_evidence_report_rejects_artifact_byte_identity_mismatch(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    diagnostics_path = tmp_path / "s11_catch_sre_wrapper_diagnostics.json"
    diagnostics_path.write_text(
        diagnostics_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "artifact_identity_mismatch s11_catch_sre_wrapper_diagnostics.json"
    ) in output
    assert "expected_sha256=" in output
    assert "actual_sha256=" in output
    assert "expected_size_bytes=" in output
    assert "actual_size_bytes=" in output
    assert "artifact_check failed studies=3 artifact_identity=1" in output


def test_event_evidence_report_rejects_missing_artifact_metadata(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _fill_fake_artifact_metadata(manifest)
    manifest["studies"][0].pop("artifact_metadata", None)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=manifest_path,
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "invalid_manifest study=s10_failure_trace "
        "missing_study_field=artifact_metadata"
    ) in output
    assert "artifact_check failed studies=3 invalid_manifest=1" in output


def test_event_evidence_report_rejects_artifact_metadata_key_mismatch(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _fill_fake_artifact_metadata(manifest)
    manifest["studies"][0]["artifact_metadata"].pop("full_trace_jsonl")
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=manifest_path,
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "invalid_manifest study=s10_failure_trace "
        "missing_artifact_metadata_key=full_trace_jsonl"
    ) in output
    assert "artifact_check failed studies=3 invalid_manifest=1" in output


def test_event_evidence_report_rejects_malformed_artifact_metadata(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _fill_fake_artifact_metadata(manifest)
    manifest["studies"][0]["artifact_metadata"]["full_trace_jsonl"][
        "sha256"
    ] = "not-a-sha256"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=manifest_path,
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "invalid_manifest study=s10_failure_trace "
        "invalid_artifact_metadata=full_trace_jsonl"
    ) in output
    assert "artifact_check failed studies=3 invalid_manifest=1" in output


def test_event_evidence_report_rejects_missing_artifact(tmp_path, capsys) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    missing_path = tmp_path / "s12_replay_trace.jsonl"
    missing_path.unlink()

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert "missing_artifact s12_replay_trace.jsonl" in output
    assert "artifact_check failed studies=3 missing=1" in output


def test_event_evidence_report_rejects_missing_top_level_studies(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("studies")
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=manifest_path,
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert "invalid_manifest missing_top_level_field=studies" in output
    assert "artifact_check failed studies=0 invalid_manifest=1" in output


def test_event_evidence_report_rejects_malformed_manifest_json(
    tmp_path, capsys
) -> None:
    manifest_path = tmp_path / "event_evidence_manifest.json"
    manifest_path.write_text("{not-json", encoding="utf-8")

    try:
        ok = evidence_report.main(
            manifest_path=manifest_path,
            repo_root=tmp_path,
        )
    except json.JSONDecodeError as exc:
        pytest.fail(f"report crashed instead of rejecting malformed manifest: {exc}")
    output = capsys.readouterr().out

    assert ok is False
    assert "invalid_manifest malformed_json" in output
    assert "artifact_check failed studies=0 invalid_manifest=1" in output


def test_event_evidence_report_rejects_missing_manifest_file(
    tmp_path, capsys
) -> None:
    manifest_path = tmp_path / "event_evidence_manifest.json"

    try:
        ok = evidence_report.main(
            manifest_path=manifest_path,
            repo_root=tmp_path,
        )
    except FileNotFoundError as exc:
        pytest.fail(f"report crashed instead of rejecting missing manifest: {exc}")
    output = capsys.readouterr().out

    assert ok is False
    assert f"invalid_manifest missing_manifest {manifest_path}" in output
    assert "artifact_check failed studies=0 invalid_manifest=1" in output


def test_event_evidence_report_rejects_missing_study_artifact_paths(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["studies"][0].pop("artifact_paths")
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=manifest_path,
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "invalid_manifest study=s10_failure_trace "
        "missing_study_field=artifact_paths"
    ) in output
    assert "artifact_check failed studies=3 invalid_manifest=1" in output


def test_event_evidence_report_rejects_missing_study_specific_field(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["studies"][0].pop("event_count_total")
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=manifest_path,
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "invalid_manifest study=s10_failure_trace "
        "missing_study_field=event_count_total"
    ) in output
    assert "artifact_check failed studies=3 invalid_manifest=1" in output


def test_event_evidence_report_rejects_unknown_study_id(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["studies"][0] = {
        "study": "s99_unreviewed_study",
        "section": 99,
        "artifact_paths": {"unreviewed_json": "s11_catch_sre_wrapper_diagnostics.json"},
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=manifest_path,
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert "invalid_manifest unknown_study=s99_unreviewed_study" in output
    assert "invalid_manifest missing_study=s10_failure_trace" in output
    assert "artifact_check failed studies=3 invalid_manifest=2" in output


def test_event_evidence_report_rejects_duplicate_and_missing_study_entries(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["studies"][2] = dict(manifest["studies"][0])
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=manifest_path,
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert "invalid_manifest duplicate_study=s10_failure_trace" in output
    assert "invalid_manifest missing_study=s12_sre_replay" in output
    assert "artifact_check failed studies=3 invalid_manifest=2" in output


def test_event_evidence_report_rejects_invalid_study_field_type(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["studies"][0]["event_count_total"] = "16"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=manifest_path,
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "invalid_manifest study=s10_failure_trace "
        "invalid_study_field_type=event_count_total"
    ) in output
    assert "artifact_check failed studies=3 invalid_manifest=1" in output


def test_event_evidence_report_rejects_s10_background_fraction_mismatch(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["studies"][0]["background_event_fraction"] = 0.5
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=manifest_path,
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "inconsistent_artifact s10_trace_full.jsonl "
        "background_event_fraction_mismatch"
    ) in output
    assert "artifact_check failed studies=3 inconsistent=1" in output


def test_event_evidence_report_rejects_s10_sample_trace_prefix_mismatch(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    full_path = tmp_path / "s10_trace_full.jsonl"
    sample_path = tmp_path / "s10_trace_sample.jsonl"
    full_rows = full_path.read_text(encoding="utf-8").splitlines()
    sample_rows = sample_path.read_text(encoding="utf-8").splitlines()
    sample_rows[0] = full_rows[-1]
    sample_path.write_text("\n".join(sample_rows) + "\n", encoding="utf-8")

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "inconsistent_artifact s10_trace_sample.jsonl "
        "sample_trace_prefix_mismatch"
    ) in output
    assert "artifact_check failed studies=3 inconsistent=1" in output


def test_event_evidence_report_rejects_empty_s10_sample_trace(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    sample_path = tmp_path / "s10_trace_sample.jsonl"
    sample_path.write_text("", encoding="utf-8")

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert "inconsistent_artifact s10_trace_sample.jsonl sample_trace_empty" in output
    assert "artifact_check failed studies=3 inconsistent=1" in output


@pytest.mark.parametrize("field", ["tick", "t_seconds"])
def test_event_evidence_report_rejects_invalid_s10_trace_time_field(
    tmp_path, capsys, field
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    trace_path = tmp_path / "s10_trace_full.jsonl"
    rows = [
        json.loads(line)
        for line in trace_path.read_text(encoding="utf-8").splitlines()
    ]
    rows[0].pop(field)
    trace_path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "invalid_artifact s10_trace_full.jsonl line=1 "
        f"invalid_trace_field={field}"
    ) in output
    assert "artifact_check failed studies=3 invalid=1" in output


def test_event_evidence_report_rejects_s10_trace_time_mismatch(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    trace_path = tmp_path / "s10_trace_full.jsonl"
    sample_path = tmp_path / "s10_trace_sample.jsonl"
    rows = [
        json.loads(line)
        for line in trace_path.read_text(encoding="utf-8").splitlines()
    ]
    sample_rows = [
        json.loads(line)
        for line in sample_path.read_text(encoding="utf-8").splitlines()
    ]
    rows[0]["t_seconds"] = rows[0]["t_seconds"] + 1.0
    sample_rows[0]["t_seconds"] = sample_rows[0]["t_seconds"] + 1.0
    trace_path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )
    sample_path.write_text(
        "\n".join(json.dumps(row) for row in sample_rows) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "invalid_artifact s10_trace_full.jsonl line=1 "
        "trace_time_mismatch"
    ) in output
    assert "artifact_check failed studies=3 invalid=1" in output


def test_s10_trace_shape_allows_float_accumulation_drift(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(evidence_report.s10_failure_trace, "DT", 0.1)
    tick = 1_000
    accumulated_time = tick * 0.1 + 2e-9
    trace_path = tmp_path / "s10_trace_full.jsonl"
    trace_path.write_text(
        json.dumps({"tick": tick, "t_seconds": accumulated_time}) + "\n",
        encoding="utf-8",
    )

    errors = evidence_report._s10_trace_shape_errors(
        trace_path,
        "s10_trace_full.jsonl",
    )

    assert errors == []


def test_s10_trace_shape_collects_all_invalid_rows(tmp_path) -> None:
    trace_path = tmp_path / "s10_trace_full.jsonl"
    trace_path.write_text(
        "\n".join(
            [
                json.dumps({"tick": -1, "t_seconds": 0.0}),
                json.dumps({"tick": 1, "t_seconds": -0.1}),
                json.dumps({"tick": 2, "t_seconds": 999.0}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    errors = evidence_report._s10_trace_shape_errors(
        trace_path,
        "s10_trace_full.jsonl",
    )

    assert errors == [
        "invalid_artifact s10_trace_full.jsonl line=1 invalid_trace_field=tick",
        "invalid_artifact s10_trace_full.jsonl line=2 invalid_trace_field=t_seconds",
        "invalid_artifact s10_trace_full.jsonl line=3 trace_time_mismatch",
    ]


def test_jsonl_validation_collects_all_invalid_rows(tmp_path) -> None:
    trace_path = tmp_path / "bad.jsonl"
    trace_path.write_text(
        "\n".join(
            [
                "{not-json",
                json.dumps(["not", "object"]),
                json.dumps({"valid": True}),
                json.dumps(5),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    errors = evidence_report._invalid_jsonl_errors(trace_path, "bad.jsonl")

    assert errors == [
        "invalid_artifact bad.jsonl line=1",
        "invalid_artifact bad.jsonl line=2 top_level_must_be_object",
        "invalid_artifact bad.jsonl line=4 top_level_must_be_object",
    ]


def test_s12_fixture_shape_collects_all_invalid_rows(tmp_path) -> None:
    fixture_path = tmp_path / "sre_replay.jsonl"
    fixture_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "expected_kind": "missing_sensor",
                        "expected_kinds": ["missing_sensor"],
                    }
                ),
                json.dumps({"expected_kinds": []}),
                json.dumps({"expected_kind": ""}),
                json.dumps({"expected_kind": "not_registered"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    errors = evidence_report._s12_fixture_shape_errors(
        fixture_path,
        "sre_replay.jsonl",
    )

    assert errors == [
        (
            "invalid_artifact sre_replay.jsonl line=1 "
            "invalid_fixture_field=expected_kind_conflict"
        ),
        "invalid_artifact sre_replay.jsonl line=2 invalid_fixture_field=expected_kinds",
        "invalid_artifact sre_replay.jsonl line=3 invalid_fixture_field=expected_kind",
        (
            "invalid_artifact sre_replay.jsonl line=4 "
            "unknown_fixture_expected_kind=not_registered"
        ),
    ]


def test_schema_validation_collects_all_invalid_s10_events(tmp_path) -> None:
    trace_path = tmp_path / "s10_trace_full.jsonl"
    trace_path.write_text(
        "\n".join(
            [
                json.dumps({"tick": 0, "t_seconds": 0.0}),
                json.dumps({"tick": 1, "t_seconds": 5.0, "kind": "missing_sensor"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    entry = {
        "study": "s10_failure_trace",
        "artifact_paths": {"full_trace_jsonl": "s10_trace_full.jsonl"},
    }

    errors = evidence_report._schema_invalid_event_errors(entry, tmp_path)

    assert errors == [
        "schema_invalid_event s10_trace_full.jsonl line=1",
        "schema_invalid_event s10_trace_full.jsonl line=2",
    ]


def test_event_evidence_report_rejects_boolean_numeric_study_field(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["studies"][0]["background_event_fraction"] = False
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=manifest_path,
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "invalid_manifest study=s10_failure_trace "
        "invalid_study_field_type=background_event_fraction"
    ) in output
    assert "artifact_check failed studies=3 invalid_manifest=1" in output


def test_event_evidence_report_rejects_unexpected_study_field_value(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["studies"][0]["evidence_label"] = "production_trace"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=manifest_path,
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "invalid_manifest study=s10_failure_trace "
        "invalid_study_field_value=evidence_label"
    ) in output
    assert "artifact_check failed studies=3 invalid_manifest=1" in output


def test_event_evidence_report_rejects_out_of_range_fraction_field(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["studies"][1]["event_visible_fraction"] = 1.5
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=manifest_path,
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "invalid_manifest study=s11_catch_sre_wrapper "
        "invalid_study_field_range=event_visible_fraction"
    ) in output
    assert "artifact_check failed studies=3 invalid_manifest=1" in output


def test_event_evidence_report_rejects_invalid_s11_case_counts_shape(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["studies"][1]["case_counts"] = {
        "feasible": "40",
        "total_overload": 40,
        "unreviewed_case": 40,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=manifest_path,
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "invalid_manifest study=s11_catch_sre_wrapper "
        "missing_case_count=placement_infeasible"
    ) in output
    assert (
        "invalid_manifest study=s11_catch_sre_wrapper "
        "unexpected_case_count=unreviewed_case"
    ) in output
    assert (
        "invalid_manifest study=s11_catch_sre_wrapper "
        "invalid_case_count=feasible"
    ) in output
    assert "artifact_check failed studies=3 invalid_manifest=3" in output


def test_event_evidence_report_rejects_boolean_s11_case_count(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["studies"][1]["case_counts"]["feasible"] = True
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=manifest_path,
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "invalid_manifest study=s11_catch_sre_wrapper "
        "invalid_case_count=feasible"
    ) in output
    assert "artifact_check failed studies=3 invalid_manifest=1" in output


def test_event_evidence_report_rejects_negative_count_field(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["studies"][2]["replay_tick_count"] = -1
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=manifest_path,
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "invalid_manifest study=s12_sre_replay "
        "invalid_study_field_range=replay_tick_count"
    ) in output
    assert "artifact_check failed studies=3 invalid_manifest=1" in output


def test_event_evidence_report_rejects_missing_contract_artifact_paths(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["contracts"][0].pop("artifact_paths")
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=manifest_path,
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "invalid_manifest contract=sre_stack_data_contract "
        "missing_contract_field=artifact_paths"
    ) in output
    assert "artifact_check failed studies=3 invalid_manifest=1" in output


def test_event_evidence_report_rejects_missing_contract_specific_field(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["contracts"][0].pop("production_claim")
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=manifest_path,
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "invalid_manifest contract=sre_stack_data_contract "
        "missing_contract_field=production_claim"
    ) in output
    assert "artifact_check failed studies=3 invalid_manifest=1" in output


def test_event_evidence_report_rejects_unknown_contract_id(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["contracts"][0] = {
        "contract": "unreviewed_contract",
        "artifact_paths": {"contract_json": "sre_stack_data_contract.json"},
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=manifest_path,
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert "invalid_manifest unknown_contract=unreviewed_contract" in output
    assert "invalid_manifest missing_contract=sre_stack_data_contract" in output
    assert "artifact_check failed studies=3 invalid_manifest=2" in output


def test_event_evidence_report_rejects_duplicate_contract_entries(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["contracts"].append(dict(manifest["contracts"][0]))
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=manifest_path,
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert "invalid_manifest duplicate_contract=sre_stack_data_contract" in output
    assert "artifact_check failed studies=3 invalid_manifest=1" in output


def test_event_evidence_report_rejects_invalid_contract_field_type(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["contracts"][0]["production_claim"] = "false"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=manifest_path,
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "invalid_manifest contract=sre_stack_data_contract "
        "invalid_contract_field_type=production_claim"
    ) in output
    assert "artifact_check failed studies=3 invalid_manifest=1" in output


def test_event_evidence_report_rejects_unexpected_contract_field_value(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["contracts"][0]["production_claim"] = True
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=manifest_path,
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "invalid_manifest contract=sre_stack_data_contract "
        "invalid_contract_field_value=production_claim"
    ) in output
    assert "artifact_check failed studies=3 invalid_manifest=1" in output


def test_event_evidence_report_rejects_absolute_artifact_path(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    absolute_path = tmp_path / "s10_trace_full.jsonl"
    manifest["studies"][0]["artifact_paths"]["full_trace_jsonl"] = str(absolute_path)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=manifest_path,
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert f"nonportable_artifact_path {absolute_path}" in output
    assert "artifact_check failed studies=3 nonportable=1" in output


def test_event_evidence_report_rejects_parent_directory_artifact_path(
    tmp_path, capsys
) -> None:
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    result = evidence_manifest.main(artifacts_dir=artifact_dir)
    outside_trace = tmp_path / "outside_trace.jsonl"
    outside_trace.write_text(
        (artifact_dir / "s10_trace_full.jsonl").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["studies"][0]["artifact_paths"]["full_trace_jsonl"] = (
        "../outside_trace.jsonl"
    )
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=manifest_path,
        repo_root=artifact_dir,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert "nonportable_artifact_path ../outside_trace.jsonl" in output
    assert "artifact_check failed studies=3 nonportable=1" in output


def test_event_evidence_report_rejects_non_string_artifact_path(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["studies"][0]["artifact_paths"]["full_trace_jsonl"] = 123
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=manifest_path,
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "invalid_manifest study=s10_failure_trace "
        "invalid_artifact_path=full_trace_jsonl"
    ) in output
    assert "artifact_check failed studies=3 invalid_manifest=1" in output


def test_event_evidence_report_rejects_missing_required_artifact_key(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["studies"][0]["artifact_paths"]["renamed_trace_jsonl"] = manifest[
        "studies"
    ][0]["artifact_paths"].pop("full_trace_jsonl")
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=manifest_path,
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "invalid_manifest study=s10_failure_trace "
        "missing_artifact_key=full_trace_jsonl"
    ) in output
    assert (
        "invalid_manifest study=s10_failure_trace "
        "unexpected_artifact_key=renamed_trace_jsonl"
    ) in output
    assert "artifact_check failed studies=3 invalid_manifest=2" in output


def test_event_evidence_report_rejects_missing_required_contract_artifact_key(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["contracts"][0]["artifact_paths"]["renamed_contract_json"] = manifest[
        "contracts"
    ][0]["artifact_paths"].pop("contract_json")
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=manifest_path,
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "invalid_manifest contract=sre_stack_data_contract "
        "missing_artifact_key=contract_json"
    ) in output
    assert (
        "invalid_manifest contract=sre_stack_data_contract "
        "unexpected_artifact_key=renamed_contract_json"
    ) in output
    assert "artifact_check failed studies=3 invalid_manifest=2" in output


def test_event_evidence_report_rejects_wrong_artifact_extension(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    wrong_suffix_path = tmp_path / "s11_catch_sre_wrapper.txt"
    wrong_suffix_path.write_bytes((tmp_path / "s11_catch_sre_wrapper.png").read_bytes())
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["studies"][1]["artifact_paths"]["summary_png"] = wrong_suffix_path.name
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=manifest_path,
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "invalid_manifest study=s11_catch_sre_wrapper "
        "invalid_artifact_extension=summary_png expected=.png actual=.txt"
    ) in output
    assert "artifact_check failed studies=3 invalid_manifest=1" in output


def test_event_evidence_report_rejects_wrong_contract_artifact_extension(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    wrong_suffix_path = tmp_path / "sre_stack_data_contract.txt"
    wrong_suffix_path.write_text(
        (tmp_path / "sre_stack_data_contract.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["contracts"][0]["artifact_paths"]["contract_json"] = wrong_suffix_path.name
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=manifest_path,
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "invalid_manifest contract=sre_stack_data_contract "
        "invalid_artifact_extension=contract_json expected=.json actual=.txt"
    ) in output
    assert "artifact_check failed studies=3 invalid_manifest=1" in output


def test_event_evidence_report_rejects_inconsistent_artifact_content(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    (tmp_path / "s12_replay_trace.jsonl").write_text("{}\n", encoding="utf-8")

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert "inconsistent_artifact s12_replay_trace.jsonl expected_lines=19 actual_lines=1" in output
    assert "artifact_check failed studies=3 inconsistent=1" in output


def test_event_evidence_report_rejects_malformed_jsonl_artifact(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    trace_path = tmp_path / "s12_replay_trace.jsonl"
    lines = trace_path.read_text(encoding="utf-8").splitlines()
    lines[0] = "{not-json"
    trace_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert "invalid_artifact s12_replay_trace.jsonl line=1" in output
    assert "artifact_check failed studies=3 invalid=1" in output


def test_event_evidence_report_rejects_non_object_jsonl_row(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    trace_path = tmp_path / "s12_replay_trace.jsonl"
    lines = trace_path.read_text(encoding="utf-8").splitlines()
    lines[0] = "[]"
    trace_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    try:
        ok = evidence_report.main(
            manifest_path=result["manifest_path"],
            repo_root=tmp_path,
        )
    except AttributeError as exc:
        pytest.fail(f"report crashed instead of rejecting JSONL row shape: {exc}")
    output = capsys.readouterr().out

    assert ok is False
    assert "invalid_artifact s12_replay_trace.jsonl line=1 top_level_must_be_object" in output
    assert "artifact_check failed studies=3 invalid=1" in output


def test_event_evidence_report_rejects_invalid_s12_trace_runtime_shape(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    trace_path = tmp_path / "s12_replay_trace.jsonl"
    rows = [
        json.loads(line)
        for line in trace_path.read_text(encoding="utf-8").splitlines()
    ]
    rows[0]["runtime"] = "not-a-runtime-object"
    trace_path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )

    try:
        ok = evidence_report.main(
            manifest_path=result["manifest_path"],
            repo_root=tmp_path,
        )
    except AttributeError as exc:
        pytest.fail(f"report crashed instead of rejecting runtime shape: {exc}")
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "invalid_artifact s12_replay_trace.jsonl line=1 "
        "invalid_runtime_field=runtime"
    ) in output
    assert "artifact_check failed studies=3 invalid=1" in output


def test_event_evidence_report_rejects_non_object_s12_runtime_event(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    trace_path = tmp_path / "s12_replay_trace.jsonl"
    rows = [
        json.loads(line)
        for line in trace_path.read_text(encoding="utf-8").splitlines()
    ]
    for row_index, row in enumerate(rows, start=1):
        events = row.get("runtime", {}).get("events", [])
        if events:
            events[0] = "not-an-event-object"
            trace_path.write_text(
                "\n".join(json.dumps(row) for row in rows) + "\n",
                encoding="utf-8",
            )

            ok = evidence_report.main(
                manifest_path=result["manifest_path"],
                repo_root=tmp_path,
            )
            output = capsys.readouterr().out

            assert ok is False
            assert (
                f"invalid_artifact s12_replay_trace.jsonl line={row_index} "
                "invalid_runtime_event=0"
            ) in output
            assert "artifact_check failed studies=3 invalid=1" in output
            return

    raise AssertionError("fixture did not emit runtime events")


def test_event_evidence_report_rejects_invalid_s12_fixture_expected_kinds_shape(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    fixture_path = REPO_ROOT / "analysis" / "fixtures" / "sre_replay.jsonl"
    rows = [
        json.loads(line)
        for line in fixture_path.read_text(encoding="utf-8").splitlines()
    ]
    rows[15]["expected_kinds"] = "missing_sensor"
    fixture_copy = tmp_path / "sre_replay_bad_expected_kinds.jsonl"
    fixture_copy.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["studies"][2]["artifact_paths"]["fixture_jsonl"] = fixture_copy.name
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    diagnostics_path = tmp_path / "s12_replay_diagnostics.json"
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    diagnostics["fixture_path"] = fixture_copy.name
    diagnostics_path.write_text(
        json.dumps(diagnostics, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=manifest_path,
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "invalid_artifact sre_replay_bad_expected_kinds.jsonl line=16 "
        "invalid_fixture_field=expected_kinds"
    ) in output
    assert "artifact_check failed studies=3 invalid=1" in output


def test_event_evidence_report_rejects_empty_s12_fixture_expected_kinds(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    fixture_path = REPO_ROOT / "analysis" / "fixtures" / "sre_replay.jsonl"
    rows = [
        json.loads(line)
        for line in fixture_path.read_text(encoding="utf-8").splitlines()
    ]
    rows[15]["expected_kinds"] = []
    fixture_copy = tmp_path / "sre_replay_empty_expected_kinds.jsonl"
    fixture_copy.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["studies"][2]["artifact_paths"]["fixture_jsonl"] = fixture_copy.name
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=manifest_path,
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "invalid_artifact sre_replay_empty_expected_kinds.jsonl line=16 "
        "invalid_fixture_field=expected_kinds"
    ) in output
    assert "artifact_check failed studies=3 invalid=1" in output


def test_event_evidence_report_rejects_unknown_s12_fixture_expected_kind(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    fixture_path = REPO_ROOT / "analysis" / "fixtures" / "sre_replay.jsonl"
    rows = [
        json.loads(line)
        for line in fixture_path.read_text(encoding="utf-8").splitlines()
    ]
    rows[4]["expected_kind"] = "unknown_runtime_event"
    fixture_copy = tmp_path / "sre_replay_unknown_expected_kind.jsonl"
    fixture_copy.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["studies"][2]["artifact_paths"]["fixture_jsonl"] = fixture_copy.name
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=manifest_path,
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "invalid_artifact sre_replay_unknown_expected_kind.jsonl line=5 "
        "unknown_fixture_expected_kind=unknown_runtime_event"
    ) in output
    assert "artifact_check failed studies=3 invalid=1" in output


def test_event_evidence_report_rejects_blank_s12_fixture_expected_kind(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    fixture_path = REPO_ROOT / "analysis" / "fixtures" / "sre_replay.jsonl"
    rows = [
        json.loads(line)
        for line in fixture_path.read_text(encoding="utf-8").splitlines()
    ]
    rows[4]["expected_kind"] = "   "
    fixture_copy = tmp_path / "sre_replay_blank_expected_kind.jsonl"
    fixture_copy.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["studies"][2]["artifact_paths"]["fixture_jsonl"] = fixture_copy.name
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=manifest_path,
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "invalid_artifact sre_replay_blank_expected_kind.jsonl line=5 "
        "invalid_fixture_field=expected_kind"
    ) in output
    assert "artifact_check failed studies=3 invalid=1" in output


def test_event_evidence_report_rejects_conflicting_s12_fixture_expected_fields(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    fixture_path = REPO_ROOT / "analysis" / "fixtures" / "sre_replay.jsonl"
    rows = [
        json.loads(line)
        for line in fixture_path.read_text(encoding="utf-8").splitlines()
    ]
    rows[15]["expected_kind"] = "missing_sensor"
    fixture_copy = tmp_path / "sre_replay_conflicting_expected_fields.jsonl"
    fixture_copy.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["studies"][2]["artifact_paths"]["fixture_jsonl"] = fixture_copy.name
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=manifest_path,
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "invalid_artifact sre_replay_conflicting_expected_fields.jsonl line=16 "
        "invalid_fixture_field=expected_kind_conflict"
    ) in output
    assert "artifact_check failed studies=3 invalid=1" in output


def test_event_evidence_report_rejects_malformed_png_artifact(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    summary_path = tmp_path / "s11_catch_sre_wrapper.png"
    summary_path.write_text("not a png", encoding="utf-8")

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert "invalid_artifact s11_catch_sre_wrapper.png invalid_png" in output
    assert "artifact_check failed studies=3 invalid=1" in output


def test_event_evidence_report_rejects_non_object_json_artifact(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    diagnostics_path = tmp_path / "s11_catch_sre_wrapper_diagnostics.json"
    diagnostics_path.write_text("[]\n", encoding="utf-8")

    try:
        ok = evidence_report.main(
            manifest_path=result["manifest_path"],
            repo_root=tmp_path,
        )
    except (KeyError, TypeError) as exc:
        pytest.fail(f"report crashed instead of rejecting artifact shape: {exc}")
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "invalid_artifact s11_catch_sre_wrapper_diagnostics.json "
        "top_level_must_be_object"
    ) in output
    assert "artifact_check failed studies=3 invalid=1" in output


def test_event_evidence_report_rejects_missing_s11_diagnostics_case_counts(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    diagnostics_path = tmp_path / "s11_catch_sre_wrapper_diagnostics.json"
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    diagnostics.pop("case_counts")
    diagnostics_path.write_text(
        json.dumps(diagnostics, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    try:
        ok = evidence_report.main(
            manifest_path=result["manifest_path"],
            repo_root=tmp_path,
        )
    except KeyError as exc:
        pytest.fail(f"report crashed instead of rejecting S11 diagnostics: {exc}")
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "invalid_artifact s11_catch_sre_wrapper_diagnostics.json "
        "missing_diagnostics_field=case_counts"
    ) in output
    assert "artifact_check failed studies=3 invalid=1" in output


def test_event_evidence_report_rejects_invalid_s11_diagnostics_case_counts(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    diagnostics_path = tmp_path / "s11_catch_sre_wrapper_diagnostics.json"
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    diagnostics["case_counts"] = {
        "feasible": True,
        "total_overload": 40,
        "unreviewed_case": 1,
    }
    diagnostics_path.write_text(
        json.dumps(diagnostics, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "invalid_artifact s11_catch_sre_wrapper_diagnostics.json "
        "missing_case_count=placement_infeasible"
    ) in output
    assert (
        "invalid_artifact s11_catch_sre_wrapper_diagnostics.json "
        "unexpected_case_count=unreviewed_case"
    ) in output
    assert (
        "invalid_artifact s11_catch_sre_wrapper_diagnostics.json "
        "invalid_case_count=feasible"
    ) in output
    assert "artifact_check failed studies=3 invalid=3" in output


@pytest.mark.parametrize(
    "field",
    [
        "feasible_quiet_fraction",
        "placement_infeasible_event_visible_fraction",
        "total_overload_event_visible_fraction",
    ],
)
def test_event_evidence_report_rejects_invalid_s11_diagnostics_fraction(
    tmp_path, capsys, field
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    diagnostics_path = tmp_path / "s11_catch_sre_wrapper_diagnostics.json"
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    diagnostics[field] = False
    diagnostics_path.write_text(
        json.dumps(diagnostics, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "invalid_artifact s11_catch_sre_wrapper_diagnostics.json "
        f"invalid_diagnostics_field={field}"
    ) in output
    assert "artifact_check failed studies=3 invalid=1" in output


def test_event_evidence_report_rejects_s11_event_visible_fraction_mismatch(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["studies"][1]["event_visible_fraction"] = 0.5
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=manifest_path,
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "inconsistent_artifact s11_catch_sre_wrapper_diagnostics.json "
        "event_visible_fraction_mismatch"
    ) in output
    assert "artifact_check failed studies=3 inconsistent=1" in output


def test_event_evidence_report_rejects_schema_invalid_event_artifact(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    trace_path = tmp_path / "s10_trace_full.jsonl"
    rows = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    rows[0].pop("safe_action")
    trace_path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )
    sample_path = tmp_path / "s10_trace_sample.jsonl"
    sample_rows = [
        json.loads(line)
        for line in sample_path.read_text(encoding="utf-8").splitlines()
    ]
    sample_rows[0].pop("safe_action")
    sample_path.write_text(
        "\n".join(json.dumps(row) for row in sample_rows) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert "schema_invalid_event s10_trace_full.jsonl line=1" in output
    assert "artifact_check failed studies=3 schema_invalid=1" in output


def test_event_evidence_report_rejects_bounded_residual_without_sufficiency_fields(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    trace_path = tmp_path / "s12_replay_trace.jsonl"
    rows = [
        json.loads(line)
        for line in trace_path.read_text(encoding="utf-8").splitlines()
    ]
    for row in rows:
        for event in row.get("runtime", {}).get("events", []):
            if event["kind"] == "bounded_ls_residual":
                event.pop("rps_residual_fraction")
                trace_path.write_text(
                    "\n".join(json.dumps(row) for row in rows) + "\n",
                    encoding="utf-8",
                )

                ok = evidence_report.main(
                    manifest_path=result["manifest_path"],
                    repo_root=tmp_path,
                )
                output = capsys.readouterr().out

                assert ok is False
                assert "schema_invalid_event s12_replay_trace.jsonl line=" in output
                assert "artifact_check failed studies=3 schema_invalid=1" in output
                return

    raise AssertionError("fixture did not emit bounded_ls_residual")


def test_event_evidence_report_rejects_s12_expected_event_count_mismatch(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    diagnostics_path = tmp_path / "s12_replay_diagnostics.json"
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    diagnostics["expected_event_count"] -= 1
    diagnostics_path.write_text(
        json.dumps(diagnostics, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "inconsistent_artifact s12_replay_diagnostics.json "
        "expected_event_count_mismatch"
    ) in output
    assert "artifact_check failed studies=3 inconsistent=1" in output


def test_event_evidence_report_rejects_invalid_s12_diagnostics_field_type(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    diagnostics_path = tmp_path / "s12_replay_diagnostics.json"
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    diagnostics["operator_action_coverage"] = "1.0"
    diagnostics_path.write_text(
        json.dumps(diagnostics, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "invalid_artifact s12_replay_diagnostics.json "
        "invalid_diagnostics_field=operator_action_coverage"
    ) in output
    assert "artifact_check failed studies=3 invalid=1" in output


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("evidence_label", 12),
        ("fixture_path", 12),
    ],
)
def test_event_evidence_report_rejects_invalid_s12_diagnostics_descriptor_type(
    tmp_path, capsys, field, value
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    diagnostics_path = tmp_path / "s12_replay_diagnostics.json"
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    diagnostics[field] = value
    diagnostics_path.write_text(
        json.dumps(diagnostics, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "invalid_artifact s12_replay_diagnostics.json "
        f"invalid_diagnostics_field={field}"
    ) in output
    assert "artifact_check failed studies=3 invalid=1" in output


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("evidence_label", "synthetic_replay_drift"),
        ("fixture_path", "analysis/fixtures/other_replay.jsonl"),
    ],
)
def test_event_evidence_report_rejects_s12_diagnostics_descriptor_mismatch(
    tmp_path, capsys, field, value
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    diagnostics_path = tmp_path / "s12_replay_diagnostics.json"
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    diagnostics[field] = value
    diagnostics_path.write_text(
        json.dumps(diagnostics, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "inconsistent_artifact s12_replay_diagnostics.json "
        f"{field}_mismatch"
    ) in output
    assert "artifact_check failed studies=3 inconsistent=1" in output


@pytest.mark.parametrize(
    "field",
    [
        "background_event_fraction",
        "expected_event_visible_fraction",
        "multi_signal_window_recovered_fraction",
        "recovered_window_fraction",
        "stability_event_visible_fraction",
    ],
)
def test_event_evidence_report_rejects_out_of_range_s12_fraction_diagnostic(
    tmp_path, capsys, field
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    diagnostics_path = tmp_path / "s12_replay_diagnostics.json"
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    diagnostics[field] = 1.5
    diagnostics_path.write_text(
        json.dumps(diagnostics, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "invalid_artifact s12_replay_diagnostics.json "
        f"invalid_diagnostics_field={field}"
    ) in output
    assert "artifact_check failed studies=3 invalid=1" in output


@pytest.mark.parametrize(
    "field",
    [
        "max_incident_window_ticks",
        "max_multi_signal_recovery_ticks",
        "max_recovery_ticks",
        "multi_signal_window_count",
        "recovery_window_count",
    ],
)
def test_event_evidence_report_rejects_negative_s12_count_diagnostic(
    tmp_path, capsys, field
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    diagnostics_path = tmp_path / "s12_replay_diagnostics.json"
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    diagnostics[field] = -1
    diagnostics_path.write_text(
        json.dumps(diagnostics, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "invalid_artifact s12_replay_diagnostics.json "
        f"invalid_diagnostics_field={field}"
    ) in output
    assert "artifact_check failed studies=3 invalid=1" in output


def test_event_evidence_report_rejects_unknown_s12_diagnostics_observed_kind(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    diagnostics_path = tmp_path / "s12_replay_diagnostics.json"
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    diagnostics["observed_expected_kinds"].append("unknown_runtime_event")
    diagnostics_path.write_text(
        json.dumps(diagnostics, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "invalid_artifact s12_replay_diagnostics.json "
        "unknown_observed_expected_kind=unknown_runtime_event"
    ) in output
    assert "artifact_check failed studies=3 invalid=1" in output


def test_event_evidence_report_rejects_unknown_s12_operator_action_kind(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    diagnostics_path = tmp_path / "s12_replay_diagnostics.json"
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    diagnostics["operator_actions_by_kind"]["unknown_runtime_event"] = [
        "inspect unregistered event"
    ]
    diagnostics_path.write_text(
        json.dumps(diagnostics, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "invalid_artifact s12_replay_diagnostics.json "
        "unknown_operator_action_kind=unknown_runtime_event"
    ) in output
    assert "artifact_check failed studies=3 invalid=1" in output


def test_event_evidence_report_rejects_blank_s12_operator_action_diagnostic(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    diagnostics_path = tmp_path / "s12_replay_diagnostics.json"
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    diagnostics["operator_actions_by_kind"]["missing_sensor"] = ["   "]
    diagnostics_path.write_text(
        json.dumps(diagnostics, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "invalid_artifact s12_replay_diagnostics.json "
        "invalid_operator_actions=missing_sensor"
    ) in output
    assert "artifact_check failed studies=3 invalid=1" in output


def test_event_evidence_report_rejects_s12_operator_actions_by_kind_mismatch(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    diagnostics_path = tmp_path / "s12_replay_diagnostics.json"
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    diagnostics["operator_actions_by_kind"]["missing_sensor"] = [
        "check a different telemetry source"
    ]
    diagnostics_path.write_text(
        json.dumps(diagnostics, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "inconsistent_artifact s12_replay_diagnostics.json "
        "operator_actions_by_kind_mismatch"
    ) in output
    assert "artifact_check failed studies=3 inconsistent=1" in output


def test_event_evidence_report_rejects_blank_s12_window_action_diagnostic(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    diagnostics_path = tmp_path / "s12_replay_diagnostics.json"
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    diagnostics["operator_actions_by_window"][
        "compound_telemetry_policy_capacity"
    ] = ["   "]
    diagnostics_path.write_text(
        json.dumps(diagnostics, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "invalid_artifact s12_replay_diagnostics.json "
        "invalid_window_operator_actions=compound_telemetry_policy_capacity"
    ) in output
    assert "artifact_check failed studies=3 invalid=1" in output


def test_event_evidence_report_rejects_s12_operator_actions_by_window_mismatch(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    diagnostics_path = tmp_path / "s12_replay_diagnostics.json"
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    diagnostics["operator_actions_by_window"][
        "compound_telemetry_policy_capacity"
    ] = ["coordinate a different incident response"]
    diagnostics_path.write_text(
        json.dumps(diagnostics, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "inconsistent_artifact s12_replay_diagnostics.json "
        "operator_actions_by_window_mismatch"
    ) in output
    assert "artifact_check failed studies=3 inconsistent=1" in output


def test_event_evidence_report_rejects_s12_observed_expected_kinds_mismatch(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    diagnostics_path = tmp_path / "s12_replay_diagnostics.json"
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    diagnostics["observed_expected_kinds"] = diagnostics["observed_expected_kinds"][:-1]
    diagnostics_path.write_text(
        json.dumps(diagnostics, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "inconsistent_artifact s12_replay_diagnostics.json "
        "observed_expected_kinds_mismatch"
    ) in output
    assert "artifact_check failed studies=3 inconsistent=1" in output


def test_event_evidence_report_rejects_s12_replay_tick_count_mismatch(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    diagnostics_path = tmp_path / "s12_replay_diagnostics.json"
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    diagnostics["replay_tick_count"] -= 1
    diagnostics_path.write_text(
        json.dumps(diagnostics, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "inconsistent_artifact s12_replay_diagnostics.json "
        "replay_tick_count_mismatch"
    ) in output
    assert "artifact_check failed studies=3 inconsistent=1" in output


def test_event_evidence_report_rejects_s12_recovery_window_count_mismatch(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    diagnostics_path = tmp_path / "s12_replay_diagnostics.json"
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    diagnostics["recovery_window_count"] -= 1
    diagnostics_path.write_text(
        json.dumps(diagnostics, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "inconsistent_artifact s12_replay_diagnostics.json "
        "recovery_window_count_mismatch"
    ) in output
    assert "artifact_check failed studies=3 inconsistent=1" in output


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("recovered_window_fraction", 0.5),
        ("max_recovery_ticks", 2.0),
    ],
)
def test_event_evidence_report_rejects_s12_recovery_diagnostic_mismatch(
    tmp_path, capsys, field, value
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    diagnostics_path = tmp_path / "s12_replay_diagnostics.json"
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    diagnostics[field] = value
    diagnostics_path.write_text(
        json.dumps(diagnostics, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "inconsistent_artifact s12_replay_diagnostics.json "
        f"{field}_mismatch"
    ) in output
    assert "artifact_check failed studies=3 inconsistent=1" in output


def test_event_evidence_report_rejects_s12_operator_action_coverage_mismatch(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    diagnostics_path = tmp_path / "s12_replay_diagnostics.json"
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    diagnostics["operator_action_coverage"] = 0.5
    diagnostics_path.write_text(
        json.dumps(diagnostics, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "inconsistent_artifact s12_replay_diagnostics.json "
        "operator_action_coverage_mismatch"
    ) in output
    assert "artifact_check failed studies=3 inconsistent=1" in output


def test_event_evidence_report_does_not_count_blank_s12_operator_action(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    fixture_path = REPO_ROOT / "analysis" / "fixtures" / "sre_replay.jsonl"
    rows = [
        json.loads(line)
        for line in fixture_path.read_text(encoding="utf-8").splitlines()
    ]
    rows[4]["operator_action"] = "   "
    fixture_copy = tmp_path / "sre_replay_blank_operator_action.jsonl"
    fixture_copy.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )
    manifest_path = result["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["studies"][2]["artifact_paths"]["fixture_jsonl"] = fixture_copy.name
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    diagnostics_path = tmp_path / "s12_replay_diagnostics.json"
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    diagnostics["fixture_path"] = fixture_copy.name
    diagnostics_path.write_text(
        json.dumps(diagnostics, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=manifest_path,
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "inconsistent_artifact s12_replay_diagnostics.json "
        "operator_action_coverage_mismatch"
    ) in output
    assert (
        "inconsistent_artifact s12_replay_diagnostics.json "
        "operator_actions_by_kind_mismatch"
    ) in output
    assert "artifact_check failed studies=3 inconsistent=2" in output


def test_event_evidence_report_rejects_s12_multi_signal_coverage_mismatch(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    diagnostics_path = tmp_path / "s12_replay_diagnostics.json"
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    diagnostics["multi_signal_window_coverage"] = 0.5
    diagnostics_path.write_text(
        json.dumps(diagnostics, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "inconsistent_artifact s12_replay_diagnostics.json "
        "multi_signal_window_coverage_mismatch"
    ) in output
    assert "artifact_check failed studies=3 inconsistent=1" in output


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("multi_signal_window_count", 2),
        ("max_incident_window_ticks", 4),
        ("multi_signal_window_recovered_fraction", 0.5),
        ("max_multi_signal_recovery_ticks", 2.0),
    ],
)
def test_event_evidence_report_rejects_s12_multi_signal_diagnostic_mismatch(
    tmp_path, capsys, field, value
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    diagnostics_path = tmp_path / "s12_replay_diagnostics.json"
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    diagnostics[field] = value
    diagnostics_path.write_text(
        json.dumps(diagnostics, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "inconsistent_artifact s12_replay_diagnostics.json "
        f"{field}_mismatch"
    ) in output
    assert "artifact_check failed studies=3 inconsistent=1" in output


@pytest.mark.parametrize(
    "field",
    [
        "expected_event_visible_fraction",
        "background_event_fraction",
        "stability_event_visible_fraction",
    ],
)
def test_event_evidence_report_rejects_s12_visibility_diagnostic_mismatch(
    tmp_path, capsys, field
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    diagnostics_path = tmp_path / "s12_replay_diagnostics.json"
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    diagnostics[field] = 0.5
    diagnostics_path.write_text(
        json.dumps(diagnostics, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok = evidence_report.main(
        manifest_path=result["manifest_path"],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "inconsistent_artifact s12_replay_diagnostics.json "
        f"{field}_mismatch"
    ) in output
    assert "artifact_check failed studies=3 inconsistent=1" in output


def test_event_evidence_report_rejects_stack_contract_production_claim(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    contract_path = tmp_path / "sre_stack_data_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["production_claim"] = True
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
    assert (
        "inconsistent_artifact sre_stack_data_contract.json "
        "production_claim_must_be_false"
    ) in output
    assert "artifact_check failed studies=3 inconsistent=1" in output


def test_event_evidence_report_rejects_unknown_stack_contract_event_kind(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    contract_path = tmp_path / "sre_stack_data_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["stages"][0]["event_kinds"].append("not_a_runtime_event")
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
    assert (
        "inconsistent_artifact sre_stack_data_contract.json "
        "unknown_stage_event_kind=not_a_runtime_event"
    ) in output
    assert "artifact_check failed studies=3 inconsistent=1" in output


def test_event_evidence_report_rejects_invalid_stack_contract_route_value(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    contract_path = tmp_path / "sre_stack_data_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["event_stage_routes"]["SignalFusion"] = ["observe"]
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
    assert (
        "inconsistent_artifact sre_stack_data_contract.json "
        "event_stage_route_invalid=SignalFusion"
    ) in output
    assert "artifact_check failed studies=3 inconsistent=1" in output


def test_event_evidence_report_rejects_unexpected_stack_contract_route_key(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    contract_path = tmp_path / "sre_stack_data_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["event_stage_routes"]["ShadowProducer"] = "observe"
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
    assert (
        "inconsistent_artifact sre_stack_data_contract.json "
        "unexpected_event_stage_route=ShadowProducer"
    ) in output
    assert "artifact_check failed studies=3 inconsistent=1" in output


def test_event_evidence_report_rejects_missing_stack_contract_route_key(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    contract_path = tmp_path / "sre_stack_data_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    del contract["event_stage_routes"]["CanaryScheduler"]
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
    assert (
        "inconsistent_artifact sre_stack_data_contract.json "
        "missing_event_stage_route=CanaryScheduler"
    ) in output
    assert "artifact_check failed studies=3 inconsistent=1" in output


def test_event_evidence_report_rejects_non_object_stack_contract_stage_entry(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    contract_path = tmp_path / "sre_stack_data_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["stages"][0] = "observe"
    contract_path.write_text(
        json.dumps(contract, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    try:
        ok = evidence_report.main(
            manifest_path=result["manifest_path"],
            repo_root=tmp_path,
        )
    except AttributeError as exc:
        pytest.fail(f"report crashed instead of rejecting stage entry shape: {exc}")
    output = capsys.readouterr().out

    assert ok is False
    assert (
        "inconsistent_artifact sre_stack_data_contract.json "
        "stage_entry_invalid=0"
    ) in output
    assert "artifact_check failed studies=3 inconsistent=1" in output


def test_event_evidence_report_rejects_invalid_stack_contract_stage_interface(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    contract_path = tmp_path / "sre_stack_data_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["stages"][0]["inputs"] = "dt"
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
    assert (
        "inconsistent_artifact sre_stack_data_contract.json "
        "stage_interface_invalid=observe.inputs"
    ) in output
    assert "artifact_check failed studies=3 inconsistent=1" in output


def test_event_evidence_report_rejects_trace_fallback_mode_not_allowed_by_stage(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    _replace_first_s10_trace_event(result, tmp_path, {
        'adapter_family': 'observe',
        'cause_type': 'adapter_input',
        'detail': 'observe adapter used an undeclared fallback mode',
        'exception_type': 'AdapterInputError',
        'fallback_action': 'zero_guardrail_action',
        'fallback_mode': 'zero_action',
        'fault_family': 'adapter_input',
        'kind': 'adapter_exception',
        'recoverable': True,
        'safe_action': 'use validated fallback',
        'stage': 'SignalFusion',
    })

    ok = evidence_report.main(
        manifest_path=result['manifest_path'],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        'contract_unrouted_fallback_mode s10_trace_full.jsonl '
        'stage=SignalFusion contract_stage=observe '
        'fallback_mode=zero_action'
    ) in output
    assert 'artifact_check failed studies=3 contract_events=1' in output


def test_event_evidence_report_rejects_trace_adapter_family_not_matching_stage_route(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    _replace_first_s10_trace_event(result, tmp_path, {
        'adapter_family': 'guard',
        'cause_type': 'adapter_input',
        'detail': 'observe adapter reported the wrong adapter family',
        'exception_type': 'AdapterInputError',
        'fallback_action': 'use_forecast_rps_for_observed_load',
        'fallback_mode': 'substitute_observed_rps',
        'fault_family': 'adapter_input',
        'kind': 'adapter_exception',
        'recoverable': True,
        'safe_action': 'use validated fallback',
        'stage': 'SignalFusion',
    })

    ok = evidence_report.main(
        manifest_path=result['manifest_path'],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        'contract_adapter_family_mismatch s10_trace_full.jsonl '
        'stage=SignalFusion contract_stage=observe adapter_family=guard'
    ) in output
    assert 'artifact_check failed studies=3 contract_events=1' in output


def test_event_evidence_report_rejects_trace_fault_family_not_matching_cause_type(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    _replace_first_s10_trace_event(result, tmp_path, {
        'adapter_family': 'observe',
        'cause_type': 'adapter_input',
        'detail': 'observe adapter reported the wrong fault family',
        'exception_type': 'AdapterInputError',
        'fallback_action': 'use_forecast_rps_for_observed_load',
        'fallback_mode': 'substitute_observed_rps',
        'fault_family': 'control_domain',
        'kind': 'adapter_exception',
        'recoverable': True,
        'safe_action': 'use validated fallback',
        'stage': 'SignalFusion',
    })

    ok = evidence_report.main(
        manifest_path=result['manifest_path'],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        'contract_fault_family_mismatch s10_trace_full.jsonl '
        'stage=SignalFusion cause_type=adapter_input '
        'fault_family=control_domain'
    ) in output
    assert 'artifact_check failed studies=3 contract_events=1' in output


def test_event_evidence_report_rejects_trace_exception_type_not_matching_cause_type(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    _replace_first_s10_trace_event(result, tmp_path, {
        'adapter_family': 'observe',
        'cause_type': 'control_domain',
        'detail': 'adapter input error reported as control-domain cause',
        'exception_type': 'AdapterInputError',
        'fallback_action': 'use_forecast_rps_for_observed_load',
        'fallback_mode': 'substitute_observed_rps',
        'fault_family': 'control_domain',
        'kind': 'adapter_exception',
        'recoverable': True,
        'safe_action': 'use validated fallback',
        'stage': 'SignalFusion',
    })

    ok = evidence_report.main(
        manifest_path=result['manifest_path'],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        'contract_exception_cause_mismatch s10_trace_full.jsonl '
        'stage=SignalFusion exception_type=AdapterInputError '
        'cause_type=control_domain'
    ) in output
    assert 'artifact_check failed studies=3 contract_events=1' in output


def test_event_evidence_report_rejects_trace_recoverable_error_marked_adapter_input(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    _replace_first_s10_trace_event(result, tmp_path, {
        'adapter_family': 'observe',
        'cause_type': 'adapter_input',
        'detail': 'recoverable control-domain error reported as adapter input',
        'exception_type': 'RecoverableControlError',
        'fallback_action': 'use_forecast_rps_for_observed_load',
        'fallback_mode': 'substitute_observed_rps',
        'fault_family': 'adapter_input',
        'kind': 'adapter_exception',
        'recoverable': True,
        'safe_action': 'use validated fallback',
        'stage': 'SignalFusion',
    })

    ok = evidence_report.main(
        manifest_path=result['manifest_path'],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        'contract_exception_cause_mismatch s10_trace_full.jsonl '
        'stage=SignalFusion exception_type=RecoverableControlError '
        'cause_type=adapter_input'
    ) in output
    assert 'artifact_check failed studies=3 contract_events=1' in output


def test_event_evidence_report_rejects_adapter_exception_marked_unrecoverable(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    _replace_first_s10_trace_event(result, tmp_path, {
        'adapter_family': 'observe',
        'cause_type': 'adapter_input',
        'detail': 'adapter exception was marked unrecoverable',
        'exception_type': 'AdapterInputError',
        'fallback_action': 'use_forecast_rps_for_observed_load',
        'fallback_mode': 'substitute_observed_rps',
        'fault_family': 'adapter_input',
        'kind': 'adapter_exception',
        'recoverable': False,
        'safe_action': 'use validated fallback',
        'stage': 'SignalFusion',
    })

    ok = evidence_report.main(
        manifest_path=result['manifest_path'],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        'contract_unrecoverable_adapter_exception s10_trace_full.jsonl '
        'stage=SignalFusion recoverable=False'
    ) in output
    assert 'artifact_check failed studies=3 contract_events=1' in output


def test_event_evidence_report_rejects_invalid_stack_contract_split_boundaries(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    contract_path = tmp_path / "sre_stack_data_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["split_ready_boundaries"] = ["observe_to_plan", 123]
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
    assert (
        "inconsistent_artifact sre_stack_data_contract.json "
        "split_ready_boundaries_invalid"
    ) in output
    assert "artifact_check failed studies=3 inconsistent=1" in output


def test_event_evidence_report_rejects_unexpected_stack_contract_split_boundary_set(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    contract_path = tmp_path / "sre_stack_data_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["split_ready_boundaries"] = [
        "observe_to_plan",
        "plan_to_guard",
        "unexpected_boundary",
    ]
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
    assert (
        "inconsistent_artifact sre_stack_data_contract.json "
        "missing_split_ready_boundary=allocate_to_execute"
    ) in output
    assert (
        "inconsistent_artifact sre_stack_data_contract.json "
        "unexpected_split_ready_boundary=unexpected_boundary"
    ) in output
    assert "artifact_check failed studies=3 inconsistent=3" in output


def test_event_evidence_report_rejects_trace_event_not_allowed_by_stack_contract(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    contract_path = tmp_path / "sre_stack_data_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    for stage in contract["stages"]:
        if stage["stage"] == "guard":
            stage["event_kinds"].remove("unsafe_proposal_projected")
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
    assert (
        "contract_unrouted_event s10_trace_full.jsonl "
        "stage=SLOGuardrail kind=unsafe_proposal_projected contract_stage=guard"
    ) in output
    assert "artifact_check failed studies=3 contract_events=1" in output
