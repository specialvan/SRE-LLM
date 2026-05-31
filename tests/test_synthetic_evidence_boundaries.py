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
import scripts.review_authority_lint as review_authority_lint
from scripts.evidence_boundary_lint import (
    PUBLIC_EVIDENCE_BOUNDARY_DOCS,
    check_public_evidence_boundaries,
    find_overclaim_phrases,
    uncovered_public_prose_docs,
)
from scripts.review_authority_lint import (
    AUTHORITY_SECTIONS,
    CURRENT_LEDGER_ANCHORS,
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

HISTORICAL_REVIEW_SUBREPORTS = (
    "claude-review/docs/v2026-05-28/00-blocker-summary.md",
    "claude-review/docs/v2026-05-28/01-line-level-findings.md",
    "claude-review/docs/v2026-05-28/02-evidence-chain-audit.md",
    "claude-review/docs/v2026-05-28/03-security-and-doc-consistency.md",
    "claude-review/docs/v2026-05-28/04-deeper-dive-addendum.md",
    "claude-review/docs/v2026-05-28/evidence/rerun-log-2026-05-28.md",
    "claude-review/docs/v2026-05-31/00-executive-summary.md",
    "claude-review/docs/v2026-05-31/01-handoff-analysis.md",
    "claude-review/docs/v2026-05-31/02-quality-gates-analysis.md",
    "claude-review/docs/v2026-05-31/03-open-risks-analysis.md",
    "claude-review/docs/v2026-05-31/04-opus-packet-analysis.md",
    "claude-review/docs/v2026-05-31/05-comprehensive-review-report.md",
    "claude-review/docs/v2026-05-31/AGENT-REVIEW-GUIDE.md",
    "claude-review/docs/v2026-05-31/HANDOFF-KNOWLEDGE-BASE.md",
    "claude-review/docs/v2026-05-26/00-executive-brief.md",
    "claude-review/docs/v2026-05-26/01-scope-and-baseline.md",
    "claude-review/docs/v2026-05-26/02-resolved-findings-spot-check.md",
    "claude-review/docs/v2026-05-26/03-new-findings.md",
    "claude-review/docs/v2026-05-26/04-evidence-manifest-audit.md",
    "claude-review/docs/v2026-05-26/05-merge-gate-checklist.md",
    "claude-review/docs/v2026-05-26/evidence/verification-rerun-2026-05-26.md",
    "docs/opus-review/v1.0/DEEP_REVIEW_REPORT.md",
    "docs/opus-review/v1.0/QUALITY_GATE_VERIFICATION.md",
    "docs/opus-review/v1.0/MODULE_INSPECTION.md",
    "docs/opus-review/v1.0/LINE_LEVEL_FINDINGS.md",
    "docs/opus-review/v1.0/REPRODUCTION_EVIDENCE.md",
    "docs/opus-review/v1.0/FOLLOWUP_BACKLOG.md",
)

HISTORICAL_AUDIT_DIRECT_ENTRY_DOCS = (
    "claude-review/docs/README.md",
    "docs/claude-development-audit/reports/2026-05-15-completion-audit.md",
    "docs/claude-development-audit/reports/2026-05-15-continuation-review.md",
    "docs/claude-development-audit/reports/2026-05-15-deep-review.md",
    "docs/claude-development-audit/reports/2026-05-15-encoding-repair-note.md",
    "docs/claude-development-audit/reports/2026-05-15-joseph-form-cleanup.md",
    "docs/claude-development-audit/reports/2026-05-15-post-commit-review.md",
    "docs/claude-development-audit/reports/2026-05-15-quality-gates-html-canonical.md",
    "docs/claude-development-audit/reports/2026-05-16-adapter-cause-taxonomy.md",
    "docs/claude-development-audit/reports/2026-05-16-control-center-exposure.md",
    "docs/claude-development-audit/reports/2026-05-16-package-smoke.md",
    "docs/claude-development-audit/reports/2026-05-16-release-hygiene.md",
    "docs/claude-development-audit/reports/2026-05-16-synthetic-evidence-boundaries.md",
    "docs/claude-development-audit/evidence/2026-05-15-continuation-snapshot.md",
    "docs/claude-development-audit/evidence/2026-05-15-joseph-form-cleanup-snapshot.md",
    "docs/claude-development-audit/evidence/2026-05-15-post-commit-snapshot.md",
    "docs/claude-development-audit/evidence/2026-05-15-quality-gates-html-canonical-snapshot.md",
    "docs/claude-development-audit/evidence/2026-05-15-snapshot.md",
    "docs/claude-development-audit/evidence/2026-05-16-adapter-cause-taxonomy-snapshot.md",
    "docs/claude-development-audit/evidence/2026-05-16-control-center-exposure-snapshot.md",
    "docs/claude-development-audit/evidence/2026-05-16-package-smoke-snapshot.md",
    "docs/claude-development-audit/evidence/2026-05-16-release-hygiene-snapshot.md",
    "docs/claude-development-audit/evidence/2026-05-16-synthetic-evidence-boundaries-snapshot.md",
    "docs/claude-development-audit/git/timeline.md",
)

HISTORICAL_SUPERPOWERS_ARTIFACTS = (
    "docs/superpowers/plans/2026-05-15-claude-development-audit.md",
    "docs/superpowers/plans/2026-05-29-evidence-artifact-test-split.md",
    "docs/superpowers/plans/2026-05-29-evidence-consistency-split.md",
    "docs/superpowers/plans/2026-05-29-evidence-contract-report-test-split.md",
    "docs/superpowers/plans/2026-05-29-evidence-manifest-check-test-split.md",
    "docs/superpowers/plans/2026-05-29-evidence-manifest-generation-test-split.md",
    "docs/superpowers/plans/2026-05-29-evidence-replay-artifact-report-test-split.md",
    "docs/superpowers/plans/2026-05-29-evidence-report-manifest-shape-test-split.md",
    "docs/superpowers/plans/2026-05-29-evidence-s10-trace-report-test-split.md",
    "docs/superpowers/plans/2026-05-30-control-center-browser-dom-test-split.md",
    "docs/superpowers/plans/2026-05-30-control-center-browser-manifest-test-split.md",
    "docs/superpowers/plans/2026-05-30-evidence-contract-report-follow-on-split.md",
    "docs/superpowers/plans/2026-05-30-evidence-report-orchestrator-cleanup.md",
    "docs/superpowers/specs/2026-05-29-evidence-artifact-test-split-design.md",
    "docs/superpowers/specs/2026-05-29-evidence-consistency-split-design.md",
)

PUBLIC_ENGINEERING_DOCS = (
    "docs/control-center.html",
    "docs/API_CONTRACTS.md",
    "docs/ARCHITECTURE.md",
    "docs/ENGINEERING_CHECKLIST.md",
    "docs/EQUATION_DEEP_DIVE.md",
    "docs/EVENT_SCHEMA.md",
    "docs/FORMULA_MAP.md",
    "docs/RUNTIME_STATES.md",
    "docs/SPECIAL_SOLUTIONS_DERIVATIONS.md",
    "wiki/runtime-lifecycle.md",
)

CURRENT_LIVE_REVIEW_DOCS = (
    "docs/opus-review/HANDOFF.md",
    "docs/opus-review/README.md",
    "docs/opus-review/OPUS_REVIEW_PACKET.md",
    "docs/codex-review/OPEN_RISKS.md",
    "docs/codex-review/QUALITY_GATES.md",
    "wiki/review-backlog.md",
)

MOJIBAKE_MARKERS = ("锛", "绔", "涓", "鍦", "瀹", "銆", "€")


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
        "These algorithms are the official SpaceX implementation. "
        "This is production-grade proof for a live control plane. "
        "The scenario evidence guarantees production safety. "
        "The replay provides production guarantees. "
        "The synthetic replay demonstrates production equivalence. "
        "The evidence validates production deployment. "
        "Synthetic evidence is equivalent to a production trace."
    )

    findings = find_overclaim_phrases(text)

    assert {finding.phrase for finding in findings} == {
        "guarantees production safety",
        "proves production readiness",
        "production equivalence",
        "production guarantees",
        "production-grade proof",
        "equivalent to a production trace",
        "validates production deployment",
        "official SpaceX implementation",
    }


