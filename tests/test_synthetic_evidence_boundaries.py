from __future__ import annotations

import hashlib
import json

import pytest

from analysis import (
    s05_ekf,
    s08_catch_allocation,
    s11_catch_sre_wrapper,
    s12_sre_replay,
)
from scripts.evidence_boundary_lint import (
    PUBLIC_EVIDENCE_BOUNDARY_DOCS,
    find_overclaim_phrases,
)
from scripts.review_authority_lint import (
    configured_authority_paths,
    find_authority_order_errors,
)


REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
EXPECTED_OPERATOR_ACTION_KINDS = {
    "bounded_ls_residual",
    "missing_sensor",
    "replica_bound_active",
    "stability_violation",
    "unsafe_proposal_projected",
}


def _artifact_digest(relative_path: str) -> str | None:
    path = REPO_ROOT / relative_path
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assert_operator_actions_cover_expected_kinds(
    actions_by_kind: dict[str, list[str]]
) -> None:
    assert set(actions_by_kind) == EXPECTED_OPERATOR_ACTION_KINDS
    for actions in actions_by_kind.values():
        assert actions
        assert all(isinstance(action, str) and action.strip() for action in actions)


@pytest.mark.parametrize("seed", [0])
def test_ekf_report_improves_velocity_and_position_with_fiducial(seed: int) -> None:
    result = s05_ekf.main(seed=seed)

    before = result["before"]
    after = result["after"]

    assert after["vel_rmse"] < before["vel_rmse"]
    assert after["pos_p95"] < before["pos_p95"]


@pytest.mark.parametrize("seed", [0])
def test_ekf_report_uses_fiducial_as_second_source(seed: int) -> None:
    result = s05_ekf.main(seed=seed)
    diagnostics = result["diagnostics"]

    assert diagnostics["radar_updates"] > 0
    assert diagnostics["fiducial_updates"] > 0
    assert diagnostics["multi_source_tick_fraction"] > 0.0


@pytest.mark.parametrize("seed", [0])
def test_ekf_report_shows_near_field_fiducial_improvement(seed: int) -> None:
    result = s05_ekf.main(seed=seed)
    after = result["after"]
    radar_only = result["radar_only"]

    assert after["near_field_pos_rmse"] < radar_only["near_field_pos_rmse"]
    assert after["near_field_pos_p95"] < radar_only["near_field_pos_p95"]


@pytest.mark.parametrize("seed", [0])
def test_catch_allocation_report_keeps_residual_tradeoff_visible(seed: int) -> None:
    result = s08_catch_allocation.main(seed=seed)

    before = result["before"]
    after = result["after"]

    assert after["saturation_violation_pct"] == 0
    assert after["mean_residual"] >= before["mean_residual"]


@pytest.mark.parametrize("seed", [0])
def test_catch_sre_wrapper_reports_residual_instead_of_hiding_capacity(
    seed: int, tmp_path
) -> None:
    before_digest = _artifact_digest("analysis/artifacts/s11_catch_sre_wrapper.png")
    result = s11_catch_sre_wrapper.main(seed=seed, artifacts_dir=tmp_path)

    before = result["before"]
    after = result["after"]

    assert before["reported_residual_mean"] == 0.0
    assert before["capacity_violation_pct"] > 0.0
    assert after["capacity_violation_pct"] == 0.0
    assert after["reported_residual_mean"] > 0.0
    assert after["event_visible_fraction"] == 1.0
    assert (tmp_path / "s11_catch_sre_wrapper.png").exists()
    assert _artifact_digest("analysis/artifacts/s11_catch_sre_wrapper.png") == before_digest


@pytest.mark.parametrize("seed", [0])
def test_catch_sre_wrapper_covers_feasible_overload_and_placement_cases(
    seed: int, tmp_path
) -> None:
    before_digest = _artifact_digest("analysis/artifacts/s11_catch_sre_wrapper.png")
    result = s11_catch_sre_wrapper.main(n_cases=9, seed=seed, artifacts_dir=tmp_path)
    diagnostics = result["diagnostics"]

    case_counts = diagnostics["case_counts"]
    assert set(case_counts) == {
        "feasible",
        "total_overload",
        "placement_infeasible",
    }
    assert case_counts["feasible"] == case_counts["total_overload"]
    assert case_counts["feasible"] == case_counts["placement_infeasible"]
    assert case_counts["feasible"] >= 1
    assert diagnostics["feasible_quiet_fraction"] == 1.0
    assert diagnostics["total_overload_event_visible_fraction"] == 1.0
    assert diagnostics["placement_infeasible_event_visible_fraction"] == 1.0
    assert (tmp_path / "s11_catch_sre_wrapper.png").exists()
    assert _artifact_digest("analysis/artifacts/s11_catch_sre_wrapper.png") == before_digest


