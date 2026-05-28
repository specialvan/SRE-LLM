from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.quality_gate_counts as quality_gate_counts
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


def _command_lines() -> str:
    return "\n".join(quality_gate_counts.CURRENT_QUALITY_GATE_COMMANDS) + "\n"


def _bullet_command_lines() -> str:
    return "".join(
        f"  - {command}\n" for command in quality_gate_counts.CURRENT_QUALITY_GATE_COMMANDS
    )


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
    html.parent.mkdir(parents=True)
    backlog.parent.mkdir(parents=True)
    codex_summary.parent.mkdir(parents=True)
    audit_backlog.parent.mkdir(parents=True)
    opus_packet.parent.mkdir(parents=True)
    pr.write_text(
        "quality-gates:\n"
        "  - python -m pytest tests          # 83 passed\n"
        + _bullet_command_lines().replace("  - python -m pytest tests\n", "")
        + "\n"
        "| 单元测试 | `python -m pytest tests` | **83 passed** |\n",
        encoding="utf-8",
    )
    html.write_text(
        '<div class="chip"><b>tests</b> 83 passed</div>\n'
        "<tr><td><code>python -m pytest tests</code></td><td><b>83 passed</b></td><td>~1 s</td></tr>\n"
        + _command_lines(),
        encoding="utf-8",
    )
    wiki_readme.write_text(
        "- Current verified local gates: `python -m pytest tests -q` passes with 83\n"
        "  tests; `python -m analysis.run_all` completes 12 studies.\n",
        encoding="utf-8",
    )
    backlog.write_text(
        "- Full test suite: `python -m pytest tests -q` passes with 83 tests\n",
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
        + _command_lines(),
        encoding="utf-8",
    )
    engineering_packet.write_text(
        "python -m pytest tests -q      # 83 passed in this continuation pass\n",
        encoding="utf-8",
    )
    audit_backlog.write_text(_command_lines(), encoding="utf-8")
    opus_packet.write_text(
        _command_lines()
        +
        "quality gate pytest count: 83\n",
        encoding="utf-8",
    )


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
    assert "docs/opus-review/OPUS_REVIEW_PACKET.md" in paths
    assert all(target.pattern for target in QUALITY_GATE_TARGETS)
    assert all(target.replacement_template for target in QUALITY_GATE_TARGETS)


def test_current_quality_gate_commands_include_demo_smoke_gate():
    assert (
        "python -m examples.demo_sre_loop"
        in quality_gate_counts.CURRENT_QUALITY_GATE_COMMANDS
    )


def test_current_quality_gate_commands_include_control_center_integration_audit():
    assert "python -m scripts.control_center_integration_audit" in (
        quality_gate_counts.CURRENT_QUALITY_GATE_COMMANDS
    )


def test_current_quality_gate_commands_include_browser_and_package_smoke_gates():
    assert BROWSER_REPORT_COMMAND in quality_gate_counts.CURRENT_QUALITY_GATE_COMMANDS
    assert "python -m scripts.package_smoke" in quality_gate_counts.CURRENT_QUALITY_GATE_COMMANDS


def test_current_quality_gate_commands_include_section_10_trace_gate():
    assert "python -m analysis.s10_failure_trace" in (
        quality_gate_counts.CURRENT_QUALITY_GATE_COMMANDS
    )
    assert "analysis.s10_failure_trace" in quality_gate_counts.ANALYSIS_SUITE_GATE_MODULES


def test_current_quality_gate_commands_match_executed_gate_modules():
    expected = (
        ("python -m pytest tests",)
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
            for module in quality_gate_counts.DEMO_SMOKE_GATE_MODULES
        )
    )

    assert quality_gate_counts.CURRENT_QUALITY_GATE_COMMANDS == expected


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

    assert commands == quality_gate_counts.CURRENT_QUALITY_GATE_COMMANDS


def test_quality_gate_command_docs_include_development_audit_backlog():
    assert (
        "docs/claude-development-audit/backlog.md"
        in quality_gate_counts.QUALITY_GATE_COMMAND_DOCS
    )