def test_evidence_boundary_lint_flags_ready_for_production_claims() -> None:
    text = (
        "The scenario evidence is ready for production. "
        "The synthetic replay is safe for production."
    )

    assert {finding.phrase for finding in find_overclaim_phrases(text)} == {
        "ready for production",
        "safe for production",
    }


def test_evidence_boundary_lint_flags_production_equivalent_claims() -> None:
    text = (
        "The synthetic replay is production-equivalent. "
        "The scenario trace is production equivalent."
    )

    assert {finding.phrase for finding in find_overclaim_phrases(text)} == {
        "production-equivalent",
        "production equivalent",
    }


def test_evidence_boundary_lint_flags_production_level_quality_claims() -> None:
    text = (
        "The synthetic replay is production-level evidence. "
        "The scenario trace is production caliber validation. "
        "The demo is production-quality proof."
    )

    assert {finding.phrase for finding in find_overclaim_phrases(text)} == {
        "production-level",
        "production caliber",
        "production-quality",
    }


def test_evidence_boundary_lint_flags_production_like_representative_claims() -> None:
    text = (
        "The synthetic replay is production-like evidence. "
        "The scenario trace is production representative. "
        "The demo is comparable to production."
    )

    assert {finding.phrase for finding in find_overclaim_phrases(text)} == {
        "production-like",
        "production representative",
        "comparable to production",
    }


def test_evidence_boundary_lint_flags_production_scale_realism_claims() -> None:
    text = (
        "The synthetic replay is production-scale evidence. "
        "The scenario trace is production realistic. "
        "The demo claims realistic production coverage. "
        "The replay is representative of production."
    )

    assert {finding.phrase for finding in find_overclaim_phrases(text)} == {
        "production-scale",
        "production realistic",
        "realistic production",
        "representative of production",
    }


def test_evidence_boundary_lint_flags_prod_abbreviation_and_parity_claims() -> None:
    text = (
        "The synthetic replay is prod-ready evidence. "
        "The scenario trace is prod like. "
        "The demo claims production parity. "
        "The replay has parity with production."
    )

    assert {finding.phrase for finding in find_overclaim_phrases(text)} == {
        "prod-ready",
        "prod like",
        "production parity",
        "parity with production",
    }


def test_evidence_boundary_lint_flags_spacex_provenance_claims() -> None:
    text = (
        "The synthetic replay is SpaceX official implementation. "
        "The scenario trace is SpaceX production implementation. "
        "The demo recreates SpaceX real algorithm. "
        "The replay is SpaceX flight software."
    )

    assert {finding.phrase for finding in find_overclaim_phrases(text)} == {
        "SpaceX official implementation",
        "SpaceX production implementation",
        "SpaceX real algorithm",
        "SpaceX flight software",
    }


def test_evidence_boundary_lint_flags_possessive_spacex_provenance_claims() -> None:
    text = (
        "The synthetic replay is SpaceX's official implementation. "
        "The scenario recreates SpaceX internal control algorithm. "
        "The demo claims SpaceX flight control software."
    )

    assert {finding.phrase for finding in find_overclaim_phrases(text)} == {
        "SpaceX's official implementation",
        "SpaceX internal control algorithm",
        "SpaceX flight control software",
    }


def test_evidence_boundary_lint_flags_hyphenated_spacex_provenance_claims() -> None:
    text = (
        "The synthetic replay is SpaceX-official implementation. "
        "The scenario recreates SpaceX-internal control software. "
        "The demo claims SpaceX-flight controller."
    )

    assert {finding.phrase for finding in find_overclaim_phrases(text)} == {
        "SpaceX-official implementation",
        "SpaceX-internal control software",
        "SpaceX-flight controller",
    }


