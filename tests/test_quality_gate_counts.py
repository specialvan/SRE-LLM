from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.quality_gate_counts as quality_gate_counts
import scripts.review_authority_lint as review_authority_lint
from scripts.quality_gate_counts import (
    QUALITY_GATE_TARGETS,
    check_quality_gate_docs,
    collect_pytest_count,
    parse_collected_count,
    parse_pytest_passed_count,
    render_pytest_label,
    replace_once,
    run_evidence_artifact_gates,
    update_quality_gate_docs,
)


CONTROL_CENTER_EVIDENCE_SUMMARY = (
    "control-center.v1 @ /api/control-center; desktop+mobile; "
    "error=desktop:1440x960:dom59890; frontend_error=desktop:1440x960:dom63261; "
    "manifest_records=normal+backend_error+frontend_error; "
    "manifest_replay=normal+backend_error+frontend_error; "
    "contract_depth=top_level:11 object_groups:5 object_fields:21 "
    "array_item_groups:7 array_item_fields:36 timeline_fields:14"
)
BROWSER_REPORT_COMMAND = (
    "python -m scripts.control_center_browser_smoke --report-manifests "
    "--report-json analysis/artifacts/control-center-browser-evidence-report.json"
)
CONTROL_CENTER_HANDOFF_TEST_FILES = (
    "tests/test_control_center.py",
    "tests/test_control_center_browser_smoke.py",
    "tests/test_control_center_browser_dom.py",
    "tests/test_control_center_browser_manifest.py",
    "tests/test_control_center_browser_error_manifest.py",
    "tests/test_control_center_browser_report.py",
    "tests/test_control_center_integration_audit.py",
)
CONTROL_CENTER_HANDOFF_TEST_COMMAND = (
    "python -m pytest " + " ".join(CONTROL_CENTER_HANDOFF_TEST_FILES) + " -q"
)
CURRENT_UNTRACKED_REVIEW_SCOPE = (
    "analysis/evidence_consistency.py",
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
    "docs/superpowers/plans/README.md",
    "docs/superpowers/specs/2026-05-29-evidence-artifact-test-split-design.md",
    "docs/superpowers/specs/2026-05-29-evidence-consistency-split-design.md",
    "docs/superpowers/specs/README.md",
    "tests/test_control_center_browser_dom.py",
    "tests/test_control_center_browser_error_manifest.py",
    "tests/test_control_center_browser_manifest.py",
    "tests/test_control_center_browser_report.py",
    "tests/test_evidence_consistency.py",
    "tests/test_evidence_contract_boundary_report.py",
    "tests/test_evidence_contract_fallback_report.py",
    "tests/test_evidence_contract_report.py",
    "tests/test_evidence_contract_trace_report.py",
    "tests/test_evidence_manifest_generation.py",
    "tests/test_evidence_replay_artifacts_report.py",
    "tests/test_evidence_replay_consistency_report.py",
    "tests/test_evidence_replay_report.py",
    "tests/test_evidence_report_artifact_paths.py",
    "tests/test_evidence_report_contract_shape.py",
    "tests/test_evidence_report_manifest_shape.py",
    "tests/test_evidence_report_study_shape.py",
    "tests/test_evidence_trace_report.py",
    "tests/test_evidence_wrapper_report.py",
)


def _current_synchronized_count(text: str) -> str:
    match = re.search(r"Current synchronized pytest count: `(?P<count>\d+)`", text)
    assert match is not None
    return match.group("count")


def _command_lines() -> str:
    return "\n".join(quality_gate_counts.FINAL_REVIEW_GATE_COMMANDS) + "\n"


def _bullet_command_lines() -> str:
    return "".join(
        f"  - {command}\n" for command in quality_gate_counts.FINAL_REVIEW_GATE_COMMANDS
    )


def _count_and_command_lines(count: int = 83) -> str:
    return (
        f"Current synchronized pytest count: `{count}`\n"
        f"- `python -m pytest --collect-only -q tests` still totals {count} collected tests.\n"
        f"- `python -u -m scripts.quality_gate_counts` reported `quality gate pytest count: {count}`.\n"
        f"quality gate pytest count: {count}\n"
        "python -m pytest tests -q\n"
        + _command_lines()
    )


def _engineering_packet_text(count: int = 83) -> str:
    return (
        f"Current synchronized pytest count: `{count}`.\n"
        + "```bash\n"
        + "\n".join(_opus_packet_expected_review_commands())
        + "\n```\n"
    )


def _fenced_command_block_after(text: str, marker: str) -> list[str]:
    start = text.index(marker)
    fence_start = text.index("```", start)
    command_start = text.index("\n", fence_start) + 1
    fence_end = text.index("```", command_start)
    return [line.strip() for line in text[command_start:fence_end].splitlines() if line.strip()]


def _opus_packet_expected_review_commands() -> list[str]:
    return list(quality_gate_counts.FINAL_REVIEW_GATE_COMMANDS)


def _current_execution_commands() -> list[str]:
    return list(quality_gate_counts.CURRENT_QUALITY_GATE_COMMANDS)


def _write_minimal_quality_gate_docs(root: Path) -> None:
    pr = root / "PR-REQUIREMENTS.md"
    html = root / "docs" / "V2_Knowledge" / "knowledge-base.html"
    wiki_readme = root / "wiki" / "README.md"
    backlog = root / "wiki" / "review-backlog.md"
    evidence_ledger = root / "wiki" / "evidence-ledger.md"
    codex_summary = root / "docs" / "codex-review" / "CODEX_SUMMARY.md"
    codex_readme = root / "docs" / "codex-review" / "README.md"
    quality_gates = root / "docs" / "codex-review" / "QUALITY_GATES.md"
    engineering_packet = root / "docs" / "codex-review" / "ENGINEERING_PACKET.md"
    audit_backlog = root / "docs" / "claude-development-audit" / "backlog.md"
    opus_packet = root / "docs" / "opus-review" / "OPUS_REVIEW_PACKET.md"
    opus_handoff = root / "docs" / "opus-review" / "HANDOFF.md"
    html.parent.mkdir(parents=True)
    backlog.parent.mkdir(parents=True)
    codex_summary.parent.mkdir(parents=True)
    audit_backlog.parent.mkdir(parents=True)
    opus_packet.parent.mkdir(parents=True)
    pr.write_text(
        "quality-gates:\n"
        "  - python -m pytest tests -q       # 83 passed\n"
        + _bullet_command_lines().replace("  - python -m pytest tests -q\n", "")
        + "\n"
        "| 鍗曞厓娴嬭瘯 | `python -m pytest tests -q` | **83 passed** |\n",
        encoding="utf-8",
    )
    html.write_text(
        '<div class="chip"><b>tests</b> 83 passed</div>\n'
        "<tr><td><code>python -m pytest tests -q</code></td><td><b>83 passed</b></td><td>300 s budget</td></tr>\n"
        + _command_lines(),
        encoding="utf-8",
    )
    wiki_readme.write_text(
        "- Current verified local gates: `python -m pytest tests -q` passes with 83\n"
        "  tests; `python -m analysis.run_all` completes 12 studies.\n",
        encoding="utf-8",
    )
    backlog.write_text(
        "- Full test suite: `python -m pytest tests -q` passes with 83 tests\n"
        "- Fresh verification: `quality gate pytest count: 83`.\n"
        + _command_lines(),
        encoding="utf-8",
    )
    evidence_ledger.write_text(
        "python -m pytest tests -q      # 83 passed\n",
        encoding="utf-8",
    )
    codex_summary.write_text(
        "- `tests/`: current full suite passes with 83 tests.\n",
        encoding="utf-8",
    )
    codex_readme.write_text(
        "| Unit/integration tests | `83 passed` |\n",
        encoding="utf-8",
    )
    quality_gates.write_text(
        "python -m pytest tests -q\n83 passed\n"
        "quality gate pytest count: 83\n"
        + _command_lines(),
        encoding="utf-8",
    )
    engineering_packet.write_text(
        _engineering_packet_text(),
        encoding="utf-8",
    )
    audit_backlog.write_text(_command_lines(), encoding="utf-8")
    opus_packet.write_text(
        _command_lines()
        +
        "Current synchronized pytest count: `83`\n"
        +
        "quality gate pytest count: 83\n",
        encoding="utf-8",
    )
    opus_handoff.write_text(_count_and_command_lines(), encoding="utf-8")


def test_parse_pytest_passed_count_supports_pytest_summary_formats():
    assert parse_pytest_passed_count("90 passed in 0.12s") == 90
    assert (
        parse_pytest_passed_count(
            "================ 90 passed, 1 warning in 0.12s ================"
        )
        == 90
    )


def test_parse_pytest_passed_count_fails_loudly_on_unknown_output():
    with pytest.raises(RuntimeError, match="Could not parse pytest pass count"):
        parse_pytest_passed_count("no pytest pass summary here")


def test_parse_collected_count_supports_quiet_pytest_file_counts():
    assert parse_collected_count("tests/test_a.py: 2\ntests/test_b.py: 3") == 5


def test_parse_collected_count_fails_loudly_on_unknown_output():
    with pytest.raises(RuntimeError, match="Could not parse pytest collection count"):
        parse_collected_count("no collection summary here")


def test_render_pytest_label_uses_current_docs_wording():
    assert render_pytest_label(85) == "85 passed"


def test_quality_gate_targets_are_data_driven_with_unique_labels():
    labels = [target.label for target in QUALITY_GATE_TARGETS]
    paths = {target.relative_path for target in QUALITY_GATE_TARGETS}

    assert len(labels) == len(set(labels))
    assert "PR-REQUIREMENTS.md" in paths
    assert "docs/V2_Knowledge/knowledge-base.html" in paths
    assert "docs/codex-review/QUALITY_GATES.md" in paths
    assert "docs/opus-review/HANDOFF.md" in paths
    assert "docs/opus-review/OPUS_REVIEW_PACKET.md" in paths
    assert all(target.pattern for target in QUALITY_GATE_TARGETS)
    assert all(target.replacement_template for target in QUALITY_GATE_TARGETS)


def test_current_quality_gate_commands_include_demo_smoke_gate():
    assert (
        "python -m examples.demo_sre_loop"
        in quality_gate_counts.CURRENT_QUALITY_GATE_COMMANDS
    )


def test_current_quality_gate_commands_use_compact_pytest_gate():
    assert quality_gate_counts.CURRENT_QUALITY_GATE_COMMANDS[0] == (
        "python -m pytest tests -q"
    )


def test_current_quality_gate_commands_include_control_center_integration_audit():
    assert "python -m scripts.control_center_integration_audit" in (
        quality_gate_counts.CURRENT_QUALITY_GATE_COMMANDS
    )


def test_current_quality_gate_commands_include_browser_and_package_smoke_gates():
    assert BROWSER_REPORT_COMMAND in quality_gate_counts.CURRENT_QUALITY_GATE_COMMANDS
    assert "python -m scripts.package_smoke" in quality_gate_counts.CURRENT_QUALITY_GATE_COMMANDS


def test_current_quality_gate_commands_include_review_authority_lint_gate():
    assert "python -m scripts.review_authority_lint" in (
        quality_gate_counts.CURRENT_QUALITY_GATE_COMMANDS
    )
    assert quality_gate_counts.REVIEW_AUTHORITY_GATE_MODULES == (
        "scripts.review_authority_lint",
    )
    sections_by_path: dict[str, list[review_authority_lint.AuthoritySection]] = {}
    for section in review_authority_lint.AUTHORITY_SECTIONS:
        sections_by_path.setdefault(section.relative_path, []).append(section)
    opus_section = sections_by_path["docs/opus-review/OPUS_REVIEW_PACKET.md"][0]
    opus_readme_section = next(
        section
        for section in sections_by_path["docs/opus-review/README.md"]
        if section.label == "First-Read Files"
    )
    opus_readme_authority_section = next(
        (
            section
            for section in sections_by_path["docs/opus-review/README.md"]
            if section.label == "Authority Order"
        ),
        None,
    )

    assert "docs/codex-review/QUALITY_GATES.md" in review_authority_lint.CURRENT_LEDGER_ANCHORS
    assert opus_section.start_marker == "## 0. How To Review This Packet Now"
    assert opus_section.end_marker == "## Historical Context"
    assert opus_section.label == "How To Review This Packet Now"
    assert opus_readme_section.start_marker == "## First-Read Files"
    assert opus_readme_section.end_marker == "## Historical Inputs"
    assert opus_readme_section.label == "First-Read Files"
    assert opus_readme_authority_section is not None
    assert opus_readme_authority_section.start_marker == "## Authority Order"
    assert opus_readme_authority_section.end_marker == "## Boundaries"
    assert opus_readme_authority_section.required_current == (
        "docs/opus-review/HANDOFF.md",
        "wiki/review-backlog.md",
        "docs/codex-review/OPEN_RISKS.md",
        "docs/codex-review/QUALITY_GATES.md",
    )
    assert "claude-review/docs/v2026-05-31/README.md" in (
        review_authority_lint.HISTORICAL_REVIEW_ANCHORS
    )


def test_current_quality_gate_commands_include_evidence_boundary_lint_gate():
    assert 'python -m scripts.evidence_boundary_lint' in (
        quality_gate_counts.CURRENT_QUALITY_GATE_COMMANDS
    )
    assert quality_gate_counts.EVIDENCE_BOUNDARY_GATE_MODULES == (
        'scripts.evidence_boundary_lint',
    )


def test_current_quality_gate_commands_include_section_10_trace_gate():
    assert "python -m analysis.s10_failure_trace" in (
        quality_gate_counts.CURRENT_QUALITY_GATE_COMMANDS
    )
    assert "analysis.s10_failure_trace" in quality_gate_counts.ANALYSIS_SUITE_GATE_MODULES


