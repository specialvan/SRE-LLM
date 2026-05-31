from __future__ import annotations

import json
from pathlib import Path

import pytest

from analysis import evidence_manifest, evidence_report

REPO_ROOT = Path(__file__).resolve().parents[1]


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