def test_sre_replay_fixture_is_labeled_and_covers_expected_event_kinds() -> None:
    result = s12_sre_replay.main()
    diagnostics = result["diagnostics"]

    assert diagnostics["evidence_label"] == "synthetic_replay_fixture"
    assert diagnostics["replay_tick_count"] == 19
    assert diagnostics["expected_event_visible_fraction"] == 1.0
    assert diagnostics["stability_event_visible_fraction"] == 1.0
    assert diagnostics["background_event_fraction"] == 0.0
    assert diagnostics["recovery_window_count"] == 5
    assert diagnostics["recovered_window_fraction"] == 1.0
    assert diagnostics["max_recovery_ticks"] == 1
    assert diagnostics["operator_action_coverage"] == 1.0
    _assert_operator_actions_cover_expected_kinds(
        diagnostics["operator_actions_by_kind"]
    )
    assert diagnostics["observed_expected_kinds"] == [
        "bounded_ls_residual",
        "missing_sensor",
        "replica_bound_active",
        "stability_violation",
        "unsafe_proposal_projected",
    ]


def test_sre_replay_operator_action_coverage_ignores_blank_annotations() -> None:
    diagnostics = s12_sre_replay._operator_action_diagnostics(
        [
            {
                "expected_kind": "missing_sensor",
                "operator_action": "check telemetry source",
            },
            {
                "expected_kind": "unsafe_proposal_projected",
                "operator_action": "   ",
            },
        ]
    )

    assert diagnostics["operator_action_coverage"] == 0.5
    assert diagnostics["operator_actions_by_kind"] == {
        "missing_sensor": ["check telemetry source"]
    }


def test_sre_replay_operator_actions_are_checked_by_coverage_not_literal_text() -> None:
    actions_by_kind = {
        "bounded_ls_residual": ["capacity action wording can evolve"],
        "missing_sensor": ["telemetry action wording can evolve"],
        "replica_bound_active": ["quota action wording can evolve"],
        "stability_violation": ["stability action wording can evolve"],
        "unsafe_proposal_projected": ["policy action wording can evolve"],
    }

    _assert_operator_actions_cover_expected_kinds(actions_by_kind)


def test_sre_replay_fixture_covers_multi_signal_incident_windows() -> None:
    result = s12_sre_replay.main()
    diagnostics = result["diagnostics"]

    assert diagnostics["multi_signal_window_count"] >= 1
    assert diagnostics["max_incident_window_ticks"] >= 3
    assert diagnostics["multi_signal_window_coverage"] == 1.0
    assert diagnostics["multi_signal_window_recovered_fraction"] == 1.0
    assert diagnostics["max_multi_signal_recovery_ticks"] <= 1
    assert diagnostics["operator_actions_by_window"] == {
        "compound_telemetry_policy_capacity": [
            "coordinate telemetry repair, policy rollback, and capacity restoration"
        ]
    }


def test_sre_replay_window_actions_ignore_blank_annotations() -> None:
    rows = [
        {
            "incident_id": "compound",
            "expected_kinds": ["missing_sensor"],
            "window_operator_action": "coordinate repair",
        },
        {
            "incident_id": "compound",
            "expected_kinds": ["unsafe_proposal_projected"],
            "window_operator_action": "   ",
        },
        {"expected_kind": None},
    ]
    trace = [
        {"runtime": {"events": [{"kind": "missing_sensor"}]}},
        {"runtime": {"events": [{"kind": "unsafe_proposal_projected"}]}},
        {"runtime": {"events": []}},
    ]

    diagnostics = s12_sre_replay._multi_signal_window_diagnostics(rows, trace)

    assert diagnostics["operator_actions_by_window"] == {
        "compound": ["coordinate repair"]
    }


def test_sre_replay_unrecovered_window_uses_strict_json_null() -> None:
    rows = [{"expected_kind": "missing_sensor"}]
    trace = [{"runtime": {"events": [{"kind": "missing_sensor"}]}}]

    diagnostics = s12_sre_replay._recovery_diagnostics(rows, trace)

    assert diagnostics["recovered_window_fraction"] == 0.0
    assert diagnostics["max_recovery_ticks"] is None
    json.dumps(diagnostics, allow_nan=False)


def test_sre_replay_unrecovered_multi_signal_window_uses_strict_json_null() -> None:
    rows = [
        {
            "incident_id": "compound",
            "expected_kinds": ["missing_sensor", "replica_bound_active"],
        }
    ]
    trace = [
        {
            "runtime": {
                "events": [
                    {"kind": "missing_sensor"},
                    {"kind": "replica_bound_active"},
                ]
            }
        }
    ]

    diagnostics = s12_sre_replay._multi_signal_window_diagnostics(rows, trace)

    assert diagnostics["multi_signal_window_recovered_fraction"] == 0.0
    assert diagnostics["max_multi_signal_recovery_ticks"] is None
    json.dumps(diagnostics, allow_nan=False)