def test_require_quality_gate_commands_reports_missing_doc_path():
    complete_text = "\n".join(quality_gate_counts.CURRENT_QUALITY_GATE_COMMANDS)
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
    commands = list(quality_gate_counts.CURRENT_QUALITY_GATE_COMMANDS)
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
        return SimpleNamespace(returncode=0, stdout="90 passed in 1.23s", stderr="")

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
        [sys.executable, "-m", "pytest", "tests"],
        [sys.executable, "-m", "pytest", "tests", "--collect-only", "-q"],
    ]
    assert timeouts == [180, 180]
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

    monkeypatch.setattr(quality_gate_counts, "collect_pytest_count", fake_collect)
    monkeypatch.setattr(quality_gate_counts, "run_analysis_suite_gate", fake_analysis_gate)
    monkeypatch.setattr(
        quality_gate_counts, "run_evidence_artifact_gates", fake_artifact_gates
    )
    monkeypatch.setattr(quality_gate_counts, "run_browser_evidence_gate", fake_browser_gate)
    monkeypatch.setattr(quality_gate_counts, "run_package_smoke_gate", fake_package_gate)
    monkeypatch.setattr(quality_gate_counts, "run_integration_audit_gate", fake_audit_gate)
    monkeypatch.setattr(quality_gate_counts, "run_demo_smoke_gate", fake_demo_gate)

    _write_minimal_quality_gate_docs(tmp_path)

    update_quality_gate_docs(tmp_path)

    assert calls == ["browser", "pytest", "analysis", "evidence", "package", "audit", "demo"]


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

    monkeypatch.setattr(quality_gate_counts, "collect_pytest_count", fake_collect)
    monkeypatch.setattr(quality_gate_counts, "run_analysis_suite_gate", fake_analysis_gate)
    monkeypatch.setattr(
        quality_gate_counts, "run_evidence_artifact_gates", fake_artifact_gates
    )
    monkeypatch.setattr(quality_gate_counts, "run_browser_evidence_gate", fake_browser_gate)
    monkeypatch.setattr(quality_gate_counts, "run_package_smoke_gate", fake_package_gate)
    monkeypatch.setattr(quality_gate_counts, "run_integration_audit_gate", fake_audit_gate)
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
    html.parent.mkdir(parents=True)
    backlog.parent.mkdir(parents=True)
    codex_summary.parent.mkdir(parents=True)
    audit_backlog.parent.mkdir(parents=True)
    opus_packet.parent.mkdir(parents=True)
    pr.write_text(
        """
quality-gates:
  - python -m pytest tests          # 83 passed
  - python -m analysis.s10_failure_trace
  - python -m analysis.run_all
  - python -m analysis.evidence_manifest
  - python -m analysis.evidence_report
  - python -m scripts.control_center_browser_smoke --report-manifests --report-json analysis/artifacts/control-center-browser-evidence-report.json
  - python -m scripts.package_smoke
  - python -m scripts.control_center_integration_audit
  - python -m examples.demo_sre_loop
  - python -m examples.demo_powered_descent
  - python -m examples.demo_catch_phase

| 单元测试 | `python -m pytest tests` | **83 passed** |
| 基准证据 | `python -m analysis.run_all` | All 12 studies finish |
| 事件证据 manifest | `python -m analysis.evidence_manifest` | exported |
| 事件证据报告 | `python -m analysis.evidence_report` | validates |
""".lstrip(),
        encoding="utf-8",
    )
    html.write_text(
        """
<div class="chip"><b>tests</b> 83 passed</div>
<tr><td><code>python -m pytest tests</code></td><td><b>83 passed</b></td><td>~1 s</td></tr>
<tr><td><code>python -m analysis.s10_failure_trace</code></td><td>Section 10 trace artifacts exported</td><td>~1 s</td></tr>
<tr><td><code>python -m analysis.run_all</code></td><td>All 12 studies finished</td><td>~3 s</td></tr>
<tr><td><code>python -m analysis.evidence_manifest</code></td><td>S10/S11/S12 JSON/JSONL evidence + stack contract exported</td><td>~2 s</td></tr>
<tr><td><code>python -m analysis.evidence_report</code></td><td>Manifest-linked artifacts validate</td><td>&lt;1 s</td></tr>
<tr><td><code>python -m scripts.control_center_browser_smoke --report-manifests --report-json analysis/artifacts/control-center-browser-evidence-report.json</code></td><td>Control-center browser evidence report exported</td><td>&lt;1 s</td></tr>
<tr><td><code>python -m scripts.package_smoke</code></td><td>Package smoke validates evidence report</td><td>&lt;1 s</td></tr>
<tr><td><code>python -m scripts.control_center_integration_audit</code></td><td>Control-center integration audit exported</td><td>&lt;1 s</td></tr>
<tr><td><code>python -m examples.demo_sre_loop</code></td><td>Demo trace prints</td><td>&lt;1 s</td></tr>
<tr><td><code>python -m examples.demo_powered_descent</code></td><td>PDG demo prints terminal state</td><td>&lt;1 s</td></tr>
<tr><td><code>python -m examples.demo_catch_phase</code></td><td>Catch demo prints lateral error</td><td>&lt;1 s</td></tr>
""".lstrip(),
        encoding="utf-8",
    )
    wiki_readme.write_text(
        "- Current verified local gates: `python -m pytest tests -q` passes with 83\n"
        "  tests; `python -m analysis.run_all` completes 12 studies.\n",
        encoding="utf-8",
    )
    backlog.write_text(
        "- Full test suite: `python -m pytest tests -q` passes with 83 tests\n",
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
        "python -m pytest tests\n"
        "python -m analysis.s10_failure_trace\n"
        "python -m analysis.run_all\n"
        "python -m analysis.evidence_manifest\n"
        "python -m analysis.evidence_report\n"
        "python -m scripts.control_center_browser_smoke --report-manifests --report-json analysis/artifacts/control-center-browser-evidence-report.json\n"
        "python -m scripts.package_smoke\n"
        "python -m scripts.control_center_integration_audit\n"
        "python -m examples.demo_sre_loop\n"
        "python -m examples.demo_powered_descent\n"
        "python -m examples.demo_catch_phase\n",
        encoding="utf-8",
    )
    engineering_packet.write_text(
        "python -m pytest tests -q      # 83 passed in this continuation pass\n",
        encoding="utf-8",
    )
    audit_backlog.write_text(_command_lines(), encoding="utf-8")
    opus_packet.write_text(
        _command_lines()
        +
        "quality gate pytest count: 83\n",
        encoding="utf-8",
    )

    update_quality_gate_docs(tmp_path)

    assert calls == ["browser", "pytest", "analysis", "evidence", "package", "audit", "demo"]


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
    html.parent.mkdir(parents=True)
    backlog.parent.mkdir(parents=True)
    codex_summary.parent.mkdir(parents=True)
    audit_backlog.parent.mkdir(parents=True)
    opus_packet.parent.mkdir(parents=True)
    pr.write_text(
        """
quality-gates:
  - python -m pytest tests          # 83 passed
  - python -m analysis.s10_failure_trace
  - python -m analysis.run_all
  - python -m analysis.evidence_manifest
  - python -m analysis.evidence_report
  - python -m scripts.control_center_browser_smoke --report-manifests --report-json analysis/artifacts/control-center-browser-evidence-report.json
  - python -m scripts.package_smoke
  - python -m scripts.control_center_integration_audit
  - python -m examples.demo_sre_loop
  - python -m examples.demo_powered_descent
  - python -m examples.demo_catch_phase

| 单元测试 | `python -m pytest tests` | **83 passed** |
| 基准证据 | `python -m analysis.run_all` | All 12 studies finish |
| 事件证据 manifest | `python -m analysis.evidence_manifest` | exported |
| 事件证据报告 | `python -m analysis.evidence_report` | validates |

historical snapshot: 51 passed
""".lstrip(),
        encoding="utf-8",
    )
    html.write_text(
        """
<div class="chip"><b>tests</b> 83 passed</div>
<tr><td><code>python -m pytest tests</code></td><td><b>83 passed</b></td><td>~1 s</td></tr>
<tr><td><code>python -m analysis.s10_failure_trace</code></td><td>Section 10 trace artifacts exported</td><td>~1 s</td></tr>
<tr><td><code>python -m analysis.run_all</code></td><td>All 12 studies finished</td><td>~3 s</td></tr>
<tr><td><code>python -m analysis.evidence_manifest</code></td><td>S10/S11/S12 JSON/JSONL evidence + stack contract exported</td><td>~2 s</td></tr>
<tr><td><code>python -m analysis.evidence_report</code></td><td>Manifest-linked artifacts validate</td><td>&lt;1 s</td></tr>
<tr><td><code>python -m scripts.control_center_browser_smoke --report-manifests --report-json analysis/artifacts/control-center-browser-evidence-report.json</code></td><td>Control-center browser evidence report exported</td><td>&lt;1 s</td></tr>
<tr><td><code>python -m scripts.package_smoke</code></td><td>Package smoke validates evidence report</td><td>&lt;1 s</td></tr>
<tr><td><code>python -m scripts.control_center_integration_audit</code></td><td>Control-center integration audit exported</td><td>&lt;1 s</td></tr>
<tr><td><code>python -m examples.demo_sre_loop</code></td><td>Demo trace prints</td><td>&lt;1 s</td></tr>
<tr><td><code>python -m examples.demo_powered_descent</code></td><td>PDG demo prints terminal state</td><td>&lt;1 s</td></tr>
<tr><td><code>python -m examples.demo_catch_phase</code></td><td>Catch demo prints lateral error</td><td>&lt;1 s</td></tr>
<p>historical snapshot: 51 passed</p>
""".lstrip(),
        encoding="utf-8",
    )
    backlog.write_text(
        """
## Current Verified Baseline

- Full test suite: `python -m pytest tests -q` passes with 83 tests in the
  current workspace.
- Historical note: 51 tests in an older packet.
""".lstrip(),
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
        + _command_lines()
        + "\n"
        "historical snapshot: 51 passed\n",
        encoding="utf-8",
    )
    engineering_packet.write_text(
        "python -m pytest tests -q      # 83 passed in this continuation pass\n"
        "historical snapshot: 51 passed\n",
        encoding="utf-8",
    )
    audit_backlog.write_text(
        _command_lines() + "historical snapshot: 51 passed\n", encoding="utf-8"
    )
    opus_packet.write_text(
        _command_lines()
        +
        "quality gate pytest count: 83\n"
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
    assert "# 85 passed" in pr_text
    assert "**85 passed**" in pr_text
    assert "historical snapshot: 51 passed" in pr_text
    assert '<div class="chip"><b>tests</b> 85 passed</div>' in html_text
    assert "<td><b>85 passed</b></td>" in html_text
    assert "historical snapshot: 51 passed" in html_text
    assert "passes with 85 tests" in backlog_text
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
    assert "# 85 passed in this continuation pass" in engineering_packet_text
    assert "historical snapshot: 51 passed" in engineering_packet_text
    assert "quality gate pytest count: 85" in opus_packet_text
    assert "historical snapshot: 51 passed" in opus_packet_text


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
    html.parent.mkdir(parents=True)
    backlog.parent.mkdir(parents=True)
    codex_summary.parent.mkdir(parents=True)
    audit_backlog.parent.mkdir(parents=True)
    opus_packet.parent.mkdir(parents=True)
    original_pr = """
quality-gates:
  - python -m pytest tests          # 83 passed
  - python -m analysis.s10_failure_trace
  - python -m analysis.run_all
  - python -m analysis.evidence_manifest
  - python -m analysis.evidence_report
  - python -m scripts.control_center_browser_smoke --report-manifests --report-json analysis/artifacts/control-center-browser-evidence-report.json
  - python -m scripts.package_smoke
  - python -m scripts.control_center_integration_audit
  - python -m examples.demo_sre_loop
  - python -m examples.demo_powered_descent
  - python -m examples.demo_catch_phase

| 单元测试 | `python -m pytest tests` | **83 passed** |
| 基准证据 | `python -m analysis.run_all` | All 12 studies finish |
| 事件证据 manifest | `python -m analysis.evidence_manifest` | exported |
| 事件证据报告 | `python -m analysis.evidence_report` | validates |
""".lstrip()
    pr.write_text(original_pr, encoding="utf-8")
    html.write_text(
        "<p>missing current quality gate fields</p>\n"
        "python -m pytest tests\n"
        "python -m analysis.s10_failure_trace\n"
        "python -m analysis.run_all\n"
        "python -m analysis.evidence_manifest\n"
        "python -m analysis.evidence_report\n"
        "python -m scripts.control_center_browser_smoke --report-manifests --report-json analysis/artifacts/control-center-browser-evidence-report.json\n"
        "python -m scripts.package_smoke\n"
        "python -m scripts.control_center_integration_audit\n"
        "python -m examples.demo_sre_loop\n"
        "python -m examples.demo_powered_descent\n"
        "python -m examples.demo_catch_phase\n",
        encoding="utf-8",
    )
    backlog.write_text(
        "- Full test suite: `python -m pytest tests -q` passes with 83 tests\n",
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
        + _command_lines(),
        encoding="utf-8",
    )
    engineering_packet.write_text(
        "python -m pytest tests -q      # 83 passed in this continuation pass\n",
        encoding="utf-8",
    )
    audit_backlog.write_text(_command_lines(), encoding="utf-8")
    opus_packet.write_text(
        _command_lines()
        +
        "quality gate pytest count: 83\n",
        encoding="utf-8",
    )

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
    audit_backlog = tmp_path / "docs" / "claude-development-audit" / "backlog.md"
    opus_packet = tmp_path / "docs" / "opus-review" / "OPUS_REVIEW_PACKET.md"
    html.parent.mkdir(parents=True)
    quality_gates.parent.mkdir(parents=True)
    audit_backlog.parent.mkdir(parents=True)
    opus_packet.parent.mkdir(parents=True)
    pr.write_text(
        """
quality-gates:
  - python -m pytest tests          # 83 passed
  - python -m analysis.s10_failure_trace
  - python -m analysis.run_all
  - python -m analysis.evidence_manifest

| 单元测试 | `python -m pytest tests` | **83 passed** |
| 基准证据 | `python -m analysis.run_all` | All 12 studies finish |
| 事件证据 manifest | `python -m analysis.evidence_manifest` | exported |
""".lstrip(),
        encoding="utf-8",
    )
    html.write_text(
        """
<div class="chip"><b>tests</b> 83 passed</div>
<tr><td><code>python -m pytest tests</code></td><td><b>83 passed</b></td><td>~1 s</td></tr>
<tr><td><code>python -m analysis.s10_failure_trace</code></td><td>Section 10 trace artifacts exported</td><td>~1 s</td></tr>
<tr><td><code>python -m analysis.run_all</code></td><td>All 12 studies finished</td><td>~3 s</td></tr>
<tr><td><code>python -m analysis.evidence_manifest</code></td><td>S10/S11/S12 JSON/JSONL evidence + stack contract exported</td><td>~2 s</td></tr>
""".lstrip(),
        encoding="utf-8",
    )
    quality_gates.write_text(
        "python -m pytest tests\n"
        "python -m analysis.s10_failure_trace\n"
        "python -m analysis.run_all\n"
        "python -m analysis.evidence_manifest\n"
        "python -m analysis.evidence_report\n"
        "python -m scripts.control_center_integration_audit\n"
        "python -m examples.demo_sre_loop\n"
        "python -m examples.demo_powered_descent\n"
        "python -m examples.demo_catch_phase\n"
        "python -m pytest tests -q\n83 passed\n",
        encoding="utf-8",
    )
    audit_backlog.write_text(
        "python -m pytest tests\n"
        "python -m analysis.s10_failure_trace\n"
        "python -m analysis.run_all\n"
        "python -m analysis.evidence_manifest\n"
        "python -m analysis.evidence_report\n"
        "python -m scripts.control_center_integration_audit\n"
        "python -m examples.demo_sre_loop\n"
        "python -m examples.demo_powered_descent\n"
        "python -m examples.demo_catch_phase\n",
        encoding="utf-8",
    )
    opus_packet.write_text(
        "python -m pytest tests\n"
        "python -m analysis.s10_failure_trace\n"
        "python -m analysis.run_all\n"
        "python -m analysis.evidence_manifest\n"
        "python -m analysis.evidence_report\n"
        "python -m scripts.control_center_integration_audit\n"
        "python -m examples.demo_sre_loop\n"
        "python -m examples.demo_powered_descent\n"
        "python -m examples.demo_catch_phase\n"
        "quality gate pytest count: 83\n",
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


def test_engineering_packet_documents_current_merge_scope_categories():
    engineering_packet = (
        quality_gate_counts.REPO_ROOT
        / "docs"
        / "codex-review"
        / "ENGINEERING_PACKET.md"
    )
    text = engineering_packet.read_text(encoding="utf-8-sig")

    assert "Merge-Scope Checklist" in text
    for path in [
        "analysis/evidence_manifest.py",
        "analysis/evidence_report.py",
        "analysis/s11_catch_sre_wrapper.py",
        "analysis/s12_sre_replay.py",
        "scripts/control_center_browser_smoke.py",
        "scripts/control_center_integration_audit.py",
        "scripts/evidence_boundary_lint.py",
        "sre_control/catch_adapter.py",
        "sre_control/stack_contract.py",
        "tests/test_evidence_manifest.py",
        "tests/test_control_center_browser_smoke.py",
        "docs/CONTROL_CENTER_HANDOFF.md",
        "docs/EVENT_EVIDENCE_MANIFEST.md",
        "docs/STACK_DATA_CONTRACT.md",
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
