from __future__ import annotations

import json
from pathlib import Path

import pytest

from analysis import evidence_manifest, evidence_report

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_event_evidence_report_rejects_s12_expected_event_count_mismatch(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    diagnostics_path = tmp_path / 's12_replay_diagnostics.json'
    diagnostics = json.loads(diagnostics_path.read_text(encoding='utf-8'))
    diagnostics['expected_event_count'] -= 1
    diagnostics_path.write_text(
        json.dumps(diagnostics, indent=2, sort_keys=True) + '\n',
        encoding='utf-8',
    )

    ok = evidence_report.main(
        manifest_path=result['manifest_path'],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        'inconsistent_artifact s12_replay_diagnostics.json '
        'expected_event_count_mismatch'
    ) in output
    assert 'artifact_check failed studies=3 inconsistent=1' in output


def test_event_evidence_report_rejects_invalid_s12_diagnostics_field_type(
    tmp_path, capsys
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    diagnostics_path = tmp_path / 's12_replay_diagnostics.json'
    diagnostics = json.loads(diagnostics_path.read_text(encoding='utf-8'))
    diagnostics['operator_action_coverage'] = '1.0'
    diagnostics_path.write_text(
        json.dumps(diagnostics, indent=2, sort_keys=True) + '\n',
        encoding='utf-8',
    )

    ok = evidence_report.main(
        manifest_path=result['manifest_path'],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        'invalid_artifact s12_replay_diagnostics.json '
        'invalid_diagnostics_field=operator_action_coverage'
    ) in output
    assert 'artifact_check failed studies=3 invalid=1' in output


@pytest.mark.parametrize(
    ('field', 'value'),
    [
        ('evidence_label', 12),
        ('fixture_path', 12),
    ],
)
def test_event_evidence_report_rejects_invalid_s12_diagnostics_descriptor_type(
    tmp_path, capsys, field, value
) -> None:
    result = evidence_manifest.main(artifacts_dir=tmp_path)
    diagnostics_path = tmp_path / 's12_replay_diagnostics.json'
    diagnostics = json.loads(diagnostics_path.read_text(encoding='utf-8'))
    diagnostics[field] = value
    diagnostics_path.write_text(
        json.dumps(diagnostics, indent=2, sort_keys=True) + '\n',
        encoding='utf-8',
    )

    ok = evidence_report.main(
        manifest_path=result['manifest_path'],
        repo_root=tmp_path,
    )
    output = capsys.readouterr().out

    assert ok is False
    assert (
        'invalid_artifact s12_replay_diagnostics.json '
        f'invalid_diagnostics_field={field}'
    ) in output
    assert 'artifact_check failed studies=3 invalid=1' in output

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