def test_evidence_boundary_lint_flags_proprietary_spacex_provenance_claims() -> None:
    text = (
        "The synthetic replay is SpaceX proprietary implementation. "
        "The scenario recreates SpaceX private control algorithm. "
        "The demo claims SpaceX confidential controller."
    )

    assert {finding.phrase for finding in find_overclaim_phrases(text)} == {
        "SpaceX proprietary implementation",
        "SpaceX private control algorithm",
        "SpaceX confidential controller",
    }


def test_evidence_boundary_lint_flags_spacex_source_provenance_claims() -> None:
    text = (
        "The synthetic replay uses SpaceX flight data. "
        "The scenario trace uses SpaceX internal telemetry. "
        "The demo is based on SpaceX production logs."
    )

    assert {finding.phrase for finding in find_overclaim_phrases(text)} == {
        "SpaceX flight data",
        "SpaceX internal telemetry",
        "SpaceX production logs",
    }


def test_evidence_boundary_lint_flags_generic_source_provenance_claims() -> None:
    text = (
        "The synthetic replay uses real flight telemetry. "
        "The scenario trace is based on actual sensor data. "
        "The demo replays live incident logs. "
        "The report derives from field traces."
    )

    assert {finding.phrase for finding in find_overclaim_phrases(text)} == {
        "real flight telemetry",
        "actual sensor data",
        "live incident logs",
        "field traces",
    }


def test_evidence_boundary_lint_flags_production_source_provenance_claims() -> None:
    text = (
        "The synthetic replay uses production telemetry. "
        "The scenario trace is based on prod logs. "
        "The demo replays production incident traces. "
        "The report derives from customer traffic data."
    )

    assert {finding.phrase for finding in find_overclaim_phrases(text)} == {
        "production telemetry",
        "prod logs",
        "production incident traces",
        "customer traffic data",
    }


