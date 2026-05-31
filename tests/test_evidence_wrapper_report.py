from __future__ import annotations

import json

import pytest

from analysis import evidence_manifest, evidence_report


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