def test_evidence_boundary_lint_flags_unsafe_production_claims() -> None:
    text = (
        "The synthetic replay proves production readiness. "
        "These algorithms are the official SpaceX implementation."
    )

    findings = find_overclaim_phrases(text)

    assert {finding.phrase for finding in findings} == {
        "proves production readiness",
        "official SpaceX implementation",
    }


def test_evidence_boundary_lint_flags_unsafe_chinese_claims() -> None:
    text = "这些 synthetic replay 证明生产就绪。这是 SpaceX 内部实现。"

    findings = find_overclaim_phrases(text)

    assert {finding.phrase for finding in findings} == {
        "证明生产就绪",
        "SpaceX 内部实现",
    }


def test_evidence_boundary_lint_allows_chinese_boundary_negation() -> None:
    text = "这些结果不能写成生产证明，也不是 SpaceX 内部实现。"

    assert find_overclaim_phrases(text) == []


def test_evidence_boundary_lint_allows_immediate_suffix_negation() -> None:
    text = "This is production-ready, but not in a production-grade sense."

    assert find_overclaim_phrases(text) == []


def test_evidence_boundary_lint_allows_rejection_wording() -> None:
    text = "The lint rejects official SpaceX implementation claims."

    assert find_overclaim_phrases(text) == []


def test_evidence_boundary_lint_allows_linted_for_wording() -> None:
    text = "Docs are linted for official SpaceX implementation wording."

    assert find_overclaim_phrases(text) == []


@pytest.mark.parametrize(
    "relative_path",
    PUBLIC_EVIDENCE_BOUNDARY_DOCS,
)
def test_live_review_docs_do_not_make_unqualified_production_claims(
    relative_path: str,
) -> None:
    text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")

    assert find_overclaim_phrases(text) == []


def test_evidence_boundary_lint_covers_public_and_review_entrypoints() -> None:
    expected_paths = {
        "README.md",
        "PR-REQUIREMENTS.md",
        "wiki/README.md",
        "docs/V2_Knowledge/knowledge-base.html",
        "docs/codex-review/CLAUDE_REVIEW_REQUEST.md",
        "docs/opus-review/README.md",
        "docs/opus-review/HANDOFF.md",
        "docs/opus-review/OPUS_REVIEW_PACKET.md",
    }

    assert expected_paths <= set(PUBLIC_EVIDENCE_BOUNDARY_DOCS)


def test_opus_handoff_reads_current_ledgers_before_historical_packets() -> None:
    assert find_authority_order_errors(REPO_ROOT / "docs/opus-review/HANDOFF.md") == []


def test_wiki_recommended_entries_put_current_ledgers_before_historical_reviews() -> None:
    assert find_authority_order_errors(REPO_ROOT / "wiki/README.md") == []


def test_opus_readme_lists_current_ledgers_before_historical_reviews() -> None:
    assert find_authority_order_errors(REPO_ROOT / "docs/opus-review/README.md") == []


def test_codex_review_readme_lists_current_ledgers_before_historical_reviews() -> None:
    assert find_authority_order_errors(REPO_ROOT / 'docs/codex-review/README.md') == []


def test_review_authority_lint_covers_current_entrypoints() -> None:
    assert set(configured_authority_paths()) == {
        'docs/codex-review/README.md',
        "docs/opus-review/README.md",
        "docs/opus-review/HANDOFF.md",
        "wiki/README.md",
    }


def test_review_authority_lint_reports_historical_packet_before_current_ledger(
    tmp_path,
) -> None:
    doc = tmp_path / "HANDOFF.md"
    doc.write_text(
        "## 当前权威锚点\n"
        "先读 `claude-review/docs/v2026-05-28/README.md`。\n"
        "再读 `docs/codex-review/OPEN_RISKS.md` 和 `wiki/review-backlog.md`。\n"
        "最后读 `docs/opus-review/OPUS_REVIEW_PACKET.md`。\n"
        "## 当前基线\n",
        encoding="utf-8",
    )

    errors = find_authority_order_errors(doc)

    assert errors == [
        "HANDOFF.md: docs/codex-review/OPEN_RISKS.md must appear before "
        "claude-review/docs/v2026-05-28/README.md in 当前权威锚点",
        "HANDOFF.md: wiki/review-backlog.md must appear before "
        "claude-review/docs/v2026-05-28/README.md in 当前权威锚点",
    ]


def test_development_audit_backlog_tracks_current_review_state() -> None:
    text = (REPO_ROOT / "docs/claude-development-audit/backlog.md").read_text(
        encoding="utf-8"
    )

    assert "Opus v2.0 F50-F60" in text
    assert "quality-gate self-healing" in text
    assert "RES-060" in text
    assert "WATCH-001" in text
    assert "current generated count is 102" not in text
    assert "83-test suite" not in text