def test_evidence_boundary_lint_flags_source_validation_claims() -> None:
    text = (
        "The synthetic replay is validated against real incidents. "
        "The scenario trace is calibrated on live traffic. "
        "The demo is trained on customer incidents. "
        "The report is benchmarked against production incidents."
    )

    assert {finding.phrase for finding in find_overclaim_phrases(text)} == {
        "validated against real incidents",
        "calibrated on live traffic",
        "trained on customer incidents",
        "benchmarked against production incidents",
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


@pytest.mark.parametrize(
    "text",
    [
        "synthetic evidence 明确标注为研究证据，非生产证明。",
        "Section 12 replay 强调了不能作为生产证明。",
        "lint 拒绝无限定的生产就绪、官方 SpaceX 实现、生产证明措辞。",
        "避免了过度承诺：没有声称生产就绪。",
        "边界声明明确：合成证据 vs 生产证明。",
        "本仓库沿这一假设做学习/工程复现，不代表 SpaceX 官方实现。",
        "> 本仓库沿这一假设做学习/工程复现，不代\n> 表 SpaceX 官方实现。",
        (
            "## 常见陷阱与注意事项\n\n"
            "### 陷阱 5: 证据边界过度泛化\n"
            "**现象**: 将合成证据描述为生产证明\n"
            "**解决**: 运行 evidence_boundary_lint。"
        ),
    ],
)
def test_evidence_boundary_lint_allows_chinese_short_boundary_negation(
    text: str,
) -> None:
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


def test_evidence_boundary_lint_allows_negated_production_guarantees() -> None:
    text = "Synthetic before/after studies are mechanism evidence, not production guarantees."

    assert find_overclaim_phrases(text) == []


def test_evidence_boundary_lint_allows_negated_ready_for_production_wording() -> None:
    text = "The synthetic replay is not ready for production and not safe for production."

    assert find_overclaim_phrases(text) == []


def test_evidence_boundary_lint_allows_negated_production_equivalent_wording() -> None:
    text = "The synthetic replay is not production-equivalent."

    assert find_overclaim_phrases(text) == []


def test_evidence_boundary_lint_allows_negated_production_level_wording() -> None:
    text = "The synthetic replay is not production-level or production-quality evidence."

    assert find_overclaim_phrases(text) == []


def test_evidence_boundary_lint_allows_negated_production_like_wording() -> None:
    text = "The synthetic replay is not production-like and not comparable to production."

    assert find_overclaim_phrases(text) == []


def test_evidence_boundary_lint_allows_negated_production_scale_wording() -> None:
    text = (
        "The synthetic replay is not production-scale, not production realistic, "
        "not realistic production, and not representative of production."
    )

    assert find_overclaim_phrases(text) == []


def test_evidence_boundary_lint_allows_negated_prod_parity_wording() -> None:
    text = (
        "The synthetic replay is not prod-ready, not prod like, "
        "and has no production parity or parity with production."
    )

    assert find_overclaim_phrases(text) == []


def test_evidence_boundary_lint_allows_negated_spacex_provenance_wording() -> None:
    text = (
        "The repo does not represent SpaceX official implementation, "
        "SpaceX production implementation, or SpaceX flight software. "
        "The replay does not use SpaceX flight data, "
        "SpaceX internal telemetry, or SpaceX production logs."
    )

    assert find_overclaim_phrases(text) == []


def test_evidence_boundary_lint_allows_negated_generic_source_provenance_wording() -> None:
    text = (
        "The replay is not based on real flight telemetry, "
        "actual sensor data, live incident logs, or field traces."
    )

    assert find_overclaim_phrases(text) == []


def test_evidence_boundary_lint_allows_non_production_source_boundary_wording() -> None:
    text = (
        "The stack exports a non-production data contract. "
        "This is not a production incident trace contract."
    )

    assert find_overclaim_phrases(text) == []


def test_evidence_boundary_lint_allows_negated_source_validation_wording() -> None:
    text = (
        "The replay is not validated against real incidents, "
        "not calibrated on live traffic, and not trained on customer incidents."
    )

    assert find_overclaim_phrases(text) == []


def test_evidence_boundary_lint_allows_operational_live_trace_wording() -> None:
    text = "The live trace showed the debug error oscillating between samples."

    assert find_overclaim_phrases(text) == []


def test_evidence_boundary_lint_allows_wrapped_negated_spacex_provenance_wording() -> None:
    text = (
        "The project is public-material learning and engineering reproduction, not\n"
        "  SpaceX official implementation."
    )

    assert find_overclaim_phrases(text) == []


def test_evidence_boundary_lint_allows_markdown_does_not_support_table_cells() -> None:
    text = (
        "| Study | Current observation | Supports | Does not support |\n"
        "|---|---|---|---|\n"
        "| Section 1 | `pos_err 148.3 -> 2.125e-6` | "
        "synthetic mechanism evidence | SpaceX official implementation |\n"
    )

    assert find_overclaim_phrases(text) == []


def test_evidence_boundary_lint_allows_negated_production_equivalence() -> None:
    text = "Docs must avoid implying production equivalence from synthetic evidence."

    assert find_overclaim_phrases(text) == []


def test_evidence_boundary_lint_allows_negated_production_trace_boundary() -> None:
    text = "Section 12 is synthetic replay-fixture evidence, not a production trace."

    assert find_overclaim_phrases(text) == []


def test_evidence_boundary_lint_does_not_let_prior_negation_mask_later_claim() -> None:
    text = (
        "This is not production proof, but the synthetic replay proves "
        "production readiness."
    )

    assert {finding.phrase for finding in find_overclaim_phrases(text)} == {
        "proves production readiness"
    }


def test_evidence_boundary_lint_allows_explicit_forbidden_example_lists() -> None:
    text = (
        "Avoid:\n"
        "- \"The control stack is production ready.\"\n"
        "- \"Synthetic evidence is equivalent to a production benchmark.\""
    )

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


@pytest.mark.parametrize("relative_path", CURRENT_LIVE_REVIEW_DOCS)
def test_current_live_review_docs_do_not_contain_mojibake(relative_path: str) -> None:
    text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")

    assert not any(marker in text for marker in MOJIBAKE_MARKERS)


def test_evidence_boundary_lint_covers_public_and_review_entrypoints() -> None:
    expected_paths = {
        "README.md",
        "PR-REQUIREMENTS.md",
        "wiki/README.md",
        "docs/CODEX_REVIEW_REPORT.md",
        "docs/CODEX_HANDOFF.md",
        "docs/knowledge-base.html",
        "docs/V2_Knowledge/knowledge-base.html",
        *PUBLIC_ENGINEERING_DOCS,
        "docs/codex-review/CLAUDE_REVIEW_REQUEST.md",
        "docs/CONTROL_CENTER_HANDOFF.md",
        "docs/EVENT_EVIDENCE_MANIFEST.md",
        "docs/STACK_DATA_CONTRACT.md",
        "docs/claude-review/README.md",
        "docs/claude-review/HANDOFF_CHECKLIST.md",
        "docs/claude-review/CODEX_TRIAGE.md",
        "docs/claude-review/REVIEW_OF_CODEX_SESSION.md",
        "docs/claude-review/DETAILED_ARCHITECTURE.md",
        "docs/claude-review/EVENT_LIFECYCLE.md",
        "docs/claude-review/FAILURE_MODES.md",
        "claude-review/docs/v2026-05-31/README.md",
        "claude-review/docs/v2026-05-28/README.md",
        "claude-review/docs/v2026-05-26/README.md",
        "claude-review/docs/v2026-05-31/00-executive-summary.md",
        "claude-review/docs/v2026-05-31/01-handoff-analysis.md",
        "claude-review/docs/v2026-05-31/02-quality-gates-analysis.md",
        "claude-review/docs/v2026-05-31/03-open-risks-analysis.md",
        "claude-review/docs/v2026-05-31/04-opus-packet-analysis.md",
        "claude-review/docs/v2026-05-31/05-comprehensive-review-report.md",
        "claude-review/docs/v2026-05-31/AGENT-REVIEW-GUIDE.md",
        "claude-review/docs/v2026-05-31/HANDOFF-KNOWLEDGE-BASE.md",
        "docs/opus-review/v1.0/README.md",
        "docs/claude-review/v1.0/README.md",
        *HISTORICAL_REVIEW_SUBREPORTS,
        "docs/claude-development-audit/README.md",
        *HISTORICAL_AUDIT_DIRECT_ENTRY_DOCS,
        "docs/superpowers/plans/README.md",
        "docs/superpowers/specs/README.md",
        *HISTORICAL_SUPERPOWERS_ARTIFACTS,
        "docs/opus-review/README.md",
        "docs/opus-review/HANDOFF.md",
        "docs/opus-review/OPUS_REVIEW_PACKET.md",
    }

    assert expected_paths <= set(PUBLIC_EVIDENCE_BOUNDARY_DOCS)


def test_evidence_boundary_lint_covers_every_public_prose_doc() -> None:
    assert uncovered_public_prose_docs(REPO_ROOT) == []


def test_evidence_boundary_lint_covers_root_level_public_prose_docs() -> None:
    assert "spacex-Session.md" in PUBLIC_EVIDENCE_BOUNDARY_DOCS


def test_root_session_export_routes_reviewers_to_live_ledgers() -> None:
    text = (REPO_ROOT / "spacex-Session.md").read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    assert "Historical session export" in text
    for anchor in [
        "docs/opus-review/HANDOFF.md",
        "wiki/review-backlog.md",
        "docs/codex-review/OPEN_RISKS.md",
        "docs/codex-review/QUALITY_GATES.md",
    ]:
        assert anchor in normalized


def test_opus_handoff_calls_out_root_session_export_as_historical() -> None:
    text = (REPO_ROOT / "docs/opus-review/HANDOFF.md").read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    assert "spacex-Session.md" in normalized
    assert "historical session export" in normalized


def test_evidence_boundary_lint_cli_reports_clean_public_surface() -> None:
    assert check_public_evidence_boundaries(REPO_ROOT) == []


def test_development_audit_readme_routes_current_status_to_live_ledgers() -> None:
    text = (REPO_ROOT / "docs/claude-development-audit/README.md").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(text.split())

    assert "## Current Status Routing" in text
    for anchor in [
        "wiki/review-backlog.md",
        "docs/codex-review/OPEN_RISKS.md",
        "docs/codex-review/QUALITY_GATES.md",
        "docs/opus-review/HANDOFF.md",
    ]:
        assert anchor in normalized
    assert "## Current Snapshot" not in text
    assert "107 tests" not in text
    assert "10 studies" not in text
    assert "HEAD:" not in text


def test_legacy_claude_review_readme_routes_current_status_to_opus_handoff() -> None:
    text = (REPO_ROOT / "docs/claude-review/README.md").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(text.split())

    assert "Historical Review Package" in text
    assert "not the current handoff" in normalized
    for anchor in [
        "docs/opus-review/HANDOFF.md",
        "wiki/review-backlog.md",
        "docs/codex-review/OPEN_RISKS.md",
        "docs/codex-review/QUALITY_GATES.md",
    ]:
        assert anchor in normalized
    assert "51 passed / 10 studies" not in normalized
    assert "current completed/open" in normalized


def test_legacy_claude_handoff_checklist_routes_reviewers_to_opus_handoff() -> None:
    text = (REPO_ROOT / "docs/claude-review/HANDOFF_CHECKLIST.md").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(text.split())

    assert "Historical Checklist" in text
    assert "not the current handoff" in normalized
    for anchor in [
        "docs/opus-review/HANDOFF.md",
        "wiki/review-backlog.md",
        "docs/codex-review/OPEN_RISKS.md",
        "docs/codex-review/QUALITY_GATES.md",
    ]:
        assert anchor in normalized
    assert "51 passed" not in normalized
    assert "All 10 studies" not in normalized
    assert "Acknowledged: docs/claude-review/README.md" not in normalized


def test_legacy_claude_triage_routes_current_facts_to_opus_handoff() -> None:
    text = (REPO_ROOT / "docs/claude-review/CODEX_TRIAGE.md").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(text.split())

    assert "Historical Triage Note" in text
    assert "not the current handoff" in normalized
    for anchor in [
        "docs/opus-review/HANDOFF.md",
        "wiki/review-backlog.md",
        "docs/codex-review/OPEN_RISKS.md",
        "docs/codex-review/QUALITY_GATES.md",
    ]:
        assert anchor in normalized
    assert "当前仓库事实" not in normalized
    assert "51 passed" not in normalized


def test_legacy_codex_review_report_routes_current_status_to_opus_handoff() -> None:
    text = (REPO_ROOT / "docs/CODEX_REVIEW_REPORT.md").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(text.split())

    assert "Historical Codex Review Report" in text
    assert "not the current handoff" in normalized
    for anchor in [
        "docs/opus-review/HANDOFF.md",
        "wiki/review-backlog.md",
        "docs/codex-review/OPEN_RISKS.md",
        "docs/codex-review/QUALITY_GATES.md",
    ]:
        assert anchor in normalized
    assert "## 褰撳墠鐘舵€?" not in text


@pytest.mark.parametrize(
    "relative_path, title",
    [
        ("docs/claude-review/REVIEW_OF_CODEX_SESSION.md", "Historical Session Review"),
        ("docs/claude-review/DETAILED_ARCHITECTURE.md", "Historical Architecture Note"),
        ("docs/claude-review/EVENT_LIFECYCLE.md", "Historical Event Lifecycle Note"),
        ("docs/claude-review/FAILURE_MODES.md", "Historical Failure Modes Note"),
    ],
)
def test_legacy_claude_leaf_docs_route_reviewers_to_opus_handoff(
    relative_path: str,
    title: str,
) -> None:
    text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    assert title in text
    assert "not the current handoff" in normalized
    for anchor in [
        "docs/opus-review/HANDOFF.md",
        "wiki/review-backlog.md",
        "docs/codex-review/OPEN_RISKS.md",
        "docs/codex-review/QUALITY_GATES.md",
    ]:
        assert anchor in normalized


@pytest.mark.parametrize(
    "relative_path, title",
    [
        ("claude-review/docs/v2026-05-28/README.md", "Historical Opus v2.1 Review Packet"),
        ("claude-review/docs/v2026-05-31/README.md", "Historical Opus v2026-05-31 Review Packet"),
        ("claude-review/docs/v2026-05-26/README.md", "Historical Opus v2.0 Review Packet"),
        ("docs/opus-review/v1.0/README.md", "Historical Opus v1.0 Review Packet"),
        ("docs/claude-review/v1.0/README.md", "Historical Opus v1.0 Pointer"),
    ],
)
def test_versioned_historical_review_packets_route_to_live_ledgers(
    relative_path: str,
    title: str,
) -> None:
    text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    assert title in text
    assert "not the current handoff" in normalized
    for anchor in [
        "docs/opus-review/HANDOFF.md",
        "wiki/review-backlog.md",
        "docs/codex-review/OPEN_RISKS.md",
        "docs/codex-review/QUALITY_GATES.md",
    ]:
        assert anchor in normalized


@pytest.mark.parametrize("relative_path", HISTORICAL_REVIEW_SUBREPORTS)
def test_versioned_historical_review_subreports_route_direct_entry_to_live_ledgers(
    relative_path: str,
) -> None:
    text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    assert "not the current handoff" in normalized
    for anchor in [
        "docs/opus-review/HANDOFF.md",
        "wiki/review-backlog.md",
        "docs/codex-review/OPEN_RISKS.md",
        "docs/codex-review/QUALITY_GATES.md",
    ]:
        assert anchor in normalized


@pytest.mark.parametrize("relative_path", HISTORICAL_AUDIT_DIRECT_ENTRY_DOCS)
def test_historical_audit_direct_entry_docs_route_to_live_ledgers(
    relative_path: str,
) -> None:
    text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    assert "not the current handoff" in normalized
    for anchor in [
        "docs/opus-review/HANDOFF.md",
        "wiki/review-backlog.md",
        "docs/codex-review/OPEN_RISKS.md",
        "docs/codex-review/QUALITY_GATES.md",
    ]:
        assert anchor in normalized


@pytest.mark.parametrize("relative_path", HISTORICAL_SUPERPOWERS_ARTIFACTS)
def test_superpowers_plan_and_spec_artifacts_route_to_live_ledgers(
    relative_path: str,
) -> None:
    text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    assert "not the current handoff" in normalized
    for anchor in [
        "docs/opus-review/HANDOFF.md",
        "wiki/review-backlog.md",
        "docs/codex-review/OPEN_RISKS.md",
        "docs/codex-review/QUALITY_GATES.md",
    ]:
        assert anchor in normalized


def test_opus_handoff_reads_current_ledgers_before_historical_packets() -> None:
    assert find_authority_order_errors(REPO_ROOT / "docs/opus-review/HANDOFF.md") == []


def test_wiki_recommended_entries_put_current_ledgers_before_historical_reviews() -> None:
    assert find_authority_order_errors(REPO_ROOT / "wiki/README.md") == []


def test_opus_readme_lists_current_ledgers_before_historical_reviews() -> None:
    assert find_authority_order_errors(REPO_ROOT / "docs/opus-review/README.md") == []


def test_codex_review_readme_lists_current_ledgers_before_historical_reviews() -> None:
    assert find_authority_order_errors(REPO_ROOT / 'docs/codex-review/README.md') == []


def test_opus_packet_review_position_lists_current_ledgers_before_history() -> None:
    assert find_authority_order_errors(REPO_ROOT / 'docs/opus-review/OPUS_REVIEW_PACKET.md') == []


def test_superpowers_plan_inventory_lists_current_ledgers_in_handoff_order() -> None:
    assert find_authority_order_errors(REPO_ROOT / "docs/superpowers/plans/README.md") == []


def test_superpowers_spec_inventory_lists_current_ledgers_in_handoff_order() -> None:
    assert find_authority_order_errors(REPO_ROOT / "docs/superpowers/specs/README.md") == []


def test_review_authority_lint_covers_current_entrypoints() -> None:
    assert set(configured_authority_paths()) == {
        "docs/CODEX_HANDOFF.md",
        "docs/CODEX_REVIEW_REPORT.md",
        "docs/codex-review/CODEX_SUMMARY.md",
        "docs/codex-review/CLAUDE_DEEP_REVIEW.md",
        "docs/codex-review/CLAUDE_REFINED_SPEC.md",
        "docs/codex-review/CLAUDE_REVIEW_REQUEST.md",
        "docs/codex-review/ENGINEERING_PACKET.md",
        "docs/CONTROL_CENTER_HANDOFF.md",
        "docs/V2_Knowledge/knowledge-base.html",
        'docs/codex-review/README.md',
        'docs/opus-review/OPUS_REVIEW_PACKET.md',
        "docs/claude-development-audit/README.md",
        "docs/opus-review/README.md",
        "docs/opus-review/HANDOFF.md",
        "wiki/README.md",
        "wiki/project-overview.md",
        "docs/superpowers/plans/README.md",
        "docs/superpowers/specs/README.md",
    }


def test_review_authority_lint_uses_handoff_live_ledger_order() -> None:
    assert CURRENT_LEDGER_ANCHORS == (
        "wiki/review-backlog.md",
        "docs/codex-review/OPEN_RISKS.md",
        "docs/codex-review/QUALITY_GATES.md",
    )


def test_review_authority_lint_reports_missing_git_scope_routing(tmp_path) -> None:
    doc = tmp_path / "docs" / "codex-review" / "README.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "## Contents\n"
        "`../../wiki/README.md` `OPEN_RISKS.md` `QUALITY_GATES.md`\n"
        "## Reading Order\n"
        "`../../wiki/review-backlog.md` `OPEN_RISKS.md` `QUALITY_GATES.md`\n"
        "## Current Baseline\n",
        encoding="utf-8",
    )
    finder = getattr(review_authority_lint, "find_git_scope_routing_errors", None)

    assert finder is not None
    assert finder(doc) == [
        "docs/codex-review/README.md: missing docs/opus-review/HANDOFF.md "
        "in git review scope routing",
        "docs/codex-review/README.md: missing Git Review Scope Snapshot "
        "in git review scope routing",
        "docs/codex-review/README.md: missing "
        "git status --short --branch --untracked-files=all "
        "in git review scope routing",
        "docs/codex-review/README.md: missing "
        "git ls-files --others --exclude-standard in git review scope routing",
        "docs/codex-review/README.md: missing dirty/untracked "
        "in git review scope routing",
    ]