def test_current_quality_gate_commands_match_executed_gate_modules():
    expected = (
        ("python -m pytest tests -q",)
        + tuple(
            f"python -m {module}"
            for module in quality_gate_counts.ANALYSIS_SUITE_GATE_MODULES
        )
        + tuple(
            f"python -m {module}"
            for module in quality_gate_counts.EVIDENCE_ARTIFACT_GATE_MODULES
        )
        + tuple(quality_gate_counts.BROWSER_EVIDENCE_GATE_COMMANDS)
        + tuple(
            f"python -m {module}"
            for module in quality_gate_counts.PACKAGE_SMOKE_GATE_MODULES
        )
        + tuple(
            f"python -m {module}"
            for module in quality_gate_counts.INTEGRATION_AUDIT_GATE_MODULES
        )
        + tuple(
            f"python -m {module}"
            for module in quality_gate_counts.REVIEW_AUTHORITY_GATE_MODULES
        )
        + tuple(
            f'python -m {module}'
            for module in quality_gate_counts.EVIDENCE_BOUNDARY_GATE_MODULES
        )
        + tuple(
            f"python -m {module}"
            for module in quality_gate_counts.DEMO_SMOKE_GATE_MODULES
        )
    )

    assert quality_gate_counts.CURRENT_QUALITY_GATE_COMMANDS == expected


def test_final_review_gate_commands_extend_executed_gates_with_self_sync_checks():
    assert quality_gate_counts.FINAL_REVIEW_GATE_COMMANDS == (
        *quality_gate_counts.CURRENT_QUALITY_GATE_COMMANDS,
        "python -u -m scripts.quality_gate_counts",
        "python -m scripts.quality_gate_counts --check --skip-expensive",
    )


def test_current_quality_gate_commands_are_derived_from_gate_modules():
    source = (Path(__file__).resolve().parents[1] / "scripts" / "quality_gate_counts.py").read_text(
        encoding="utf-8"
    )
    assignment = source.split("CURRENT_QUALITY_GATE_COMMANDS =", 1)[1].split(
        "QUALITY_GATE_COMMAND_DOCS =", 1
    )[0]

    assert "command_for_module" in assignment
    assert '"python -m analysis.run_all"' not in assignment
    assert '"python -m examples.demo_sre_loop"' not in assignment


def test_quality_gates_required_command_block_matches_current_command_set():
    quality_gates = (
        quality_gate_counts.REPO_ROOT
        / "docs"
        / "codex-review"
        / "QUALITY_GATES.md"
    )
    text = quality_gates.read_text(encoding="utf-8-sig")
    start = text.index("## Required Commands")
    fenced_start = text.index("```", start)
    fenced_end = text.index("```", fenced_start + 3)
    fenced_lines = [
        line.strip()
        for line in text[fenced_start + 3 : fenced_end].splitlines()
        if line.strip()
    ]
    if fenced_lines and fenced_lines[0] == "bash":
        fenced_lines = fenced_lines[1:]
    commands = tuple(fenced_lines)

    assert commands == tuple(_opus_packet_expected_review_commands())


def test_quality_gates_observed_result_block_is_not_canonical_command_source():
    quality_gates = (
        quality_gate_counts.REPO_ROOT
        / "docs"
        / "codex-review"
        / "QUALITY_GATES.md"
    )
    text = quality_gates.read_text(encoding="utf-8-sig")
    required_start = text.index("## Required Commands")
    observed_start = text.index("Current local result", required_start)

    assert "canonical command list" in text[required_start:observed_start]
    assert "observed local output" in text[observed_start:]
    assert "`-q`" in text[observed_start:]


def test_opus_first_read_surfaces_quality_gates_before_packet():
    readme = quality_gate_counts.REPO_ROOT / "docs" / "opus-review" / "README.md"
    text = readme.read_text(encoding="utf-8-sig")
    start = text.index("## First-Read Files")
    end = text.index("## Historical Inputs", start)
    first_read = text[start:end]

    quality_gates_index = first_read.index("../codex-review/QUALITY_GATES.md")
    packet_index = first_read.index("OPUS_REVIEW_PACKET.md")

    assert quality_gates_index < packet_index


def test_opus_readme_routes_git_scope_to_handoff_first_read():
    readme = quality_gate_counts.REPO_ROOT / "docs" / "opus-review" / "README.md"
    text = readme.read_text(encoding="utf-8-sig")
    start = text.index("## First-Read Files")
    end = text.index("## Historical Inputs", start)
    first_read = text[start:end]

    for phrase in [
        "Git Review Scope Snapshot",
        "git status --short --branch --untracked-files=all",
        "git ls-files --others --exclude-standard",
        "dirty/untracked",
    ]:
        assert phrase in first_read


def test_opus_handoff_runbook_surfaces_quality_gates_before_packet_commands():
    handoff = quality_gate_counts.REPO_ROOT / "docs" / "opus-review" / "HANDOFF.md"
    text = handoff.read_text(encoding="utf-8-sig")
    start = text.index("## Reviewer Runbook")
    end = text.index("## Handoff Sanity Checklist", start)
    runbook = text[start:end]

    quality_gates_index = runbook.index("docs/codex-review/QUALITY_GATES.md")
    packet_index = runbook.index("docs/opus-review/OPUS_REVIEW_PACKET.md")

    assert quality_gates_index < packet_index


def test_opus_handoff_documents_git_review_scope_snapshot():
    handoff = quality_gate_counts.REPO_ROOT / "docs" / "opus-review" / "HANDOFF.md"
    text = handoff.read_text(encoding="utf-8-sig")
    start = text.index("## Git Review Scope Snapshot")
    end = text.index("## Current Baseline", start)
    section = text[start:end]

    for phrase in [
        "git status --short --branch --untracked-files=all",
        "git log --oneline --decorate -5",
        "git log --reverse --oneline origin/spacex-session..HEAD",
        "git diff --name-status",
        "git ls-files --others --exclude-standard",
        "git diff --check",
        "spacex-session...origin/spacex-session [ahead 93]",
        "git log --reverse --oneline 5df8e0c..origin/spacex-session",
        "origin/spacex-session..HEAD may be empty after push",
        "tracked modified surface",
        "untracked files are intentional review scope",
        "analysis/evidence_consistency.py",
        "docs/superpowers/plans/README.md",
        "docs/superpowers/specs/README.md",
        "tests/test_control_center_browser_dom.py",
        "tests/test_evidence_report_manifest_shape.py",
        "tests/test_evidence_contract_boundary_report.py",
        "do not omit untracked split files",
        "line-ending warnings are not review blockers",
        "unexpected files outside these categories should be treated as review questions",
    ]:
        assert phrase in section
    assert "targeted tests such as\n  `tests/test_synthetic_evidence_boundaries.py` and\n  `tests/test_quality_gate_counts.py`" in section

    assert "Current untracked review-scope inventory:" in section
    for relative_path in CURRENT_UNTRACKED_REVIEW_SCOPE:
        assert f"- `{relative_path}`" in section


def test_opus_handoff_content_partitions_use_current_synchronized_count():
    handoff = quality_gate_counts.REPO_ROOT / "docs" / "opus-review" / "HANDOFF.md"
    text = handoff.read_text(encoding="utf-8-sig")
    current_count = _current_synchronized_count(text)
    start = text.index("## Content Partitions For Commit And Review")
    end = text.index("## Current Baseline", start)
    section = text[start:end]
    partition_counts = re.findall(r"`(\d+)` pytest count", section)

    assert partition_counts
    assert set(partition_counts) == {current_count}
    assert "`943` pytest count" not in section


def test_opus_handoff_untracked_inventory_matches_live_or_pre_submit_git_status():
    output = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=quality_gate_counts.REPO_ROOT,
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    current_untracked = tuple(line for line in output.splitlines() if line)

    if current_untracked:
        assert current_untracked == CURRENT_UNTRACKED_REVIEW_SCOPE
    else:
        handoff = quality_gate_counts.REPO_ROOT / "docs" / "opus-review" / "HANDOFF.md"
        text = handoff.read_text(encoding="utf-8-sig")
        assert "pre-commit inventory" in text
        for relative_path in CURRENT_UNTRACKED_REVIEW_SCOPE:
            assert f"- `{relative_path}`" in text


def test_opus_handoff_untracked_examples_are_currently_untracked():
    handoff = quality_gate_counts.REPO_ROOT / "docs" / "opus-review" / "HANDOFF.md"
    text = handoff.read_text(encoding="utf-8-sig")
    start = text.index("- The untracked files are intentional review scope")
    end = text.index("- For any merge or external packet export", start)
    section = text[start:end]
    documented_paths = tuple(
        match.group(1)
        for match in re.finditer(r"`([^`]+)`", section)
        if "/" in match.group(1)
    )

    assert documented_paths
    assert set(documented_paths).issubset(set(CURRENT_UNTRACKED_REVIEW_SCOPE))


