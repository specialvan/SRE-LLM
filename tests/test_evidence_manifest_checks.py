from __future__ import annotations

import copy
import json

from analysis import evidence_manifest, evidence_manifest_checks


def _generated_manifest(tmp_path) -> dict:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    return json.loads(result["manifest_path"].read_text(encoding="utf-8"))


def test_manifest_shape_errors_accepts_generated_manifest(tmp_path):
    manifest = _generated_manifest(tmp_path)

    assert evidence_manifest_checks.manifest_shape_errors(manifest) == []


def test_is_sha256_accepts_uppercase_hex():
    assert evidence_manifest_checks.is_sha256("A" * 64) is True
    assert evidence_manifest_checks.is_sha256("F" * 64) is True


def test_manifest_shape_errors_reports_missing_and_duplicate_studies(tmp_path):
    manifest = _generated_manifest(tmp_path)
    manifest["studies"] = [
        copy.deepcopy(manifest["studies"][0]),
        copy.deepcopy(manifest["studies"][0]),
        copy.deepcopy(manifest["studies"][1]),
    ]

    errors = evidence_manifest_checks.manifest_shape_errors(manifest)

    assert "invalid_manifest duplicate_study=s10_failure_trace" in errors
    assert "invalid_manifest missing_study=s12_sre_replay" in errors


def test_manifest_shape_errors_reports_contract_metadata_shape(tmp_path):
    manifest = _generated_manifest(tmp_path)
    manifest["contracts"][0]["artifact_metadata"]["contract_json"] = {
        "sha256": "not-a-sha",
        "size_bytes": 1,
    }

    errors = evidence_manifest_checks.manifest_shape_errors(manifest)

    assert errors == [
        "invalid_manifest contract=sre_stack_data_contract "
        "invalid_artifact_metadata=contract_json"
    ]