def test_review_authority_gate_includes_git_scope_routing_errors(
    tmp_path,
    monkeypatch,
) -> None:
    doc = tmp_path / "docs" / "codex-review" / "README.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "## Contents\n"
        "`../../wiki/README.md` `OPEN_RISKS.md` `QUALITY_GATES.md`\n"
        "## Reading Order\n"
        "`../../wiki/review-backlog.md` `OPEN_RISKS.md` `QUALITY_GATES.md`\n"
        "## Current Baseline\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        review_authority_lint,
        "AUTHORITY_SECTIONS",
        (
            review_authority_lint.AuthoritySection(
                "docs/codex-review/README.md",
                "## Contents",
                "## Current Baseline",
                "temporary review packet routing",
                anchor_aliases={
                    "wiki/review-backlog.md": (
                        "../../wiki/README.md",
                        "../../wiki/review-backlog.md",
                    ),
                    "docs/codex-review/OPEN_RISKS.md": ("OPEN_RISKS.md",),
                    "docs/codex-review/QUALITY_GATES.md": ("QUALITY_GATES.md",),
                },
            ),
        ),
    )

    errors = review_authority_lint.check_authority_order(tmp_path)

    assert (
        "docs/codex-review/README.md: missing Git Review Scope Snapshot "
        "in git review scope routing"
    ) in errors