def test_opus_handoff_tracked_examples_are_modified_or_pre_submit_examples():
    handoff = quality_gate_counts.REPO_ROOT / "docs" / "opus-review" / "HANDOFF.md"
    text = handoff.read_text(encoding="utf-8-sig")
    start = text.index("- The tracked modified surface spans")
    end = text.index("- The untracked files are intentional review scope", start)
    section = text[start:end]
    documented_paths = tuple(
        match.group(1)
        for match in re.finditer(r"`([^`]+)`", section)
        if "/" in match.group(1)
    )
    diff_output = subprocess.run(
        ["git", "diff", "--name-only"],
        cwd=quality_gate_counts.REPO_ROOT,
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    modified_paths = {line.strip() for line in diff_output.splitlines() if line.strip()}

    assert documented_paths
    documented_set = set(documented_paths)
    if documented_set.issubset(modified_paths):
        return

    assert "pre-submit local snapshot" in text
    assert "content-split commits" in text


def test_opus_handoff_git_status_commands_always_show_untracked_files():
    handoff = quality_gate_counts.REPO_ROOT / "docs" / "opus-review" / "HANDOFF.md"
    text = handoff.read_text(encoding="utf-8-sig")
    bad_mentions = [
        match.group(0)
        for match in re.finditer(r"git status --short --branch(?! --untracked-files=all)", text)
    ]

    assert bad_mentions == []


def test_opus_handoff_baseline_records_full_quality_gate_count_run():
    handoff = quality_gate_counts.REPO_ROOT / "docs" / "opus-review" / "HANDOFF.md"
    text = handoff.read_text(encoding="utf-8-sig")
    start = text.index("## Current Baseline")
    end = text.index("## Reviewer Runbook", start)
    baseline = text[start:end]
    current_count = _current_synchronized_count(baseline)

    full_gate_index = baseline.index("python -u -m scripts.quality_gate_counts")
    check_gate_index = baseline.index(
        "python -m scripts.quality_gate_counts --check --skip-expensive"
    )

    assert f"quality gate pytest count: {current_count}" in baseline
    assert full_gate_index < check_gate_index


def test_opus_handoff_review_focus_uses_live_ledger_order():
    handoff = quality_gate_counts.REPO_ROOT / "docs" / "opus-review" / "HANDOFF.md"
    text = handoff.read_text(encoding="utf-8-sig")
    start = text.index("## Review Focus")
    end = text.index("## Questions For Opus", start)
    focus = text[start:end]

    backlog_index = focus.index("wiki/review-backlog.md")
    risks_index = focus.index("OPEN_RISKS.md")
    gates_index = focus.index("QUALITY_GATES.md")
    packet_index = focus.index("OPUS_REVIEW_PACKET.md")

    assert backlog_index < risks_index < gates_index < packet_index


def test_review_authority_lint_requires_quality_gates_before_packet_history():
    root = quality_gate_counts.REPO_ROOT
    errors = review_authority_lint.check_authority_order(root)

    assert not errors
    for section in review_authority_lint.AUTHORITY_SECTIONS:
        assert "docs/codex-review/QUALITY_GATES.md" in section.required_current


def test_audit_backlog_verification_gate_block_includes_full_quality_gate_count_run():
    audit_backlog = (
        quality_gate_counts.REPO_ROOT
        / "docs"
        / "claude-development-audit"
        / "backlog.md"
    )
    text = audit_backlog.read_text(encoding="utf-8-sig")

    commands = _fenced_command_block_after(text, "## Current Verification Gates")

    assert commands == _opus_packet_expected_review_commands()


def test_review_backlog_final_gate_includes_full_quality_gate_count_run():
    backlog = quality_gate_counts.REPO_ROOT / "wiki" / "review-backlog.md"
    text = backlog.read_text(encoding="utf-8-sig")

    commands = _fenced_command_block_after(text, "## Final Gate For A New Implementation Pass")

    assert commands == _opus_packet_expected_review_commands()


def test_quality_gate_command_docs_include_development_audit_backlog():
    assert (
        "docs/claude-development-audit/backlog.md"
        in quality_gate_counts.QUALITY_GATE_COMMAND_DOCS
    )


def test_quality_gate_command_docs_include_live_review_ledgers():
    assert "wiki/review-backlog.md" in quality_gate_counts.QUALITY_GATE_COMMAND_DOCS
    assert "docs/opus-review/HANDOFF.md" in quality_gate_counts.QUALITY_GATE_COMMAND_DOCS


def test_quality_gate_command_docs_include_engineering_packet():
    assert (
        "docs/codex-review/ENGINEERING_PACKET.md"
        in quality_gate_counts.QUALITY_GATE_COMMAND_DOCS
    )


def test_engineering_packet_current_verification_block_matches_current_gate_commands():
    engineering_packet = (
        quality_gate_counts.REPO_ROOT
        / "docs"
        / "codex-review"
        / "ENGINEERING_PACKET.md"
    )
    text = engineering_packet.read_text(encoding="utf-8-sig")

    commands = _fenced_command_block_after(text, "## Current Verification")

    assert commands == _opus_packet_expected_review_commands()


def test_engineering_packet_entry_points_route_opus_to_live_handoff():
    engineering_packet = (
        quality_gate_counts.REPO_ROOT
        / "docs"
        / "codex-review"
        / "ENGINEERING_PACKET.md"
    )
    text = engineering_packet.read_text(encoding="utf-8-sig")
    start = text.index("## Entry Points")
    end = text.index("## Runtime Chain", start)
    section = text[start:end]

    assert "docs/opus-review/HANDOFF.md" in section
    assert "Current Opus first-read handoff" in section


def test_engineering_packet_routes_git_scope_to_opus_handoff():
    engineering_packet = (
        quality_gate_counts.REPO_ROOT
        / "docs"
        / "codex-review"
        / "ENGINEERING_PACKET.md"
    )
    text = engineering_packet.read_text(encoding="utf-8-sig")
    start = text.index("## Merge-Scope Checklist")
    end = text.index("## Resolved Review Items", start)
    section = text[start:end]

    for phrase in [
        "docs/opus-review/HANDOFF.md",
        "Git Review Scope Snapshot",
        "git status --short --branch --untracked-files=all",
        "git ls-files --others --exclude-standard",
        "exact current untracked inventory",
    ]:
        assert phrase in section


def test_control_center_handoff_verification_lists_split_browser_test_ownership():
    handoff = quality_gate_counts.REPO_ROOT / "docs" / "CONTROL_CENTER_HANDOFF.md"
    text = handoff.read_text(encoding="utf-8-sig")
    entry_start = text.index("## Entry Points")
    entry_end = text.index("## OpenDesign Integration", entry_start)
    entry_section = text[entry_start:entry_end]
    verification_commands = _fenced_command_block_after(
        text, "## Verification Before Handing Off"
    )
    verification_text = "\n".join(verification_commands)

    assert f"Regression tests: `{CONTROL_CENTER_HANDOFF_TEST_COMMAND}`" in entry_section
    assert CONTROL_CENTER_HANDOFF_TEST_COMMAND in verification_commands
    assert "python -m pytest tests/test_control_center.py -q" not in entry_section
    assert "python -m pytest tests/test_control_center_browser_smoke.py -q" not in verification_commands
    for test_file in CONTROL_CENTER_HANDOFF_TEST_FILES:
        assert test_file in entry_section
        assert test_file in verification_text


def test_live_review_backlog_has_no_stale_quality_gate_count():
    backlog = quality_gate_counts.REPO_ROOT / "wiki" / "review-backlog.md"
    text = backlog.read_text(encoding="utf-8-sig")

    assert "quality gate pytest count: 477" not in text
    assert "current `628` synchronized test count" not in text
    assert re.search(r"\bsynchronized \d+-count\b", text) is None


def test_live_count_sync_closure_prose_is_count_neutral():
    handoff = quality_gate_counts.REPO_ROOT / "docs" / "opus-review" / "HANDOFF.md"
    backlog = quality_gate_counts.REPO_ROOT / "wiki" / "review-backlog.md"
    handoff_text = handoff.read_text(encoding="utf-8-sig")
    backlog_text = backlog.read_text(encoding="utf-8-sig")

    assert re.search(r"\bsynchronized \d+-count\b", handoff_text) is None
    assert "current-count checks" in handoff_text
    assert "current-count docs" in backlog_text


def test_live_review_backlog_documents_quality_gates_authority_anchor():
    backlog = quality_gate_counts.REPO_ROOT / "wiki" / "review-backlog.md"
    text = backlog.read_text(encoding="utf-8-sig")
    start = text.index("### Opus Handoff / Gate Hardening")
    end = text.index("## Active Research Landing Candidates", start)
    section = text[start:end]
    normalized_section = " ".join(section.split())

    assert "docs/codex-review/QUALITY_GATES.md" in section
    assert "QUALITY_GATE_COMMAND_DOCS" in section
    assert "docs/codex-review/ENGINEERING_PACKET.md" in section
    assert "full Opus handoff rerun command block" in normalized_section
    for relative_path in [
        "docs/CODEX_HANDOFF.md",
        "docs/CODEX_REVIEW_REPORT.md",
        "docs/codex-review/CODEX_SUMMARY.md",
        "docs/codex-review/CLAUDE_DEEP_REVIEW.md",
        "docs/codex-review/CLAUDE_REFINED_SPEC.md",
        "docs/codex-review/CLAUDE_REVIEW_REQUEST.md",
        "docs/codex-review/ENGINEERING_PACKET.md",
        "docs/CONTROL_CENTER_HANDOFF.md",
        "docs/claude-development-audit/README.md",
    ]:
        assert relative_path in section
    assert "The same authority lint now also covers additional clickable handoff" in section
    assert "docs/CONTROL_CENTER_HANDOFF.md" in section.split(
        "The same boundary lint surface now includes", 1
    )[0]
    assert "current completion, risk, and command-gate anchors" in normalized_section
    assert "current risk, completion, and command-gate anchors" not in normalized_section
    assert "docs/superpowers/plans/README.md" in section
    assert "docs/superpowers/specs/README.md" in section
    assert "Superpowers plan/spec inventory" in normalized_section
    assert "Git Review Scope Snapshot" in section
    assert "docs/opus-review/README.md" in section
    assert "wiki/README.md" in section
    assert "git status --short --branch --untracked-files=all" in section
    assert "exact current untracked inventory" in section
    assert "300 s timeout budget" in section
    assert "minutes-level runtime variance" in section
    assert "current local full suite takes about 174 s" not in section
    assert "`python -m pytest tests` gate as a `~1 s` command" not in section


def test_wiki_recommended_entries_route_opus_to_git_scope_handoff():
    wiki = quality_gate_counts.REPO_ROOT / "wiki" / "README.md"
    text = wiki.read_text(encoding="utf-8-sig")
    start = text.index("## Current Recommended Entries")
    end = text.index("## Current Baseline", start)
    section = text[start:end]

    handoff_index = section.index("docs/opus-review/HANDOFF.md")
    returned_review_index = section.index("claude-review/docs/v2026-05-31/README.md")
    historical_index = section.index("claude-review/docs/v2026-05-28/README.md")

    assert handoff_index < returned_review_index
    assert handoff_index < historical_index
    for phrase in [
        "Git Review Scope Snapshot",
        "git status --short --branch --untracked-files=all",
        "dirty/untracked",
    ]:
        assert phrase in section


def test_wiki_baseline_does_not_call_historical_opus_packet_latest():
    wiki = quality_gate_counts.REPO_ROOT / "wiki" / "README.md"
    text = wiki.read_text(encoding="utf-8-sig")
    start = text.index("## Current Baseline")
    end = text.index("## Maintenance Rules", start)
    section = text[start:end]

    assert "docs/opus-review/HANDOFF.md" in section
    assert "current Opus handoff" in section
    assert "Historical Opus v2.1 review packet" in section
    assert "latest review packet is under\n  `claude-review/docs/v2026-05-28/`" not in section


def test_current_project_overview_routes_opus_to_live_authorities_not_historical_spec():
    root = quality_gate_counts.REPO_ROOT
    overview = root / "wiki" / "project-overview.md"
    refined_spec = root / "docs" / "codex-review" / "CLAUDE_REFINED_SPEC.md"

    overview_text = overview.read_text(encoding="utf-8-sig")
    refined_text = refined_spec.read_text(encoding="utf-8-sig")
    normalized_overview = " ".join(overview_text.split())
    normalized_refined = " ".join(refined_text.split())

    assert "wiki/review-backlog.md" in normalized_overview
    assert "docs/codex-review/OPEN_RISKS.md" in normalized_overview
    assert "docs/codex-review/QUALITY_GATES.md" in normalized_overview
    assert "CLAUDE_REFINED_SPEC.md) as the current implementation authority" not in normalized_overview

    assert "historical execution rationale" in normalized_refined
    assert "is not the live backlog" in normalized_refined
    assert (
        "`wiki/review-backlog.md`, `docs/codex-review/OPEN_RISKS.md`, and "
        "`docs/codex-review/QUALITY_GATES.md`"
    ) in normalized_refined


def test_v2_knowledge_base_routes_reviewers_to_current_opus_handoff():
    html = (
        quality_gate_counts.REPO_ROOT
        / "docs"
        / "V2_Knowledge"
        / "knowledge-base.html"
    )
    text = html.read_text(encoding="utf-8-sig")
    normalized = " ".join(text.split())

    for anchor in [
        "docs/opus-review/HANDOFF.md",
        "docs/codex-review/OPEN_RISKS.md",
        "wiki/review-backlog.md",
        "docs/codex-review/QUALITY_GATES.md",
    ]:
        assert anchor in normalized
    assert "docs/claude-review/README.md</code> 鏄竴瀵规帴鎵嬪寘" not in normalized
    assert "Acknowledged: docs/claude-review/README.md" not in normalized


def test_v2_knowledge_base_hero_handoff_points_to_opus_handoff():
    html = (
        quality_gate_counts.REPO_ROOT
        / "docs"
        / "V2_Knowledge"
        / "knowledge-base.html"
    )
    text = html.read_text(encoding="utf-8-sig")
    hero = text.split('<header class="hero">', 1)[1].split("</header>", 1)[0]

    assert "spacex/docs/opus-review/HANDOFF.md" in hero
    assert "spacex/docs/claude-review/" not in hero


def test_v2_knowledge_base_does_not_understate_full_pytest_runtime():
    html = (
        quality_gate_counts.REPO_ROOT
        / "docs"
        / "V2_Knowledge"
        / "knowledge-base.html"
    )
    text = html.read_text(encoding="utf-8-sig")
    pytest_row = next(
        line for line in text.splitlines() if "python -m pytest tests -q</code>" in line
    )

    assert "~1 s" not in pytest_row
    assert "300 s budget" in pytest_row


def test_current_public_section5_metric_docs_match_generated_evidence():
    root = quality_gate_counts.REPO_ROOT
    readme = (root / "README.md").read_text(encoding="utf-8-sig")
    requirements = (root / "PR-REQUIREMENTS.md").read_text(encoding="utf-8-sig")
    html = (
        root / "docs" / "V2_Knowledge" / "knowledge-base.html"
    ).read_text(encoding="utf-8-sig")
    section5 = html.split('<section id="s5">', 1)[1].split("</section>", 1)[0]

    for text in (readme, requirements, section5):
        assert "629.4" in text
        assert "9.374" in text
    for stale in ("481 m/s", "51 m/s", "481鈫?1", "481 鈫?51"):
        assert stale not in readme
        assert stale not in requirements
        assert stale not in section5


def test_legacy_codex_handoff_routes_reviewers_to_current_opus_handoff():
    handoff = quality_gate_counts.REPO_ROOT / "docs" / "CODEX_HANDOFF.md"
    text = handoff.read_text(encoding="utf-8-sig")
    normalized = " ".join(text.split())

    assert "Historical handoff from 2026-05-12" in normalized
    for anchor in [
        "docs/opus-review/HANDOFF.md",
        "wiki/review-backlog.md",
        "docs/codex-review/OPEN_RISKS.md",
        "docs/codex-review/QUALITY_GATES.md",
    ]:
        assert anchor in normalized
    assert "51 passed" not in normalized
    assert "10 studies finished" not in normalized
    assert "Acknowledged: docs/claude-review/README.md" not in normalized


@pytest.mark.parametrize(
    "relative_path",
    [
        "docs/CODEX_HANDOFF.md",
        "docs/CODEX_REVIEW_REPORT.md",
        "docs/CONTROL_CENTER_HANDOFF.md",
        "docs/claude-development-audit/README.md",
    ],
)
def test_secondary_handoff_entrypoints_route_git_scope_to_opus_handoff(
    relative_path: str,
) -> None:
    text = (quality_gate_counts.REPO_ROOT / relative_path).read_text(
        encoding="utf-8-sig"
    )
    normalized = " ".join(text.split())

    for phrase in [
        "docs/opus-review/HANDOFF.md",
        "Git Review Scope Snapshot",
        "git status --short --branch --untracked-files=all",
        "git ls-files --others --exclude-standard",
        "dirty/untracked",
    ]:
        assert phrase in normalized


def test_pr_requirements_marks_legacy_claude_acknowledgment_as_superseded():
    requirements = quality_gate_counts.REPO_ROOT / "PR-REQUIREMENTS.md"
    text = requirements.read_text(encoding="utf-8-sig")
    normalized = " ".join(text.split())

    assert "docs/opus-review/HANDOFF.md" in normalized
    assert "wiki/review-backlog.md" in normalized
    assert "旧 Claude acknowledgment 要求已废弃" in normalized
    assert "绗竴涓?commit message 鏈熬蹇呴』鍚?`Acknowledged: docs/claude-review/README.md`" not in normalized


def test_v1_knowledge_base_demotes_legacy_codex_handoff_as_historical():
    html = quality_gate_counts.REPO_ROOT / "docs" / "knowledge-base.html"
    text = html.read_text(encoding="utf-8-sig")
    normalized = " ".join(text.split())

    assert "docs/opus-review/HANDOFF.md" in normalized
    assert "wiki/review-backlog.md" in normalized
    assert "docs/codex-review/OPEN_RISKS.md" in normalized
    assert "docs/codex-review/QUALITY_GATES.md" in normalized
    assert "current thread status and next move" not in normalized
    assert "use as the live handoff" not in normalized


def test_codex_review_readme_labels_summary_as_current_handoff_context():
    root = quality_gate_counts.REPO_ROOT
    readme = root / "docs" / "codex-review" / "README.md"
    summary = root / "docs" / "codex-review" / "CODEX_SUMMARY.md"

    readme_text = readme.read_text(encoding="utf-8-sig")
    summary_text = summary.read_text(encoding="utf-8-sig")
    normalized_readme = " ".join(readme_text.split())
    normalized_summary = " ".join(summary_text.split())

    assert "CODEX_SUMMARY.md" in normalized_readme
    assert "current handoff posture" in normalized_summary
    assert "Current architecture/evidence summary" in normalized_readme
    assert "CODEX_SUMMARY.md`](./CODEX_SUMMARY.md) | Historical" not in normalized_readme


@pytest.mark.parametrize(
    "relative_path",
    [
        "docs/codex-review/README.md",
        "docs/codex-review/CODEX_SUMMARY.md",
        "wiki/README.md",
        "wiki/project-overview.md",
    ],
)
def test_current_overview_entrypoints_route_git_scope_to_opus_handoff(
    relative_path: str,
) -> None:
    text = (quality_gate_counts.REPO_ROOT / relative_path).read_text(
        encoding="utf-8-sig"
    )
    normalized = " ".join(text.split())

    for phrase in [
        "docs/opus-review/HANDOFF.md",
        "Git Review Scope Snapshot",
        "git status --short --branch --untracked-files=all",
        "git ls-files --others --exclude-standard",
        "dirty/untracked",
    ]:
        assert phrase in normalized


@pytest.mark.parametrize(
    "relative_path",
    [
        "docs/codex-review/CLAUDE_DEEP_REVIEW.md",
        "docs/codex-review/CLAUDE_REFINED_SPEC.md",
        "docs/codex-review/CLAUDE_REVIEW_REQUEST.md",
    ],
)
def test_historical_codex_review_entries_route_git_scope_to_opus_handoff(
    relative_path: str,
) -> None:
    text = (quality_gate_counts.REPO_ROOT / relative_path).read_text(
        encoding="utf-8-sig"
    )
    normalized = " ".join(text.split())

    for phrase in [
        "docs/opus-review/HANDOFF.md",
        "Git Review Scope Snapshot",
        "git status --short --branch --untracked-files=all",
        "git ls-files --others --exclude-standard",
        "dirty/untracked",
    ]:
        assert phrase in normalized


def test_codex_review_readme_contents_lists_live_ledgers_before_history():
    readme = (
        quality_gate_counts.REPO_ROOT
        / "docs"
        / "codex-review"
        / "README.md"
    )
    text = readme.read_text(encoding="utf-8-sig")
    start = text.index("## Contents")
    end = text.index("## Reading Order", start)
    contents = text[start:end]

    backlog_index = contents.index("../../wiki/README.md")
    risks_index = contents.index("OPEN_RISKS.md")
    gates_index = contents.index("QUALITY_GATES.md")
    historical_index = min(
        contents.index("CLAUDE_DEEP_REVIEW.md"),
        contents.index("CLAUDE_REFINED_SPEC.md"),
        contents.index("CLAUDE_REVIEW_REQUEST.md"),
        contents.index("../../claude-review/docs/v2026-05-31/README.md"),
        contents.index("../../claude-review/docs/v2026-05-28/README.md"),
        contents.index("../../claude-review/docs/v2026-05-26/README.md"),
    )

    assert backlog_index < risks_index < gates_index < historical_index


def test_require_quality_gate_commands_reports_missing_doc_path():
    complete_text = "\n".join(quality_gate_counts.FINAL_REVIEW_GATE_COMMANDS)
    missing_demo_text = complete_text.replace(
        "python -m examples.demo_catch_phase", ""
    )

    with pytest.raises(RuntimeError) as excinfo:
        quality_gate_counts.require_quality_gate_commands(
            [
                ("docs/ok.md", complete_text),
                ("docs/drifted.md", missing_demo_text),
            ]
        )

    message = str(excinfo.value)
    assert "docs/drifted.md" in message
    assert "python -m examples.demo_catch_phase" in message


def test_require_quality_gate_commands_rejects_manifest_report_order_drift():
    commands = _opus_packet_expected_review_commands()
    manifest_index = commands.index("python -m analysis.evidence_manifest")
    report_index = commands.index("python -m analysis.evidence_report")
    commands[manifest_index], commands[report_index] = (
        commands[report_index],
        commands[manifest_index],
    )

    with pytest.raises(RuntimeError) as excinfo:
        quality_gate_counts.require_quality_gate_commands(
            [("docs/drifted-order.md", "\n".join(commands))]
        )

    message = str(excinfo.value)
    assert "docs/drifted-order.md" in message
    assert "analysis.evidence_manifest" in message
    assert "analysis.evidence_report" in message
    assert "before" in message


def test_require_quality_gate_commands_rejects_quality_gate_check_order_drift():
    commands = _opus_packet_expected_review_commands()
    update_index = commands.index("python -u -m scripts.quality_gate_counts")
    check_index = commands.index(
        "python -m scripts.quality_gate_counts --check --skip-expensive"
    )
    commands[update_index], commands[check_index] = (
        commands[check_index],
        commands[update_index],
    )

    with pytest.raises(RuntimeError) as excinfo:
        quality_gate_counts.require_quality_gate_commands(
            [("docs/drifted-quality-check.md", "\n".join(commands))]
        )

    message = str(excinfo.value)
    assert "docs/drifted-quality-check.md" in message
    assert "python -u -m scripts.quality_gate_counts" in message
    assert "python -m scripts.quality_gate_counts --check --skip-expensive" in message
    assert "before" in message


def test_require_quality_gate_commands_rejects_full_sequence_order_drift():
    commands = _opus_packet_expected_review_commands()
    demo_index = commands.index("python -m examples.demo_sre_loop")
    update_index = commands.index("python -u -m scripts.quality_gate_counts")
    check_index = commands.index(
        "python -m scripts.quality_gate_counts --check --skip-expensive"
    )
    drifted_commands = (
        commands[:demo_index]
        + [commands[update_index], commands[check_index]]
        + commands[demo_index:update_index]
        + commands[check_index + 1 :]
    )

    with pytest.raises(RuntimeError) as excinfo:
        quality_gate_counts.require_quality_gate_commands(
            [("docs/drifted-full-sequence.md", "\n".join(drifted_commands))]
        )

    message = str(excinfo.value)
    assert "docs/drifted-full-sequence.md" in message
    assert "canonical quality gate command order" in message
    assert "python -u -m scripts.quality_gate_counts" in message


def test_require_quality_gate_commands_rejects_scattered_mentions_without_command_surface():
    scattered_text = "\n\n".join(
        f"Reviewer note {index}: `{command}` is discussed elsewhere."
        for index, command in enumerate(quality_gate_counts.FINAL_REVIEW_GATE_COMMANDS)
    )

    with pytest.raises(RuntimeError) as excinfo:
        quality_gate_counts.require_quality_gate_commands(
            [("docs/scattered-command-mentions.md", scattered_text)]
        )

    message = str(excinfo.value)
    assert "docs/scattered-command-mentions.md" in message
    assert "contiguous canonical quality gate command surface" in message


def test_require_quality_gate_commands_rejects_stale_nonquiet_pytest_gate():
    complete_text = "\n".join(quality_gate_counts.FINAL_REVIEW_GATE_COMMANDS)
    stale_text = complete_text + "\nlegacy: `python -m pytest tests`, parsed pass summary\n"

    with pytest.raises(RuntimeError) as excinfo:
        quality_gate_counts.require_quality_gate_commands(
            [("docs/stale-pytest.md", stale_text)]
        )

    message = str(excinfo.value)
    assert "docs/stale-pytest.md" in message
    assert "stale non-quiet pytest gate" in message
    assert "python -m pytest tests -q" in message


def test_require_quality_gate_commands_allows_collect_only_pytest_options():
    complete_text = "\n".join(quality_gate_counts.FINAL_REVIEW_GATE_COMMANDS)
    collect_only_text = (
        complete_text
        + "\nchecklist: `python -m pytest tests --collect-only -q` confirms count parity\n"
    )

    quality_gate_counts.require_quality_gate_commands(
        [("docs/collect-only.md", collect_only_text)]
    )


def test_demo_smoke_gate_modules_cover_current_demo_requirements():
    assert quality_gate_counts.DEMO_SMOKE_GATE_MODULES == (
        "examples.demo_sre_loop",
        "examples.demo_powered_descent",
        "examples.demo_catch_phase",
    )


def test_replace_once_requires_exactly_one_match():
    assert replace_once(
        "alpha 83 passed omega", r"\d+ passed", "85 passed", "unit"
    ) == ("alpha 85 passed omega")

    with pytest.raises(RuntimeError, match="missing unit"):
        replace_once("alpha", r"\d+ passed", "85 passed", "unit")

    with pytest.raises(RuntimeError, match="matched 2 times"):
        replace_once("83 passed and 84 passed", r"\d+ passed", "85 passed", "unit")


def test_collect_pytest_count_runs_tests_before_parsing_collection(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[list[str]] = []
    timeouts: list[int] = []
    encodings: list[str | None] = []
    error_handlers: list[str | None] = []
    smoke_dirs: list[Path] = []

    def fake_run(
        command: list[str], *args: object, **kwargs: object
    ) -> SimpleNamespace:
        calls.append(command)
        timeouts.append(kwargs["timeout"])
        encodings.append(kwargs.get("encoding"))
        error_handlers.append(kwargs.get("errors"))
        if "--collect-only" in command:
            return SimpleNamespace(
                returncode=0, stdout="tests/test_a.py: 90", stderr=""
            )
        return SimpleNamespace(
            returncode=0,
            stdout=(
                "........................................................................ [100%]\n"
            ),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(
        quality_gate_counts.package_smoke,
        "build_wheel_and_smoke_imports",
        lambda work_dir, repo_root: smoke_dirs.append(work_dir),
    )
    monkeypatch.setattr(
        quality_gate_counts.package_smoke,
        "verify_control_center_evidence_report",
        lambda report_path: CONTROL_CENTER_EVIDENCE_SUMMARY,
    )

    assert collect_pytest_count(Path("/repo")) == 90
    assert len(smoke_dirs) == 1
    assert calls == [
        [sys.executable, "-m", "pytest", "tests", "-q"],
        [sys.executable, "-m", "pytest", "tests", "--collect-only", "-q"],
    ]
    assert timeouts == [quality_gate_counts.PYTEST_TIMEOUT_SECONDS] * 2
    assert quality_gate_counts.PYTEST_TIMEOUT_SECONDS >= 300
    assert encodings == ["utf-8", "utf-8"]
    assert error_handlers == ["replace", "replace"]


def test_collect_pytest_count_validates_control_center_evidence_report(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[tuple[str, Path]] = []

    def fake_run(
        command: list[str], *args: object, **kwargs: object
    ) -> SimpleNamespace:
        if "--collect-only" in command:
            return SimpleNamespace(
                returncode=0, stdout="tests/test_a.py: 90", stderr=""
            )
        return SimpleNamespace(returncode=0, stdout="90 passed in 1.23s", stderr="")

    def fake_build(work_dir: Path, repo_root: Path) -> None:
        calls.append(("build", repo_root))

    def fake_verify(report_path: Path) -> str:
        calls.append(("verify", report_path))
        return CONTROL_CENTER_EVIDENCE_SUMMARY

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(
        quality_gate_counts.package_smoke,
        "build_wheel_and_smoke_imports",
        fake_build,
    )
    monkeypatch.setattr(
        quality_gate_counts.package_smoke,
        "verify_control_center_evidence_report",
        fake_verify,
    )

    repo_root = Path("/repo")

    assert collect_pytest_count(repo_root) == 90
    assert calls == [
        ("build", repo_root),
        (
            "verify",
            repo_root
            / "analysis"
            / "artifacts"
            / "control-center-browser-evidence-report.json",
        ),
    ]


def test_collect_pytest_count_rejects_control_center_evidence_without_frontend_error(
    monkeypatch: pytest.MonkeyPatch,
):
    def fake_run(
        command: list[str], *args: object, **kwargs: object
    ) -> SimpleNamespace:
        if "--collect-only" in command:
            return SimpleNamespace(
                returncode=0, stdout="tests/test_a.py: 90", stderr=""
            )
        return SimpleNamespace(returncode=0, stdout="90 passed in 1.23s", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(
        quality_gate_counts.package_smoke,
        "build_wheel_and_smoke_imports",
        lambda work_dir, repo_root: None,
    )
    monkeypatch.setattr(
        quality_gate_counts.package_smoke,
        "verify_control_center_evidence_report",
        lambda report_path: "control-center.v1 @ /api/control-center; desktop+mobile; error=desktop:1440x960:dom59890",
    )

    with pytest.raises(RuntimeError, match="frontend-error browser evidence"):
        collect_pytest_count(Path("/repo"))


def test_collect_pytest_count_rejects_control_center_evidence_without_backend_error(
    monkeypatch: pytest.MonkeyPatch,
):
    def fake_run(
        command: list[str], *args: object, **kwargs: object
    ) -> SimpleNamespace:
        if "--collect-only" in command:
            return SimpleNamespace(
                returncode=0, stdout="tests/test_a.py: 90", stderr=""
            )
        return SimpleNamespace(returncode=0, stdout="90 passed in 1.23s", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(
        quality_gate_counts.package_smoke,
        "build_wheel_and_smoke_imports",
        lambda work_dir, repo_root: None,
    )
    monkeypatch.setattr(
        quality_gate_counts.package_smoke,
        "verify_control_center_evidence_report",
        lambda report_path: (
            "control-center.v1 @ /api/control-center; desktop+mobile; "
            "frontend_error=desktop:1440x960:dom63261; "
            "contract_depth=top_level:11 object_groups:5 object_fields:21 "
            "array_item_groups:7 array_item_fields:36 timeline_fields:14"
        ),
    )

    with pytest.raises(RuntimeError, match="backend-error browser evidence"):
        collect_pytest_count(Path("/repo"))


def test_collect_pytest_count_rejects_control_center_evidence_without_contract_depth(
    monkeypatch: pytest.MonkeyPatch,
):
    def fake_run(
        command: list[str], *args: object, **kwargs: object
    ) -> SimpleNamespace:
        if "--collect-only" in command:
            return SimpleNamespace(
                returncode=0, stdout="tests/test_a.py: 90", stderr=""
            )
        return SimpleNamespace(returncode=0, stdout="90 passed in 1.23s", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(
        quality_gate_counts.package_smoke,
        "build_wheel_and_smoke_imports",
        lambda work_dir, repo_root: None,
    )
    monkeypatch.setattr(
        quality_gate_counts.package_smoke,
        "verify_control_center_evidence_report",
        lambda report_path: (
            "control-center.v1 @ /api/control-center; desktop+mobile; "
            "error=desktop:1440x960:dom59890; frontend_error=desktop:1440x960:dom63261; "
            "manifest_records=normal+backend_error+frontend_error; "
            "manifest_replay=normal+backend_error+frontend_error"
        ),
    )

    with pytest.raises(RuntimeError, match="contract-depth browser evidence"):
        collect_pytest_count(Path("/repo"))


def test_collect_pytest_count_rejects_control_center_evidence_without_full_contract_depth(
    monkeypatch: pytest.MonkeyPatch,
):
    def fake_run(
        command: list[str], *args: object, **kwargs: object
    ) -> SimpleNamespace:
        if "--collect-only" in command:
            return SimpleNamespace(
                returncode=0, stdout="tests/test_a.py: 90", stderr=""
            )
        return SimpleNamespace(returncode=0, stdout="90 passed in 1.23s", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(
        quality_gate_counts.package_smoke,
        "build_wheel_and_smoke_imports",
        lambda work_dir, repo_root: None,
    )
    monkeypatch.setattr(
        quality_gate_counts.package_smoke,
        "verify_control_center_evidence_report",
        lambda report_path: (
            "control-center.v1 @ /api/control-center; desktop+mobile; "
            "error=desktop:1440x960:dom59890; "
            "frontend_error=desktop:1440x960:dom63261; "
            "manifest_records=normal+backend_error+frontend_error; "
            "manifest_replay=normal+backend_error+frontend_error; "
            "contract_depth=top_level:11"
        ),
    )

    with pytest.raises(RuntimeError, match="contract-depth browser evidence"):
        collect_pytest_count(Path("/repo"))


def test_collect_pytest_count_rejects_control_center_evidence_without_manifest_replay(
    monkeypatch: pytest.MonkeyPatch,
):
    def fake_run(
        command: list[str], *args: object, **kwargs: object
    ) -> SimpleNamespace:
        if "--collect-only" in command:
            return SimpleNamespace(
                returncode=0, stdout="tests/test_a.py: 90", stderr=""
            )
        return SimpleNamespace(returncode=0, stdout="90 passed in 1.23s", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(
        quality_gate_counts.package_smoke,
        "build_wheel_and_smoke_imports",
        lambda work_dir, repo_root: None,
    )
    monkeypatch.setattr(
        quality_gate_counts.package_smoke,
        "verify_control_center_evidence_report",
        lambda report_path: (
            "control-center.v1 @ /api/control-center; desktop+mobile; "
            "error=desktop:1440x960:dom59890; frontend_error=desktop:1440x960:dom63261; "
            "manifest_records=normal+backend_error+frontend_error; "
            "contract_depth=top_level:11 object_groups:5 object_fields:21 "
            "array_item_groups:7 array_item_fields:36 timeline_fields:14"
        ),
    )

    with pytest.raises(RuntimeError, match="manifest replay evidence"):
        collect_pytest_count(Path("/repo"))


def test_collect_pytest_count_rejects_passed_collection_mismatch(
    monkeypatch: pytest.MonkeyPatch,
):
    def fake_run(
        command: list[str], *args: object, **kwargs: object
    ) -> SimpleNamespace:
        if "--collect-only" in command:
            return SimpleNamespace(
                returncode=0, stdout="tests/test_a.py: 90", stderr=""
            )
        return SimpleNamespace(
            returncode=0, stdout="89 passed, 1 skipped in 1.23s", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(
        quality_gate_counts.package_smoke,
        "build_wheel_and_smoke_imports",
        lambda work_dir, repo_root: None,
    )
    monkeypatch.setattr(
        quality_gate_counts.package_smoke,
        "verify_control_center_evidence_report",
        lambda report_path: CONTROL_CENTER_EVIDENCE_SUMMARY,
    )

    with pytest.raises(RuntimeError, match="89 passed, 90 collected"):
        collect_pytest_count(Path("/repo"))


def test_collect_pytest_count_fails_loudly_on_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch,
):
    def fake_run(*args: object, **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            returncode=1, stdout="89 passed, 1 failed", stderr="failure"
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="pytest quality gate failed"):
        collect_pytest_count(Path("/repo"))


def test_collect_pytest_count_fails_loudly_on_timeout(monkeypatch: pytest.MonkeyPatch):
    def fake_run(*args: object, **kwargs: object) -> SimpleNamespace:
        raise subprocess.TimeoutExpired(cmd=["pytest"], timeout=1)

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="pytest quality gate timed out"):
        collect_pytest_count(Path("/repo"))


def test_run_evidence_artifact_gates_runs_manifest_then_report(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[list[str]] = []
    encodings: list[str | None] = []
    error_handlers: list[str | None] = []

    def fake_run(command: list[str], *args: object, **kwargs: object) -> SimpleNamespace:
        calls.append(command)
        encodings.append(kwargs.get("encoding"))
        error_handlers.append(kwargs.get("errors"))
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    run_evidence_artifact_gates(Path("/repo"))

    assert calls == [
        [sys.executable, "-m", "analysis.evidence_manifest"],
        [sys.executable, "-m", "analysis.evidence_report"],
    ]
    assert encodings == ["utf-8", "utf-8"]
    assert error_handlers == ["replace", "replace"]


def test_run_integration_audit_gate_runs_control_center_audit(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[list[str]] = []

    def fake_run(command: list[str], *args: object, **kwargs: object) -> SimpleNamespace:
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    quality_gate_counts.run_integration_audit_gate(Path("/repo"))

    assert calls == [[sys.executable, "-m", "scripts.control_center_integration_audit"]]


def test_run_review_authority_gate_runs_review_authority_lint(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[list[str]] = []

    def fake_run(command: list[str], *args: object, **kwargs: object) -> SimpleNamespace:
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    quality_gate_counts.run_review_authority_gate(Path("/repo"))

    assert calls == [[sys.executable, "-m", "scripts.review_authority_lint"]]


def test_run_evidence_boundary_gate_runs_evidence_boundary_lint(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[list[str]] = []

    def fake_run(command: list[str], *args: object, **kwargs: object) -> SimpleNamespace:
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout='ok', stderr='')

    monkeypatch.setattr(subprocess, 'run', fake_run)

    quality_gate_counts.run_evidence_boundary_gate(Path('/repo'))

    assert calls == [[sys.executable, '-m', 'scripts.evidence_boundary_lint']]


def test_run_browser_evidence_gate_runs_report_manifest_command(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[list[str]] = []

    def fake_run(command: list[str], *args: object, **kwargs: object) -> SimpleNamespace:
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    quality_gate_counts.run_browser_evidence_gate(Path("/repo"))

    assert calls == [
        [
            sys.executable,
            "-m",
            "scripts.control_center_browser_smoke",
            "--report-manifests",
            "--report-json",
            "analysis/artifacts/control-center-browser-evidence-report.json",
        ]
    ]


def test_run_package_smoke_gate_runs_package_smoke_module(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[list[str]] = []

    def fake_run(command: list[str], *args: object, **kwargs: object) -> SimpleNamespace:
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    quality_gate_counts.run_package_smoke_gate(Path("/repo"))

    assert calls == [[sys.executable, "-m", "scripts.package_smoke"]]


def test_update_quality_gate_docs_runs_analysis_before_artifact_gates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    calls: list[str] = []

    monkeypatch.setattr(
        quality_gate_counts,
        "collect_pytest_count",
        lambda repo_root: calls.append("pytest") or 85,
    )
    monkeypatch.setattr(
        quality_gate_counts,
        "run_analysis_suite_gate",
        lambda repo_root: calls.append("analysis"),
    )
    monkeypatch.setattr(
        quality_gate_counts,
        "run_evidence_artifact_gates",
        lambda repo_root: calls.append("evidence"),
    )
    monkeypatch.setattr(
        quality_gate_counts,
        "run_browser_evidence_gate",
        lambda repo_root: calls.append("browser"),
    )
    monkeypatch.setattr(
        quality_gate_counts,
        "run_package_smoke_gate",
        lambda repo_root: calls.append("package"),
    )
    monkeypatch.setattr(
        quality_gate_counts,
        "run_integration_audit_gate",
        lambda repo_root: calls.append("audit"),
    )
    monkeypatch.setattr(
        quality_gate_counts,
        "run_review_authority_gate",
        lambda repo_root: calls.append("authority"),
    )
    monkeypatch.setattr(
        quality_gate_counts,
        "run_evidence_boundary_gate",
        lambda repo_root: calls.append("boundary"),
    )
    monkeypatch.setattr(
        quality_gate_counts,
        "run_demo_smoke_gate",
        lambda repo_root: calls.append("demo"),
    )

    _write_minimal_quality_gate_docs(tmp_path)

    update_quality_gate_docs(tmp_path)

    assert calls == [
        "browser",
        "pytest",
        "analysis",
        "evidence",
        "package",
        "audit",
        "authority",
        "boundary",
        "demo",
    ]


def test_run_evidence_artifact_gates_fails_loudly_on_report_error(
    monkeypatch: pytest.MonkeyPatch,
):
    def fake_run(command: list[str], *args: object, **kwargs: object) -> SimpleNamespace:
        if command[-1] == "analysis.evidence_report":
            return SimpleNamespace(
                returncode=1,
                stdout="artifact_identity_mismatch",
                stderr="",
            )
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="analysis.evidence_report failed"):
        run_evidence_artifact_gates(Path("/repo"))


def test_update_quality_gate_docs_runs_demo_smoke_after_artifact_gates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    calls: list[str] = []

    def fake_collect(repo_root: Path) -> int:
        calls.append("pytest")
        return 85

    def fake_artifact_gates(repo_root: Path) -> None:
        calls.append("evidence")

    def fake_analysis_gate(repo_root: Path) -> None:
        calls.append("analysis")

    def fake_demo_gate(repo_root: Path) -> None:
        calls.append("demo")

    def fake_browser_gate(repo_root: Path) -> None:
        calls.append("browser")

    def fake_package_gate(repo_root: Path) -> None:
        calls.append("package")

    def fake_audit_gate(repo_root: Path) -> None:
        calls.append("audit")

    def fake_authority_gate(repo_root: Path) -> None:
        calls.append("authority")

    def fake_boundary_gate(repo_root: Path) -> None:
        calls.append("boundary")

    monkeypatch.setattr(quality_gate_counts, "collect_pytest_count", fake_collect)
    monkeypatch.setattr(quality_gate_counts, "run_analysis_suite_gate", fake_analysis_gate)
    monkeypatch.setattr(
        quality_gate_counts, "run_evidence_artifact_gates", fake_artifact_gates
    )
    monkeypatch.setattr(quality_gate_counts, "run_browser_evidence_gate", fake_browser_gate)
    monkeypatch.setattr(quality_gate_counts, "run_package_smoke_gate", fake_package_gate)
    monkeypatch.setattr(quality_gate_counts, "run_integration_audit_gate", fake_audit_gate)
    monkeypatch.setattr(quality_gate_counts, "run_review_authority_gate", fake_authority_gate)
    monkeypatch.setattr(quality_gate_counts, "run_evidence_boundary_gate", fake_boundary_gate)
    monkeypatch.setattr(quality_gate_counts, "run_demo_smoke_gate", fake_demo_gate)

    _write_minimal_quality_gate_docs(tmp_path)

    update_quality_gate_docs(tmp_path)

    assert calls == [
        "browser",
        "pytest",
        "analysis",
        "evidence",
        "package",
        "audit",
        "authority",
        "boundary",
        "demo",
    ]


def test_update_quality_gate_docs_runs_evidence_gates_after_pytest_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    calls: list[str] = []

    def fake_collect(repo_root: Path) -> int:
        calls.append("pytest")
        return 85

    def fake_artifact_gates(repo_root: Path) -> None:
        calls.append("evidence")

    def fake_analysis_gate(repo_root: Path) -> None:
        calls.append("analysis")

    def fake_demo_gate(repo_root: Path) -> None:
        calls.append("demo")

    def fake_browser_gate(repo_root: Path) -> None:
        calls.append("browser")

    def fake_package_gate(repo_root: Path) -> None:
        calls.append("package")

    def fake_audit_gate(repo_root: Path) -> None:
        calls.append("audit")

    def fake_authority_gate(repo_root: Path) -> None:
        calls.append("authority")

    monkeypatch.setattr(quality_gate_counts, "collect_pytest_count", fake_collect)
    monkeypatch.setattr(quality_gate_counts, "run_analysis_suite_gate", fake_analysis_gate)
    monkeypatch.setattr(
        quality_gate_counts, "run_evidence_artifact_gates", fake_artifact_gates
    )
    monkeypatch.setattr(quality_gate_counts, "run_browser_evidence_gate", fake_browser_gate)
    monkeypatch.setattr(quality_gate_counts, "run_package_smoke_gate", fake_package_gate)
    monkeypatch.setattr(quality_gate_counts, "run_integration_audit_gate", fake_audit_gate)
    monkeypatch.setattr(quality_gate_counts, "run_review_authority_gate", fake_authority_gate)
    monkeypatch.setattr(
        quality_gate_counts,
        "run_evidence_boundary_gate",
        lambda repo_root: calls.append("boundary"),
    )
    monkeypatch.setattr(quality_gate_counts, "run_demo_smoke_gate", fake_demo_gate)

    pr = tmp_path / "PR-REQUIREMENTS.md"
    html = tmp_path / "docs" / "V2_Knowledge" / "knowledge-base.html"
    wiki_readme = tmp_path / "wiki" / "README.md"
    backlog = tmp_path / "wiki" / "review-backlog.md"
    evidence_ledger = tmp_path / "wiki" / "evidence-ledger.md"
    codex_summary = tmp_path / "docs" / "codex-review" / "CODEX_SUMMARY.md"
    codex_readme = tmp_path / "docs" / "codex-review" / "README.md"
    quality_gates = tmp_path / "docs" / "codex-review" / "QUALITY_GATES.md"
    engineering_packet = tmp_path / "docs" / "codex-review" / "ENGINEERING_PACKET.md"
    audit_backlog = tmp_path / "docs" / "claude-development-audit" / "backlog.md"
    opus_packet = tmp_path / "docs" / "opus-review" / "OPUS_REVIEW_PACKET.md"
    opus_handoff = tmp_path / "docs" / "opus-review" / "HANDOFF.md"
    html.parent.mkdir(parents=True)
    backlog.parent.mkdir(parents=True)
    codex_summary.parent.mkdir(parents=True)
    audit_backlog.parent.mkdir(parents=True)
    opus_packet.parent.mkdir(parents=True)
    pr.write_text(
        """
quality-gates:
  - python -m pytest tests -q       # 83 passed
  - python -m analysis.s10_failure_trace
  - python -m analysis.run_all
  - python -m analysis.evidence_manifest
  - python -m analysis.evidence_report
  - python -m scripts.control_center_browser_smoke --report-manifests --report-json analysis/artifacts/control-center-browser-evidence-report.json
  - python -m scripts.package_smoke
  - python -m scripts.control_center_integration_audit
  - python -m scripts.review_authority_lint
  - python -m scripts.evidence_boundary_lint
  - python -m examples.demo_sre_loop
  - python -m examples.demo_powered_descent
  - python -m examples.demo_catch_phase
  - python -u -m scripts.quality_gate_counts
  - python -m scripts.quality_gate_counts --check --skip-expensive

| 鍗曞厓娴嬭瘯 | `python -m pytest tests -q` | **83 passed** |
| 鍩哄噯璇佹嵁 | `python -m analysis.run_all` | All 12 studies finish |
| 浜嬩欢璇佹嵁 manifest | `python -m analysis.evidence_manifest` | exported |
| 浜嬩欢璇佹嵁鎶ュ憡 | `python -m analysis.evidence_report` | validates |
""".lstrip(),
        encoding="utf-8",
    )
    html.write_text(
        """
<div class="chip"><b>tests</b> 83 passed</div>
<tr><td><code>python -m pytest tests -q</code></td><td><b>83 passed</b></td><td>300 s budget</td></tr>
<tr><td><code>python -m analysis.s10_failure_trace</code></td><td>Section 10 trace artifacts exported</td><td>~1 s</td></tr>
<tr><td><code>python -m analysis.run_all</code></td><td>All 12 studies finished</td><td>~3 s</td></tr>
<tr><td><code>python -m analysis.evidence_manifest</code></td><td>S10/S11/S12 JSON/JSONL evidence + stack contract exported</td><td>~2 s</td></tr>
<tr><td><code>python -m analysis.evidence_report</code></td><td>Manifest-linked artifacts validate</td><td>&lt;1 s</td></tr>
<tr><td><code>python -m scripts.control_center_browser_smoke --report-manifests --report-json analysis/artifacts/control-center-browser-evidence-report.json</code></td><td>Control-center browser evidence report exported</td><td>&lt;1 s</td></tr>
<tr><td><code>python -m scripts.package_smoke</code></td><td>Package smoke validates evidence report</td><td>&lt;1 s</td></tr>
<tr><td><code>python -m scripts.control_center_integration_audit</code></td><td>Control-center integration audit exported</td><td>&lt;1 s</td></tr>
<tr><td><code>python -m scripts.review_authority_lint</code></td><td>Review authority order validates</td><td>&lt;1 s</td></tr>
<tr><td><code>python -m scripts.evidence_boundary_lint</code></td><td>Evidence boundary lint validates</td><td>&lt;1 s</td></tr>
<tr><td><code>python -m examples.demo_sre_loop</code></td><td>Demo trace prints</td><td>&lt;1 s</td></tr>
<tr><td><code>python -m examples.demo_powered_descent</code></td><td>PDG demo prints terminal state</td><td>&lt;1 s</td></tr>
<tr><td><code>python -m examples.demo_catch_phase</code></td><td>Catch demo prints lateral error</td><td>&lt;1 s</td></tr>
<tr><td><code>python -u -m scripts.quality_gate_counts</code></td><td>Quality-gate counts sync</td><td>300 s budget</td></tr>
<tr><td><code>python -m scripts.quality_gate_counts --check --skip-expensive</code></td><td>Quality-gate docs check</td><td>&lt;1 s</td></tr>
""".lstrip(),
        encoding="utf-8",
    )
    wiki_readme.write_text(
        "- Current verified local gates: `python -m pytest tests -q` passes with 83\n"
        "  tests; `python -m analysis.run_all` completes 12 studies.\n",
        encoding="utf-8",
    )
    backlog.write_text(
        "- Full test suite: `python -m pytest tests -q` passes with 83 tests\n"
        "- Fresh verification: `quality gate pytest count: 83`.\n"
        + _command_lines(),
        encoding="utf-8",
    )
    evidence_ledger.write_text(
        "python -m pytest tests -q      # 83 passed\n",
        encoding="utf-8",
    )
    codex_summary.write_text(
        "- `tests/`: current full suite passes with 83 tests.\n",
        encoding="utf-8",
    )
    codex_readme.write_text(
        "| Unit/integration tests | `83 passed` |\n",
        encoding="utf-8",
    )
    quality_gates.write_text(
        "python -m pytest tests -q\n83 passed\n"
        "quality gate pytest count: 83\n"
        + _command_lines(),
        encoding="utf-8",
    )
    engineering_packet.write_text(
        _engineering_packet_text(),
        encoding="utf-8",
    )
    audit_backlog.write_text(_command_lines(), encoding="utf-8")
    opus_packet.write_text(
        _command_lines()
        +
        "Current synchronized pytest count: `83`\n"
        +
        "quality gate pytest count: 83\n",
        encoding="utf-8",
    )
    opus_handoff.write_text(_count_and_command_lines(), encoding="utf-8")

    update_quality_gate_docs(tmp_path)

    assert calls == [
        "browser",
        "pytest",
        "analysis",
        "evidence",
        "package",
        "audit",
        "authority",
        "boundary",
        "demo",
    ]


def test_update_quality_gate_docs_refreshes_browser_report_before_count_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    calls: list[str] = []

    monkeypatch.setattr(
        quality_gate_counts,
        "run_browser_evidence_gate",
        lambda repo_root: calls.append("browser"),
    )
    monkeypatch.setattr(
        quality_gate_counts,
        "collect_pytest_count",
        lambda repo_root: calls.append("pytest") or 85,
    )
    monkeypatch.setattr(
        quality_gate_counts,
        "run_analysis_suite_gate",
        lambda repo_root: calls.append("analysis"),
    )
    monkeypatch.setattr(
        quality_gate_counts,
        "run_evidence_artifact_gates",
        lambda repo_root: calls.append("evidence"),
    )
    monkeypatch.setattr(
        quality_gate_counts,
        "run_package_smoke_gate",
        lambda repo_root: calls.append("package"),
    )
    monkeypatch.setattr(
        quality_gate_counts,
        "run_integration_audit_gate",
        lambda repo_root: calls.append("audit"),
    )
    monkeypatch.setattr(
        quality_gate_counts,
        "run_review_authority_gate",
        lambda repo_root: calls.append("authority"),
    )
    monkeypatch.setattr(
        quality_gate_counts,
        "run_evidence_boundary_gate",
        lambda repo_root: calls.append("boundary"),
    )
    monkeypatch.setattr(
        quality_gate_counts,
        "run_demo_smoke_gate",
        lambda repo_root: calls.append("demo"),
    )

    _write_minimal_quality_gate_docs(tmp_path)

    update_quality_gate_docs(tmp_path)

    assert calls.index("browser") < calls.index("pytest")


def test_check_quality_gate_docs_reports_drift_without_writing(tmp_path: Path):
    _write_minimal_quality_gate_docs(tmp_path)
    original_pr = (tmp_path / "PR-REQUIREMENTS.md").read_text(encoding="utf-8")

    with pytest.raises(RuntimeError, match="quality gate docs drift"):
        check_quality_gate_docs(tmp_path, count=85)

    assert (tmp_path / "PR-REQUIREMENTS.md").read_text(encoding="utf-8") == original_pr


def test_check_quality_gate_docs_accepts_current_docs_without_writing(tmp_path: Path):
    _write_minimal_quality_gate_docs(tmp_path)
    update_quality_gate_docs(tmp_path, count=85)
    original_pr = (tmp_path / "PR-REQUIREMENTS.md").read_text(encoding="utf-8")

    assert check_quality_gate_docs(tmp_path, count=85) == 85

    assert (tmp_path / "PR-REQUIREMENTS.md").read_text(encoding="utf-8") == original_pr


def test_check_quality_gate_docs_skip_expensive_only_checks_doc_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _write_minimal_quality_gate_docs(tmp_path)

    monkeypatch.setattr(
        quality_gate_counts,
        "collect_pytest_count",
        lambda repo_root: (_ for _ in ()).throw(AssertionError("pytest should not run")),
    )
    monkeypatch.setattr(
        quality_gate_counts,
        "run_browser_evidence_gate",
        lambda repo_root: (_ for _ in ()).throw(AssertionError("browser should not run")),
    )

    assert check_quality_gate_docs(tmp_path, skip_expensive=True) is None


def test_update_quality_gate_docs_updates_opus_handoff_full_gate_and_snippet_counts(
    tmp_path: Path,
):
    _write_minimal_quality_gate_docs(tmp_path)

    update_quality_gate_docs(tmp_path, count=85)

    opus_handoff = tmp_path / "docs" / "opus-review" / "HANDOFF.md"
    text = opus_handoff.read_text(encoding="utf-8")

    assert (
        "`python -u -m scripts.quality_gate_counts` reported "
        "`quality gate pytest count: 85`." in text
    )
    assert "\nquality gate pytest count: 85\n" in text
    assert text.count("quality gate pytest count: 85") == 2


def test_update_quality_gate_docs_updates_quality_gates_cli_count_snippet(
    tmp_path: Path,
):
    _write_minimal_quality_gate_docs(tmp_path)

    update_quality_gate_docs(tmp_path, count=85)

    quality_gates = tmp_path / "docs" / "codex-review" / "QUALITY_GATES.md"
    text = quality_gates.read_text(encoding="utf-8")

    assert "\nquality gate pytest count: 85\n" in text
    assert "\nquality gate pytest count: 83\n" not in text


def test_update_quality_gate_docs_updates_only_current_fields(tmp_path: Path):
    pr = tmp_path / "PR-REQUIREMENTS.md"
    html = tmp_path / "docs" / "V2_Knowledge" / "knowledge-base.html"
    wiki_readme = tmp_path / "wiki" / "README.md"
    backlog = tmp_path / "wiki" / "review-backlog.md"
    evidence_ledger = tmp_path / "wiki" / "evidence-ledger.md"
    codex_summary = tmp_path / "docs" / "codex-review" / "CODEX_SUMMARY.md"
    codex_readme = tmp_path / "docs" / "codex-review" / "README.md"
    quality_gates = tmp_path / "docs" / "codex-review" / "QUALITY_GATES.md"
    engineering_packet = tmp_path / "docs" / "codex-review" / "ENGINEERING_PACKET.md"
    audit_backlog = tmp_path / "docs" / "claude-development-audit" / "backlog.md"
    opus_packet = tmp_path / "docs" / "opus-review" / "OPUS_REVIEW_PACKET.md"
    opus_handoff = tmp_path / "docs" / "opus-review" / "HANDOFF.md"
    html.parent.mkdir(parents=True)
    backlog.parent.mkdir(parents=True)
    codex_summary.parent.mkdir(parents=True)
    audit_backlog.parent.mkdir(parents=True)
    opus_packet.parent.mkdir(parents=True)
    pr.write_text(
        """
quality-gates:
  - python -m pytest tests -q       # 83 passed
  - python -m analysis.s10_failure_trace
  - python -m analysis.run_all
  - python -m analysis.evidence_manifest
  - python -m analysis.evidence_report
  - python -m scripts.control_center_browser_smoke --report-manifests --report-json analysis/artifacts/control-center-browser-evidence-report.json
  - python -m scripts.package_smoke
  - python -m scripts.control_center_integration_audit
  - python -m scripts.review_authority_lint
  - python -m scripts.evidence_boundary_lint
  - python -m examples.demo_sre_loop
  - python -m examples.demo_powered_descent
  - python -m examples.demo_catch_phase
  - python -u -m scripts.quality_gate_counts
  - python -m scripts.quality_gate_counts --check --skip-expensive

| 鍗曞厓娴嬭瘯 | `python -m pytest tests -q` | **83 passed** |
| 鍩哄噯璇佹嵁 | `python -m analysis.run_all` | All 12 studies finish |
| 浜嬩欢璇佹嵁 manifest | `python -m analysis.evidence_manifest` | exported |
| 浜嬩欢璇佹嵁鎶ュ憡 | `python -m analysis.evidence_report` | validates |

historical snapshot: 51 passed
""".lstrip(),
        encoding="utf-8",
    )
    html.write_text(
        """
<div class="chip"><b>tests</b> 83 passed</div>
<tr><td><code>python -m pytest tests -q</code></td><td><b>83 passed</b></td><td>300 s budget</td></tr>
<tr><td><code>python -m analysis.s10_failure_trace</code></td><td>Section 10 trace artifacts exported</td><td>~1 s</td></tr>
<tr><td><code>python -m analysis.run_all</code></td><td>All 12 studies finished</td><td>~3 s</td></tr>
<tr><td><code>python -m analysis.evidence_manifest</code></td><td>S10/S11/S12 JSON/JSONL evidence + stack contract exported</td><td>~2 s</td></tr>
<tr><td><code>python -m analysis.evidence_report</code></td><td>Manifest-linked artifacts validate</td><td>&lt;1 s</td></tr>
<tr><td><code>python -m scripts.control_center_browser_smoke --report-manifests --report-json analysis/artifacts/control-center-browser-evidence-report.json</code></td><td>Control-center browser evidence report exported</td><td>&lt;1 s</td></tr>
<tr><td><code>python -m scripts.package_smoke</code></td><td>Package smoke validates evidence report</td><td>&lt;1 s</td></tr>
<tr><td><code>python -m scripts.control_center_integration_audit</code></td><td>Control-center integration audit exported</td><td>&lt;1 s</td></tr>
<tr><td><code>python -m scripts.review_authority_lint</code></td><td>Review authority order validates</td><td>&lt;1 s</td></tr>
<tr><td><code>python -m scripts.evidence_boundary_lint</code></td><td>Evidence boundary lint validates</td><td>&lt;1 s</td></tr>
<tr><td><code>python -m examples.demo_sre_loop</code></td><td>Demo trace prints</td><td>&lt;1 s</td></tr>
<tr><td><code>python -m examples.demo_powered_descent</code></td><td>PDG demo prints terminal state</td><td>&lt;1 s</td></tr>
<tr><td><code>python -m examples.demo_catch_phase</code></td><td>Catch demo prints lateral error</td><td>&lt;1 s</td></tr>
<tr><td><code>python -u -m scripts.quality_gate_counts</code></td><td>Quality-gate counts sync</td><td>300 s budget</td></tr>
<tr><td><code>python -m scripts.quality_gate_counts --check --skip-expensive</code></td><td>Quality-gate docs check</td><td>&lt;1 s</td></tr>
<p>historical snapshot: 51 passed</p>
""".lstrip(),
        encoding="utf-8",
    )
    backlog.write_text(
        """
## Current Verified Baseline

- Full test suite: `python -m pytest tests -q` passes with 83 tests in the
  current workspace.
- Fresh verification:
  `python -u -m scripts.quality_gate_counts` reports
  `quality gate pytest count: 83`; `python -m pytest tests -q` passes.
- Historical note: 51 tests in an older packet.
""".lstrip()
        + _command_lines(),
        encoding="utf-8",
    )
    wiki_readme.write_text(
        """
## Current Baseline

- Current verified local gates: `python -m pytest tests -q` passes with 83
  tests; `python -m analysis.run_all` completes 12 studies.
- Historical note: 51 tests in an older packet.
""".lstrip(),
        encoding="utf-8",
    )
    codex_summary.write_text(
        """
## Current State

- `tests/`: current full suite passes with 83 tests.
- Historical note: 51 tests in an older packet.
""".lstrip(),
        encoding="utf-8",
    )
    evidence_ledger.write_text(
        "python -m pytest tests -q      # 83 passed\n"
        "historical snapshot: 51 passed\n",
        encoding="utf-8",
    )
    codex_readme.write_text(
        "| Unit/integration tests | `83 passed` |\n"
        "| Historical | `51 passed` |\n",
        encoding="utf-8",
    )
    quality_gates.write_text(
        "python -m pytest tests -q\n83 passed\n"
        "quality gate pytest count: 83\n"
        + _command_lines()
        + "\n"
        "historical snapshot: 51 passed\n",
        encoding="utf-8",
    )
    engineering_packet.write_text(
        _engineering_packet_text()
        +
        "historical snapshot: 51 passed\n",
        encoding="utf-8",
    )
    audit_backlog.write_text(
        _command_lines() + "historical snapshot: 51 passed\n", encoding="utf-8"
    )
    opus_packet.write_text(
        _command_lines()
        +
        "Current synchronized pytest count: `83`\n"
        "quality gate pytest count: 83\n"
        "historical snapshot: 51 passed\n",
        encoding="utf-8",
    )
    opus_handoff.write_text(
        _count_and_command_lines()
        +
        "historical snapshot: 51 passed\n",
        encoding="utf-8",
    )

    update_quality_gate_docs(tmp_path, 85)

    pr_text = pr.read_text(encoding="utf-8")
    html_text = html.read_text(encoding="utf-8")
    backlog_text = backlog.read_text(encoding="utf-8")
    wiki_readme_text = wiki_readme.read_text(encoding="utf-8")
    codex_summary_text = codex_summary.read_text(encoding="utf-8")
    evidence_ledger_text = evidence_ledger.read_text(encoding="utf-8")
    codex_readme_text = codex_readme.read_text(encoding="utf-8")
    quality_gates_text = quality_gates.read_text(encoding="utf-8")
    engineering_packet_text = engineering_packet.read_text(encoding="utf-8")
    opus_packet_text = opus_packet.read_text(encoding="utf-8")
    opus_handoff_text = opus_handoff.read_text(encoding="utf-8")
    assert "# 85 passed" in pr_text
    assert "**85 passed**" in pr_text
    assert "historical snapshot: 51 passed" in pr_text
    assert '<div class="chip"><b>tests</b> 85 passed</div>' in html_text
    assert "<td><b>85 passed</b></td>" in html_text
    assert "historical snapshot: 51 passed" in html_text
    assert "passes with 85 tests" in backlog_text
    assert "quality gate pytest count: 85" in backlog_text
    assert "Historical note: 51 tests" in backlog_text
    assert "passes with 85\n  tests" in wiki_readme_text
    assert "Historical note: 51 tests" in wiki_readme_text
    assert "passes with 85 tests" in codex_summary_text
    assert "Historical note: 51 tests" in codex_summary_text
    assert "# 85 passed" in evidence_ledger_text
    assert "historical snapshot: 51 passed" in evidence_ledger_text
    assert "| Unit/integration tests | `85 passed` |" in codex_readme_text
    assert "| Historical | `51 passed` |" in codex_readme_text
    assert "python -m pytest tests -q\n85 passed" in quality_gates_text
    assert "historical snapshot: 51 passed" in quality_gates_text
    assert "Current synchronized pytest count: `85`" in engineering_packet_text
    assert "historical snapshot: 51 passed" in engineering_packet_text
    assert "quality gate pytest count: 85" in opus_packet_text
    assert "Current synchronized pytest count: `85`" in opus_packet_text
    assert "historical snapshot: 51 passed" in opus_packet_text
    assert "quality gate pytest count: 85" in opus_handoff_text
    assert "Current synchronized pytest count: `85`" in opus_handoff_text
    assert "still totals 85 collected tests" in opus_handoff_text
    assert "historical snapshot: 51 passed" in opus_handoff_text


def test_update_quality_gate_docs_does_not_partially_write_on_replacement_failure(
    tmp_path: Path,
):
    pr = tmp_path / "PR-REQUIREMENTS.md"
    html = tmp_path / "docs" / "V2_Knowledge" / "knowledge-base.html"
    wiki_readme = tmp_path / "wiki" / "README.md"
    backlog = tmp_path / "wiki" / "review-backlog.md"
    evidence_ledger = tmp_path / "wiki" / "evidence-ledger.md"
    codex_summary = tmp_path / "docs" / "codex-review" / "CODEX_SUMMARY.md"
    codex_readme = tmp_path / "docs" / "codex-review" / "README.md"
    quality_gates = tmp_path / "docs" / "codex-review" / "QUALITY_GATES.md"
    engineering_packet = tmp_path / "docs" / "codex-review" / "ENGINEERING_PACKET.md"
    audit_backlog = tmp_path / "docs" / "claude-development-audit" / "backlog.md"
    opus_packet = tmp_path / "docs" / "opus-review" / "OPUS_REVIEW_PACKET.md"
    opus_handoff = tmp_path / "docs" / "opus-review" / "HANDOFF.md"
    html.parent.mkdir(parents=True)
    backlog.parent.mkdir(parents=True)
    codex_summary.parent.mkdir(parents=True)
    audit_backlog.parent.mkdir(parents=True)
    opus_packet.parent.mkdir(parents=True)
    original_pr = """
quality-gates:
  - python -m pytest tests -q       # 83 passed
  - python -m analysis.s10_failure_trace
  - python -m analysis.run_all
  - python -m analysis.evidence_manifest
  - python -m analysis.evidence_report
  - python -m scripts.control_center_browser_smoke --report-manifests --report-json analysis/artifacts/control-center-browser-evidence-report.json
  - python -m scripts.package_smoke
  - python -m scripts.control_center_integration_audit
  - python -m scripts.review_authority_lint
  - python -m scripts.evidence_boundary_lint
  - python -m examples.demo_sre_loop
  - python -m examples.demo_powered_descent
  - python -m examples.demo_catch_phase
  - python -u -m scripts.quality_gate_counts
  - python -m scripts.quality_gate_counts --check --skip-expensive
  - python -u -m scripts.quality_gate_counts
  - python -m scripts.quality_gate_counts --check --skip-expensive

| 鍗曞厓娴嬭瘯 | `python -m pytest tests -q` | **83 passed** |
| 鍩哄噯璇佹嵁 | `python -m analysis.run_all` | All 12 studies finish |
| 浜嬩欢璇佹嵁 manifest | `python -m analysis.evidence_manifest` | exported |
| 浜嬩欢璇佹嵁鎶ュ憡 | `python -m analysis.evidence_report` | validates |
""".lstrip()
    pr.write_text(original_pr, encoding="utf-8")
    html.write_text(
        "<p>missing current quality gate fields</p>\n"
        "python -m pytest tests -q\n"
        "python -m analysis.s10_failure_trace\n"
        "python -m analysis.run_all\n"
        "python -m analysis.evidence_manifest\n"
        "python -m analysis.evidence_report\n"
        "python -m scripts.control_center_browser_smoke --report-manifests --report-json analysis/artifacts/control-center-browser-evidence-report.json\n"
        "python -m scripts.package_smoke\n"
        "python -m scripts.control_center_integration_audit\n"
        "python -m scripts.review_authority_lint\n"
        "python -m scripts.evidence_boundary_lint\n"
        "python -m examples.demo_sre_loop\n"
        "python -m examples.demo_powered_descent\n"
        "python -m examples.demo_catch_phase\n"
        "python -u -m scripts.quality_gate_counts\n"
        "python -m scripts.quality_gate_counts --check --skip-expensive\n",
        encoding="utf-8",
    )
    backlog.write_text(
        "- Full test suite: `python -m pytest tests -q` passes with 83 tests\n"
        + _command_lines(),
        encoding="utf-8",
    )
    wiki_readme.write_text(
        "- Current verified local gates: `python -m pytest tests -q` passes with 83\n"
        "  tests; `python -m analysis.run_all` completes 12 studies.\n",
        encoding="utf-8",
    )
    codex_summary.write_text(
        "- `tests/`: current full suite passes with 83 tests.\n",
        encoding="utf-8",
    )
    evidence_ledger.write_text(
        "python -m pytest tests -q      # 83 passed\n",
        encoding="utf-8",
    )
    codex_readme.write_text(
        "| Unit/integration tests | `83 passed` |\n",
        encoding="utf-8",
    )
    quality_gates.write_text(
        "python -m pytest tests -q\n83 passed\n"
        "quality gate pytest count: 83\n"
        + _command_lines(),
        encoding="utf-8",
    )
    engineering_packet.write_text(
        _engineering_packet_text(),
        encoding="utf-8",
    )
    audit_backlog.write_text(_command_lines(), encoding="utf-8")
    opus_packet.write_text(
        _command_lines()
        +
        "Current synchronized pytest count: `83`\n"
        +
        "quality gate pytest count: 83\n",
        encoding="utf-8",
    )
    opus_handoff.write_text(_count_and_command_lines(), encoding="utf-8")

    with pytest.raises(RuntimeError) as excinfo:
        update_quality_gate_docs(tmp_path, 85)

    message = str(excinfo.value)
    assert "docs/V2_Knowledge/knowledge-base.html" in message
    assert "V2 tests chip" in message
    assert pr.read_text(encoding="utf-8") == original_pr


def test_update_quality_gate_docs_requires_manifest_report_gates(tmp_path: Path):
    pr = tmp_path / "PR-REQUIREMENTS.md"
    html = tmp_path / "docs" / "V2_Knowledge" / "knowledge-base.html"
    quality_gates = tmp_path / "docs" / "codex-review" / "QUALITY_GATES.md"
    engineering_packet = tmp_path / "docs" / "codex-review" / "ENGINEERING_PACKET.md"
    review_backlog = tmp_path / "wiki" / "review-backlog.md"
    audit_backlog = tmp_path / "docs" / "claude-development-audit" / "backlog.md"
    opus_packet = tmp_path / "docs" / "opus-review" / "OPUS_REVIEW_PACKET.md"
    opus_handoff = tmp_path / "docs" / "opus-review" / "HANDOFF.md"
    html.parent.mkdir(parents=True)
    review_backlog.parent.mkdir(parents=True)
    quality_gates.parent.mkdir(parents=True)
    audit_backlog.parent.mkdir(parents=True)
    opus_packet.parent.mkdir(parents=True)
    pr.write_text(
        """
quality-gates:
  - python -m pytest tests -q       # 83 passed
  - python -m analysis.s10_failure_trace
  - python -m analysis.run_all
  - python -m analysis.evidence_manifest

| 鍗曞厓娴嬭瘯 | `python -m pytest tests -q` | **83 passed** |
| 鍩哄噯璇佹嵁 | `python -m analysis.run_all` | All 12 studies finish |
| 浜嬩欢璇佹嵁 manifest | `python -m analysis.evidence_manifest` | exported |
""".lstrip(),
        encoding="utf-8",
    )
    html.write_text(
        """
<div class="chip"><b>tests</b> 83 passed</div>
<tr><td><code>python -m pytest tests -q</code></td><td><b>83 passed</b></td><td>300 s budget</td></tr>
<tr><td><code>python -m analysis.s10_failure_trace</code></td><td>Section 10 trace artifacts exported</td><td>~1 s</td></tr>
<tr><td><code>python -m analysis.run_all</code></td><td>All 12 studies finished</td><td>~3 s</td></tr>
<tr><td><code>python -m analysis.evidence_manifest</code></td><td>S10/S11/S12 JSON/JSONL evidence + stack contract exported</td><td>~2 s</td></tr>
""".lstrip(),
        encoding="utf-8",
    )
    quality_gates.write_text(
        "python -m pytest tests -q\n"
        "python -m analysis.s10_failure_trace\n"
        "python -m analysis.run_all\n"
        "python -m analysis.evidence_manifest\n"
        "python -m analysis.evidence_report\n"
        "python -m scripts.control_center_integration_audit\n"
        "python -m examples.demo_sre_loop\n"
        "python -m examples.demo_powered_descent\n"
        "python -m examples.demo_catch_phase\n"
        "python -m pytest tests -q\n83 passed\n"
        "quality gate pytest count: 83\n",
        encoding="utf-8",
    )
    engineering_packet.write_text(_engineering_packet_text(), encoding="utf-8")
    audit_backlog.write_text(
        _command_lines(),
        encoding="utf-8",
    )
    opus_packet.write_text(
        _command_lines()
        +
        "Current synchronized pytest count: `83`\n"
        +
        "quality gate pytest count: 83\n",
        encoding="utf-8",
    )
    opus_handoff.write_text(_count_and_command_lines(), encoding="utf-8")
    review_backlog.write_text(
        "- Full test suite: `python -m pytest tests -q` passes with 83 tests\n"
        + _command_lines(),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="missing quality gate command: python -m analysis.evidence_report"):
        update_quality_gate_docs(tmp_path, 85)


def test_current_quality_gates_document_offline_package_smoke_build():
    quality_gates = (
        quality_gate_counts.REPO_ROOT
        / "docs"
        / "codex-review"
        / "QUALITY_GATES.md"
    )
    text = quality_gates.read_text(encoding="utf-8-sig")

    assert "--no-build-isolation" in text
    assert "--no-index" in text
    assert "PIP_DISABLE_PIP_VERSION_CHECK" in text
    assert "PIP_USE_DEPRECATED=legacy-certs" in text


def test_current_quality_gates_document_includes_control_center_browser_evidence_gate():
    quality_gates = (
        quality_gate_counts.REPO_ROOT
        / "docs"
        / "codex-review"
        / "QUALITY_GATES.md"
    )
    text = quality_gates.read_text(encoding="utf-8-sig")

    report_command = (
        "python -m scripts.control_center_browser_smoke --report-manifests "
        "--report-json analysis/artifacts/control-center-browser-evidence-report.json"
    )
    package_command = "python -m scripts.package_smoke"
    audit_command = "python -m scripts.control_center_integration_audit"

    assert report_command in text
    assert package_command in text
    assert audit_command in text
    assert text.index(report_command) < text.index(package_command)
    assert text.index(package_command) < text.index(audit_command)
    assert "control-center evidence report" in text
    assert "control-center-integration-audit.json" in text
    assert "manifest_paths" in text
    assert "manifest_records" in text
    assert "manifest_paths=" in text
    assert "manifest_records=" in text
    assert "manifest_replay=normal+backend_error+frontend_error" in text
    assert "manifest_records=normal+backend_error+frontend_error" in text
    assert "manifest_replay=normal+backend_error+frontend_error" in text
    assert "verify_evidence_manifest" in text
    assert "verify_error_evidence_manifest" in text
    assert "verify_frontend_error_evidence_manifest" in text
    assert "frontend_error" in text
    assert "contract_depth" in text
    assert "top_level" in text
    assert "object_groups" in text
    assert "array_item_fields" in text
    assert "timeline_fields" in text


def test_current_quality_gates_document_extracted_evidence_validator_gates():
    quality_gates = (
        quality_gate_counts.REPO_ROOT
        / "docs"
        / "codex-review"
        / "QUALITY_GATES.md"
    )
    text = quality_gates.read_text(encoding="utf-8-sig")

    for test_file in [
        "tests/test_evidence_artifacts.py",
        "tests/test_evidence_manifest_checks.py",
        "tests/test_evidence_consistency.py",
        "tests/test_evidence_contracts.py",
        "tests/test_evidence_contract_report.py",
        "tests/test_evidence_contract_fallback_report.py",
        "tests/test_evidence_contract_trace_report.py",
        "tests/test_evidence_contract_boundary_report.py",
    ]:
        assert test_file in text


def test_engineering_packet_documents_current_merge_scope_categories():
    engineering_packet = (
        quality_gate_counts.REPO_ROOT
        / "docs"
        / "codex-review"
        / "ENGINEERING_PACKET.md"
    )
    text = engineering_packet.read_text(encoding="utf-8-sig")

    assert "Merge-Scope Checklist" in text
    for target in QUALITY_GATE_TARGETS:
        assert target.relative_path in text
    for relative_path in quality_gate_counts.QUALITY_GATE_COMMAND_DOCS:
        assert relative_path in text
    for path in [
        "analysis/evidence_artifacts.py",
        "analysis/evidence_manifest_checks.py",
        "analysis/evidence_consistency.py",
        "analysis/evidence_contracts.py",
        "analysis/evidence_manifest.py",
        "analysis/evidence_report.py",
        "analysis/s11_catch_sre_wrapper.py",
        "analysis/s12_sre_replay.py",
        "scripts/control_center_browser_smoke.py",
        "scripts/control_center_integration_audit.py",
        "scripts/evidence_boundary_lint.py",
        "scripts/quality_gate_counts.py",
        "scripts/review_authority_lint.py",
        "sre_control/catch_adapter.py",
        "sre_control/stack_contract.py",
        "tests/test_evidence_artifacts.py",
        "tests/test_evidence_manifest_checks.py",
        "tests/test_evidence_consistency.py",
        "tests/test_evidence_contracts.py",
        "tests/test_evidence_manifest_generation.py",
        "tests/test_evidence_manifest.py",
        "tests/test_evidence_report_manifest_shape.py",
        "tests/test_evidence_report_study_shape.py",
        "tests/test_evidence_report_contract_shape.py",
        "tests/test_evidence_report_artifact_paths.py",
        "tests/test_evidence_contract_report.py",
        "tests/test_evidence_contract_fallback_report.py",
        "tests/test_evidence_contract_trace_report.py",
        "tests/test_evidence_contract_boundary_report.py",
        "tests/test_evidence_trace_report.py",
        "tests/test_evidence_wrapper_report.py",
        "tests/test_evidence_replay_report.py",
        "tests/test_evidence_replay_consistency_report.py",
        "tests/test_evidence_replay_artifacts_report.py",
        "tests/test_quality_gate_counts.py",
        "tests/test_control_center_browser_dom.py",
        "tests/test_control_center_browser_smoke.py",
        "tests/test_control_center_browser_manifest.py",
        "tests/test_control_center_browser_error_manifest.py",
        "tests/test_control_center_browser_report.py",
        "tests/test_control_center_integration_audit.py",
        "docs/CONTROL_CENTER_HANDOFF.md",
        "docs/EVENT_EVIDENCE_MANIFEST.md",
        "docs/STACK_DATA_CONTRACT.md",
        "docs/opus-review/HANDOFF.md",
        "docs/superpowers/plans/README.md",
        "docs/superpowers/specs/README.md",
    ]:
        assert path in text
    for artifact in [
        "analysis/artifacts/event_evidence_manifest.json",
        "analysis/artifacts/control-center-browser-evidence-report.json",
        "analysis/artifacts/control-center-integration-audit.json",
    ]:
        assert artifact in text
    assert "local inspection/cache artifacts" in text
    assert "control-center-review.png" in text
    assert "Superpowers plan/spec inventories" in text
    assert "docs/superpowers/plans/README.md" in text
    assert "docs/superpowers/specs/README.md" in text
    assert "every dated plan or spec artifact" in text


def test_opus_packet_targeted_evidence_commands_include_split_report_tests():
    opus_packet = (
        quality_gate_counts.REPO_ROOT
        / "docs"
        / "opus-review"
        / "OPUS_REVIEW_PACKET.md"
    )
    text = opus_packet.read_text(encoding="utf-8-sig")
    start = text.index("Targeted evidence commands:")
    end = text.index("Manifest sanity outputs", start)
    command_block = text[start:end]

    for test_file in [
        "tests/test_evidence_manifest.py",
        "tests/test_evidence_artifacts.py",
        "tests/test_evidence_manifest_checks.py",
        "tests/test_evidence_consistency.py",
        "tests/test_evidence_contracts.py",
        "tests/test_evidence_manifest_generation.py",
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
        "tests/test_control_center_browser_dom.py",
        "tests/test_control_center_browser_smoke.py",
        "tests/test_control_center_browser_manifest.py",
        "tests/test_control_center_browser_error_manifest.py",
        "tests/test_control_center_browser_report.py",
        "tests/test_control_center_integration_audit.py",
        "tests/test_quality_gate_counts.py",
    ]:
        assert test_file in command_block

    handoff = (
        quality_gate_counts.REPO_ROOT
        / "docs"
        / "opus-review"
        / "HANDOFF.md"
    )
    handoff_text = handoff.read_text(encoding="utf-8-sig")

    current_count = _current_synchronized_count(handoff_text)
    assert "## Reviewer Runbook" in handoff_text
    assert "## Handoff Sanity Checklist" in handoff_text
    assert "## Questions For Opus" in handoff_text
    assert _fenced_command_block_after(handoff_text, "## Recommended Re-Run Commands") == _opus_packet_expected_review_commands()
    for phrase in [
        "First 15 minutes",
        "Evidence replay",
        "Risk decision",
        "scripts/quality_gate_counts.py",
        "tests/test_quality_gate_counts.py",
        "Fresh `git status --short --branch --untracked-files=all`",
        "Do not promote synthetic scenario evidence to production proof",
        "Are any current `docs/codex-review/OPEN_RISKS.md` items blockers",
        "Does the evidence-report split preserve",
        "normal,\n   backend-error, and frontend-contract-error replay paths",
    ]:
        assert phrase in handoff_text

    opus_packet = (
        quality_gate_counts.REPO_ROOT
        / "docs"
        / "opus-review"
        / "OPUS_REVIEW_PACKET.md"
    )
    text = opus_packet.read_text(encoding="utf-8-sig")
    lead = "\n".join(text.splitlines()[:12])

    assert "Current Opus re-entry packet" in lead
    assert "was submitted for Opus v2.0 re-review" not in lead
    assert "## 0. How To Review This Packet Now" in text
    assert "## 1. Current Verification Snapshot" in text
    assert "Historical Context" in text
    assert f"Current synchronized pytest count: `{current_count}`" in text
    assert "python -m scripts.quality_gate_counts --check --skip-expensive" in text
    expected_review_commands = _opus_packet_expected_review_commands()
    assert _fenced_command_block_after(text, "Current handoff commands:") == expected_review_commands
    assert _fenced_command_block_after(text, "Minimum review command set:") == expected_review_commands
    normalized_packet_text = " ".join(text.split())
    assert "current completed/open status and command authority" in normalized_packet_text
    assert (
        "`wiki/review-backlog.md`, `docs/codex-review/OPEN_RISKS.md`, and "
        "`docs/codex-review/QUALITY_GATES.md`"
    ) in normalized_packet_text
    assert "Superpowers plan/spec inventories" in text
    assert "docs/superpowers/plans/README.md" in text
    assert "docs/superpowers/specs/README.md" in text
    assert "every dated plan or spec artifact" in text
    assert "## 0. Review Position" not in text
    assert text.count("Boundary statement:") == 1


def test_opus_packet_routes_git_scope_review_to_handoff_commands():
    opus_packet = (
        quality_gate_counts.REPO_ROOT
        / "docs"
        / "opus-review"
        / "OPUS_REVIEW_PACKET.md"
    )
    text = opus_packet.read_text(encoding="utf-8-sig")
    start = text.index("## 0. How To Review This Packet Now")
    end = text.index("## Historical Context", start)
    section = text[start:end]

    for phrase in [
        "Git Review Scope Snapshot",
        "git status --short --branch --untracked-files=all",
        "git diff --name-status",
        "git ls-files --others --exclude-standard",
        "git diff --check",
    ]:
        assert phrase in section


def test_opus_packet_verifier_coverage_mentions_contract_report_paths():
    opus_packet = (
        quality_gate_counts.REPO_ROOT
        / "docs"
        / "opus-review"
        / "OPUS_REVIEW_PACKET.md"
    )
    text = opus_packet.read_text(encoding="utf-8-sig")
    start = text.index("Verifier coverage:")
    end = text.index("## 3. Opus", start)
    verifier_section = text[start:end]

    for test_file in [
        "tests/test_evidence_contract_report.py",
        "tests/test_evidence_contract_fallback_report.py",
        "tests/test_evidence_contract_trace_report.py",
        "tests/test_evidence_contract_boundary_report.py",
    ]:
        assert test_file in verifier_section
    assert "stack-contract" in verifier_section
    assert "fallback" in verifier_section
    assert "trace-route" in verifier_section
    assert "split-boundary" in verifier_section


def test_opus_handoff_clarifies_superpowers_plan_artifacts_are_not_live_backlog():
    root = quality_gate_counts.REPO_ROOT
    handoff = root / "docs" / "opus-review" / "HANDOFF.md"
    plans_readme = root / "docs" / "superpowers" / "plans" / "README.md"
    specs_readme = root / "docs" / "superpowers" / "specs" / "README.md"

    handoff_text = handoff.read_text(encoding="utf-8-sig")
    assert "docs/superpowers/plans/README.md" in handoff_text
    assert "docs/superpowers/specs/README.md" in handoff_text
    assert "execution trace" in handoff_text
    assert "design note" in handoff_text

    readme_text = plans_readme.read_text(encoding="utf-8-sig")
    assert "not the live review backlog" in readme_text
    assert "wiki/review-backlog.md" in readme_text
    assert "docs/codex-review/OPEN_RISKS.md" in readme_text
    assert "docs/codex-review/QUALITY_GATES.md" in readme_text
    assert readme_text.index("wiki/review-backlog.md") < readme_text.index(
        "docs/codex-review/OPEN_RISKS.md"
    )
    assert readme_text.index("docs/codex-review/OPEN_RISKS.md") < readme_text.index(
        "docs/codex-review/QUALITY_GATES.md"
    )
    assert "dated execution traces" in readme_text

    specs_text = specs_readme.read_text(encoding="utf-8-sig")
    assert "not the live review backlog" in specs_text
    assert "wiki/review-backlog.md" in specs_text
    assert "docs/codex-review/OPEN_RISKS.md" in specs_text
    assert "docs/codex-review/QUALITY_GATES.md" in specs_text
    assert specs_text.index("wiki/review-backlog.md") < specs_text.index(
        "docs/codex-review/OPEN_RISKS.md"
    )
    assert specs_text.index("docs/codex-review/OPEN_RISKS.md") < specs_text.index(
        "docs/codex-review/QUALITY_GATES.md"
    )
    assert "dated design notes" in specs_text


@pytest.mark.parametrize(
    "relative_path",
    [
        "docs/superpowers/plans/README.md",
        "docs/superpowers/specs/README.md",
    ],
)
def test_superpowers_inventory_readmes_route_git_scope_to_opus_handoff(
    relative_path: str,
) -> None:
    text = (quality_gate_counts.REPO_ROOT / relative_path).read_text(
        encoding="utf-8-sig"
    )
    normalized = " ".join(text.split())

    for phrase in [
        "docs/opus-review/HANDOFF.md",
        "Git Review Scope Snapshot",
        "git status --short --branch --untracked-files=all",
        "git ls-files --others --exclude-standard",
        "dirty/untracked",
    ]:
        assert phrase in normalized


def test_opus_readme_includes_superpowers_inventory_in_first_read_scope():
    root = quality_gate_counts.REPO_ROOT
    readme = root / "docs" / "opus-review" / "README.md"

    text = readme.read_text(encoding="utf-8-sig")

    assert "docs/superpowers/plans/README.md" in text
    assert "docs/superpowers/specs/README.md" in text
    assert "Superpowers plan/spec inventories" in text
    assert "dated plan or spec artifact" in text
    assert "not the live review backlog" in text


def test_superpowers_artifact_readmes_inventory_current_files():
    root = quality_gate_counts.REPO_ROOT

    plan_dir = root / "docs" / "superpowers" / "plans"
    plan_readme = (plan_dir / "README.md").read_text(encoding="utf-8-sig")
    plan_files = sorted(
        path.name for path in plan_dir.glob("*.md") if path.name != "README.md"
    )
    assert "## Current Artifact Inventory" in plan_readme
    for filename in plan_files:
        assert f"`{filename}`" in plan_readme

    specs_dir = root / "docs" / "superpowers" / "specs"
    specs_readme = (specs_dir / "README.md").read_text(encoding="utf-8-sig")
    spec_files = sorted(
        path.name for path in specs_dir.glob("*.md") if path.name != "README.md"
    )
    assert "## Current Artifact Inventory" in specs_readme
    for filename in spec_files:
        assert f"`{filename}`" in specs_readme


def test_superpowers_plan_inventory_documents_no_open_task_checkboxes():
    root = quality_gate_counts.REPO_ROOT
    plan_dir = root / "docs" / "superpowers" / "plans"
    plan_readme = (plan_dir / "README.md").read_text(encoding="utf-8-sig")
    normalized_readme = " ".join(plan_readme.split())

    assert "no current plan artifact has open task checkboxes" in normalized_readme
    for path in plan_dir.glob("*.md"):
        if path.name == "README.md":
            continue
        text = path.read_text(encoding="utf-8-sig")
        open_tasks = [
            f"{path.name}:{line_number}"
            for line_number, line in enumerate(text.splitlines(), start=1)
            if line.startswith("- [ ]")
        ]
        assert open_tasks == []