def test_review_authority_git_scope_routing_must_be_in_authority_section(
    tmp_path,
    monkeypatch,
) -> None:
    doc = tmp_path / "docs" / "codex-review" / "README.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "## Current Routing\n"
        "`../../wiki/review-backlog.md` `OPEN_RISKS.md` `QUALITY_GATES.md`\n"
        "## Historical Notes\n"
        "`docs/opus-review/HANDOFF.md`\n"
        "`Git Review Scope Snapshot`\n"
        "`git status --short --branch --untracked-files=all`\n"
        "`git ls-files --others --exclude-standard`\n"
        "`dirty/untracked`\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        review_authority_lint,
        "AUTHORITY_SECTIONS",
        (
            review_authority_lint.AuthoritySection(
                "docs/codex-review/README.md",
                "## Current Routing",
                "## Historical Notes",
                "temporary current routing",
                anchor_aliases={
                    "wiki/review-backlog.md": ("../../wiki/review-backlog.md",),
                    "docs/codex-review/OPEN_RISKS.md": ("OPEN_RISKS.md",),
                    "docs/codex-review/QUALITY_GATES.md": ("QUALITY_GATES.md",),
                },
            ),
        ),
    )

    errors = review_authority_lint.find_git_scope_routing_errors(doc)

    assert errors == [
        "docs/codex-review/README.md: missing docs/opus-review/HANDOFF.md "
        "in git review scope routing",
        "docs/codex-review/README.md: missing Git Review Scope Snapshot "
        "in git review scope routing",
        "docs/codex-review/README.md: missing "
        "git status --short --branch --untracked-files=all "
        "in git review scope routing",
        "docs/codex-review/README.md: missing "
        "git ls-files --others --exclude-standard in git review scope routing",
        "docs/codex-review/README.md: missing dirty/untracked "
        "in git review scope routing",
    ]


def test_git_scope_routing_reports_missing_configured_section_marker(
    tmp_path,
    monkeypatch,
) -> None:
    doc = tmp_path / "docs" / "codex-review" / "README.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "Current routing text without the configured header:\n"
        "`docs/opus-review/HANDOFF.md`\n"
        "`Git Review Scope Snapshot`\n"
        "`git status --short --branch --untracked-files=all`\n"
        "`git ls-files --others --exclude-standard`\n"
        "`dirty/untracked`\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        review_authority_lint,
        "AUTHORITY_SECTIONS",
        (
            review_authority_lint.AuthoritySection(
                "docs/codex-review/README.md",
                "## Current Routing",
                "## Historical Notes",
                "temporary current routing",
            ),
        ),
    )

    errors = review_authority_lint.find_git_scope_routing_errors(doc)

    assert errors == [
        "docs/codex-review/README.md: missing start marker "
        "## Current Routing for temporary current routing"
    ]


def test_review_authority_lint_does_not_require_opus_handoff_to_link_to_itself(
    tmp_path,
) -> None:
    doc = tmp_path / "docs" / "opus-review" / "HANDOFF.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "Treat the live ledgers as the source of truth before reading historical packets:\n"
        "## Git Review Scope Snapshot\n"
        "git status --short --branch --untracked-files=all\n"
        "git ls-files --others --exclude-standard\n"
        "dirty/untracked review scope\n"
        "## Current Baseline\n",
        encoding="utf-8",
    )
    finder = getattr(review_authority_lint, "find_git_scope_routing_errors", None)

    assert finder is not None
    assert finder(doc) == []


def test_review_authority_lint_current_entrypoints_have_git_scope_routing() -> None:
    finder = getattr(review_authority_lint, "find_git_scope_routing_errors", None)

    assert finder is not None
    for relative_path in configured_authority_paths():
        assert finder(REPO_ROOT / relative_path) == []


def test_opus_handoff_authority_lint_uses_current_section_markers() -> None:
    section = next(
        section
        for section in AUTHORITY_SECTIONS
        if section.relative_path == "docs/opus-review/HANDOFF.md"
    )

    assert section.start_marker == "live ledgers as the source of truth"
    assert section.end_marker == "## Current Baseline"
    assert section.label == "Opus handoff live ledger order"


def test_project_overview_authority_lint_uses_current_section_markers() -> None:
    section = next(
        section
        for section in AUTHORITY_SECTIONS
        if section.relative_path == "wiki/project-overview.md"
    )

    assert section.start_marker == "## Current Execution Authority"
    assert section.end_marker == "## "
    assert section.label == "Current Execution Authority"
    assert "docs/codex-review/CLAUDE_REFINED_SPEC.md" in section.historical


def test_v2_knowledge_base_authority_lint_uses_handoff_section_markers() -> None:
    section = next(
        section
        for section in AUTHORITY_SECTIONS
        if section.relative_path == "docs/V2_Knowledge/knowledge-base.html"
    )

    assert section.start_marker == '<section id="handoff">'
    assert section.end_marker == "<!-- ===================== Next Work"
    assert section.label == "V2 knowledge-base handoff routing"
    assert "docs/claude-review/README.md" in section.historical


def test_v2_knowledge_base_lists_current_ledgers_in_handoff_order() -> None:
    assert (
        find_authority_order_errors(
            REPO_ROOT / "docs/V2_Knowledge/knowledge-base.html"
        )
        == []
    )


@pytest.mark.parametrize(
    "relative_path",
    [
        "docs/CODEX_HANDOFF.md",
        "docs/CODEX_REVIEW_REPORT.md",
        "docs/codex-review/CODEX_SUMMARY.md",
        "docs/codex-review/CLAUDE_DEEP_REVIEW.md",
        "docs/codex-review/CLAUDE_REFINED_SPEC.md",
        "docs/codex-review/CLAUDE_REVIEW_REQUEST.md",
        "docs/codex-review/ENGINEERING_PACKET.md",
        "docs/CONTROL_CENTER_HANDOFF.md",
        "docs/claude-development-audit/README.md",
    ],
)
def test_review_authority_lint_covers_additional_clickable_handoff_entries(
    relative_path: str,
) -> None:
    assert find_authority_order_errors(REPO_ROOT / relative_path) == []


def test_review_authority_lint_reports_historical_packet_before_current_ledger(
    tmp_path,
) -> None:
    doc = tmp_path / "HANDOFF.md"
    doc.write_text(
        "Treat the live ledgers as the source of truth before reading historical packets:\n"
        "1. `claude-review/docs/v2026-05-28/README.md`\n"
        "2. `wiki/review-backlog.md`, `docs/codex-review/OPEN_RISKS.md`, "
        "and `docs/codex-review/QUALITY_GATES.md`\n"
        "3. `docs/opus-review/OPUS_REVIEW_PACKET.md`\n"
        "## Current Baseline\n",
        encoding="utf-8",
    )

    errors = find_authority_order_errors(doc)

    assert errors == [
        "HANDOFF.md: wiki/review-backlog.md must appear before "
        "claude-review/docs/v2026-05-28/README.md in review authority order",
        "HANDOFF.md: docs/codex-review/OPEN_RISKS.md must appear before "
        "claude-review/docs/v2026-05-28/README.md in review authority order",
        "HANDOFF.md: docs/codex-review/QUALITY_GATES.md must appear before "
        "claude-review/docs/v2026-05-28/README.md in review authority order",
    ]


def test_review_authority_lint_reports_current_ledger_internal_order_drift(
    tmp_path,
) -> None:
    doc = tmp_path / "HANDOFF.md"
    doc.write_text(
        "Treat the live ledgers as the source of truth before reading historical packets:\n"
        "1. `docs/codex-review/OPEN_RISKS.md`\n"
        "2. `wiki/review-backlog.md`\n"
        "3. `docs/codex-review/QUALITY_GATES.md`\n"
        "4. `docs/opus-review/OPUS_REVIEW_PACKET.md`\n"
        "## Current Baseline\n",
        encoding="utf-8",
    )

    errors = find_authority_order_errors(doc)

    assert errors == [
        "HANDOFF.md: wiki/review-backlog.md must appear before "
        "docs/codex-review/OPEN_RISKS.md in review authority order"
    ]


def test_review_authority_lint_reports_missing_configured_section_marker(
    tmp_path,
    monkeypatch,
) -> None:
    doc = tmp_path / "docs" / "codex-review" / "README.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "Current routing text without the configured header:\n"
        "`../../wiki/review-backlog.md` `OPEN_RISKS.md` `QUALITY_GATES.md`\n"
        "`docs/opus-review/OPUS_REVIEW_PACKET.md`\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        review_authority_lint,
        "AUTHORITY_SECTIONS",
        (
            review_authority_lint.AuthoritySection(
                "docs/codex-review/README.md",
                "## Current Routing",
                "## Historical Notes",
                "temporary current routing",
                anchor_aliases={
                    "wiki/review-backlog.md": ("../../wiki/review-backlog.md",),
                    "docs/codex-review/OPEN_RISKS.md": ("OPEN_RISKS.md",),
                    "docs/codex-review/QUALITY_GATES.md": ("QUALITY_GATES.md",),
                },
            ),
        ),
    )

    errors = find_authority_order_errors(doc)

    assert errors == [
        "docs/codex-review/README.md: missing start marker "
        "## Current Routing for temporary current routing"
    ]


def test_review_authority_lint_reports_secondary_section_order_drift(
    tmp_path,
) -> None:
    doc = tmp_path / "docs" / "codex-review" / "README.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "## Contents\n"
        "| File | Purpose |\n"
        "|---|---|\n"
        "| `CLAUDE_DEEP_REVIEW.md` | historical |\n"
        "| `../../wiki/README.md` | current wiki |\n"
        "| `OPEN_RISKS.md` | current risks |\n"
        "| `QUALITY_GATES.md` | current gates |\n"
        "## Reading Order\n"
        "1. `../../wiki/review-backlog.md`\n"
        "2. `OPEN_RISKS.md`\n"
        "3. `QUALITY_GATES.md`\n"
        "4. historical packets\n"
        "## Current Baseline\n",
        encoding="utf-8",
    )

    errors = find_authority_order_errors(doc)

    assert errors == [
        "docs/codex-review/README.md: wiki/review-backlog.md must appear before "
        "docs/codex-review/CLAUDE_DEEP_REVIEW.md in Contents",
        "docs/codex-review/README.md: docs/codex-review/OPEN_RISKS.md must appear before "
        "docs/codex-review/CLAUDE_DEEP_REVIEW.md in Contents",
        "docs/codex-review/README.md: docs/codex-review/QUALITY_GATES.md must appear before "
        "docs/codex-review/CLAUDE_DEEP_REVIEW.md in Contents",
    ]


def test_review_authority_lint_reports_opus_readme_authority_order_drift(
    tmp_path,
) -> None:
    doc = tmp_path / "docs" / "opus-review" / "README.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "## First-Read Files\n"
        "| File | Purpose | How to read it |\n"
        "|---|---|---|\n"
        "| `HANDOFF.md` | handoff | read first |\n"
        "| `../../wiki/review-backlog.md` | ledger | check status |\n"
        "| `../codex-review/OPEN_RISKS.md` | risks | check risks |\n"
        "| `../codex-review/QUALITY_GATES.md` | gates | rerun gates |\n"
        "## Historical Inputs\n"
        "## Authority Order\n"
        "1. Current source, tests, and generated evidence artifacts.\n"
        "2. `wiki/review-backlog.md`.\n"
        "3. `docs/opus-review/HANDOFF.md`.\n"
        "4. `docs/codex-review/OPEN_RISKS.md`.\n"
        "5. `docs/codex-review/QUALITY_GATES.md`.\n"
        "## Boundaries\n",
        encoding="utf-8",
    )

    errors = find_authority_order_errors(doc)

    assert errors == [
        "docs/opus-review/README.md: docs/opus-review/HANDOFF.md must appear before "
        "wiki/review-backlog.md in Authority Order"
    ]


def test_review_authority_lint_errors_include_configured_relative_path(
    tmp_path,
) -> None:
    doc = tmp_path / "docs" / "superpowers" / "plans" / "README.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "Current review state is authoritative in this order:\n"
        "1. `docs/codex-review/OPEN_RISKS.md`\n"
        "2. `wiki/review-backlog.md`\n"
        "3. `docs/codex-review/QUALITY_GATES.md`\n"
        "## Current Artifact Inventory\n",
        encoding="utf-8",
    )

    errors = find_authority_order_errors(doc)

    assert errors == [
        "docs/superpowers/plans/README.md: wiki/review-backlog.md must appear before "
        "docs/codex-review/OPEN_RISKS.md in Superpowers plan inventory authority order"
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
