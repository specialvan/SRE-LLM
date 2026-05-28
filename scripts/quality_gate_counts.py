from __future__ import annotations

import argparse
from dataclasses import dataclass
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from scripts import package_smoke


REPO_ROOT = Path(__file__).resolve().parents[1]
PYTEST_TIMEOUT_SECONDS = 300
EVIDENCE_ARTIFACT_GATE_MODULES = (
    "analysis.evidence_manifest",
    "analysis.evidence_report",
)
ANALYSIS_SUITE_GATE_MODULES = ("analysis.s10_failure_trace", "analysis.run_all")
BROWSER_EVIDENCE_GATE_COMMANDS = (
    "python -m scripts.control_center_browser_smoke --report-manifests "
    "--report-json analysis/artifacts/control-center-browser-evidence-report.json",
)
PACKAGE_SMOKE_GATE_MODULES = ("scripts.package_smoke",)
INTEGRATION_AUDIT_GATE_MODULES = ("scripts.control_center_integration_audit",)
REVIEW_AUTHORITY_GATE_MODULES = ("scripts.review_authority_lint",)
DEMO_SMOKE_GATE_MODULES = (
    "examples.demo_sre_loop",
    "examples.demo_powered_descent",
    "examples.demo_catch_phase",
)
EXPECTED_CONTROL_CENTER_CONTRACT_DEPTH_KEYS = (
    "top_level",
    "object_groups",
    "object_fields",
    "array_item_groups",
    "array_item_fields",
    "timeline_fields",
)


def command_for_module(module: str) -> str:
    return f"python -m {module}"


def _summary_has_token(summary: str, token: str) -> bool:
    return any(part.strip() == token for part in summary.split(";"))


def _summary_has_field_prefix(summary: str, prefix: str) -> bool:
    return any(part.strip().startswith(prefix) for part in summary.split(";"))


CURRENT_QUALITY_GATE_COMMANDS = (
    "python -m pytest tests",
    *(command_for_module(module) for module in ANALYSIS_SUITE_GATE_MODULES),
    *(command_for_module(module) for module in EVIDENCE_ARTIFACT_GATE_MODULES),
    *BROWSER_EVIDENCE_GATE_COMMANDS,
    *(command_for_module(module) for module in PACKAGE_SMOKE_GATE_MODULES),
    *(command_for_module(module) for module in INTEGRATION_AUDIT_GATE_MODULES),
    *(command_for_module(module) for module in REVIEW_AUTHORITY_GATE_MODULES),
    *(command_for_module(module) for module in DEMO_SMOKE_GATE_MODULES),
)
QUALITY_GATE_COMMAND_DOCS = (
    "PR-REQUIREMENTS.md",
    "docs/V2_Knowledge/knowledge-base.html",
    "docs/codex-review/QUALITY_GATES.md",
    "docs/claude-development-audit/backlog.md",
    "docs/opus-review/HANDOFF.md",
    "docs/opus-review/OPUS_REVIEW_PACKET.md",
    "wiki/review-backlog.md",
)


@dataclass(frozen=True)
class QualityGateTarget:
    relative_path: str
    pattern: str
    replacement_template: str
    label: str

    def replacement(self, count: int, label: str) -> str:
        return self.replacement_template.format(count=count, label=label)


QUALITY_GATE_TARGETS = (
    QualityGateTarget(
        "PR-REQUIREMENTS.md",
        r"python -m pytest tests\s+# \d+ passed",
        "python -m pytest tests          # {label}",
        "PR front-matter pytest quality gate",
    ),
    QualityGateTarget(
        "PR-REQUIREMENTS.md",
        r"\| 单元测试 \| `python -m pytest tests` \| \*\*\d+ passed\*\* \|",
        "| 单元测试 | `python -m pytest tests` | **{label}** |",
        "PR NFR pytest quality gate",
    ),
    QualityGateTarget(
        "docs/V2_Knowledge/knowledge-base.html",
        r'<div class="chip"><b>tests</b> \d+ passed</div>',
        '<div class="chip"><b>tests</b> {label}</div>',
        "V2 tests chip",
    ),
    QualityGateTarget(
        "docs/V2_Knowledge/knowledge-base.html",
        (
            r"<tr><td><code>python -m pytest tests</code></td><td><b>"
            r"\d+ passed</b></td><td>~1 s</td></tr>"
        ),
        (
            "<tr><td><code>python -m pytest tests</code></td><td><b>"
            "{label}</b></td><td>~1 s</td></tr>"
        ),
        "V2 quality gate row",
    ),
    QualityGateTarget(
        "wiki/review-backlog.md",
        r"Full test suite: `python -m pytest tests -q` passes with \d+ tests",
        "Full test suite: `python -m pytest tests -q` passes with {count} tests",
        "wiki review backlog pytest baseline",
    ),
    QualityGateTarget(
        "wiki/README.md",
        (
            r"Current verified local gates: `python -m pytest tests -q` "
            r"passes with \d+\s+tests;"
        ),
        (
            "Current verified local gates: `python -m pytest tests -q` passes "
            "with {count}\n  tests;"
        ),
        "wiki README pytest baseline",
    ),
    QualityGateTarget(
        "docs/codex-review/CODEX_SUMMARY.md",
        r"`tests/`: current full suite passes with \d+ tests",
        "`tests/`: current full suite passes with {count} tests",
        "Codex summary pytest baseline",
    ),
    QualityGateTarget(
        "wiki/evidence-ledger.md",
        r"python -m pytest tests -q\s+# \d+ passed",
        "python -m pytest tests -q      # {label}",
        "wiki evidence ledger pytest baseline",
    ),
    QualityGateTarget(
        "docs/codex-review/README.md",
        r"\| Unit/integration tests \| `\d+ passed` \|",
        "| Unit/integration tests | `{label}` |",
        "Codex review README pytest baseline",
    ),
    QualityGateTarget(
        "docs/codex-review/QUALITY_GATES.md",
        r"python -m pytest tests -q\n\d+ passed",
        "python -m pytest tests -q\n{label}",
        "Codex quality gates pytest baseline",
    ),
    QualityGateTarget(
        "docs/codex-review/ENGINEERING_PACKET.md",
        r"python -m pytest tests -q\s+# \d+ passed in this continuation pass",
        "python -m pytest tests -q      # {label} in this continuation pass",
        "Codex engineering packet pytest baseline",
    ),
    QualityGateTarget(
        "docs/opus-review/OPUS_REVIEW_PACKET.md",
        r"quality gate pytest count: \d+",
        "quality gate pytest count: {count}",
        "Opus packet pytest baseline",
    ),
    QualityGateTarget(
        "docs/opus-review/HANDOFF.md",
        r"quality gate pytest count: \d+",
        "quality gate pytest count: {count}",
        "Opus handoff pytest baseline",
    ),
)


def parse_pytest_passed_count(output: str) -> int:
    match = re.search(r"(?m)(?:^|=+\s)(\d+)\s+passed\b", output)
    if match:
        return int(match.group(1))
    excerpt = output.strip().splitlines()[-5:]
    raise RuntimeError(
        "Could not parse pytest pass count from output:\n" + "\n".join(excerpt)
    )


def parse_collected_count(output: str) -> int:
    patterns = [
        r"(?m)^collected\s+(\d+)\s+items?\b",
        r"(?m)^(\d+)\s+tests?\s+collected\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, output)
        if match:
            return int(match.group(1))
    file_counts = [
        int(match.group(1))
        for match in re.finditer(r"(?m)^tests[/\\].+\.py:\s+(\d+)\s*$", output)
    ]
    if file_counts:
        return sum(file_counts)
    excerpt = output.strip().splitlines()[-5:]
    raise RuntimeError(
        "Could not parse pytest collection count from output:\n" + "\n".join(excerpt)
    )


def render_pytest_label(count: int) -> str:
    return f"{count} passed"


def replace_once(text: str, pattern: str, replacement: str, label: str) -> str:
    matches = list(re.finditer(pattern, text))
    if not matches:
        raise RuntimeError(f"missing {label}")
    if len(matches) != 1:
        raise RuntimeError(f"{label} matched {len(matches)} times")
    return re.sub(pattern, replacement, text, count=1)


def require_quality_gate_commands(docs: list[tuple[str, str]]) -> None:
    for relative_path, text in docs:
        for command in CURRENT_QUALITY_GATE_COMMANDS:
            if command not in text:
                raise RuntimeError(
                    f"{relative_path}: missing quality gate command: {command}"
                )
        manifest_command = "python -m analysis.evidence_manifest"
        report_command = "python -m analysis.evidence_report"
        if text.index(manifest_command) > text.index(report_command):
            raise RuntimeError(
                f"{relative_path}: {manifest_command} must appear before "
                f"{report_command}"
            )


def run_evidence_artifact_gates(repo_root: Path = REPO_ROOT) -> None:
    for module in EVIDENCE_ARTIFACT_GATE_MODULES:
        result = subprocess.run(
            [sys.executable, "-m", module],
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if result.returncode != 0:
            output = f"{result.stdout}\n{result.stderr}".strip()
            raise RuntimeError(f"{module} failed:\n{output}")


def run_browser_evidence_gate(repo_root: Path = REPO_ROOT) -> None:
    command = [
        sys.executable,
        "-m",
        "scripts.control_center_browser_smoke",
        "--report-manifests",
        "--report-json",
        "analysis/artifacts/control-center-browser-evidence-report.json",
    ]
    result = subprocess.run(
        command,
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        output = f"{result.stdout}\n{result.stderr}".strip()
        raise RuntimeError(
            "scripts.control_center_browser_smoke --report-manifests failed:\n"
            + output
        )


def run_package_smoke_gate(repo_root: Path = REPO_ROOT) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "scripts.package_smoke"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        output = f"{result.stdout}\n{result.stderr}".strip()
        raise RuntimeError(f"scripts.package_smoke failed:\n{output}")


def run_integration_audit_gate(repo_root: Path = REPO_ROOT) -> None:
    for module in INTEGRATION_AUDIT_GATE_MODULES:
        result = subprocess.run(
            [sys.executable, "-m", module],
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if result.returncode != 0:
            output = f"{result.stdout}\n{result.stderr}".strip()
            raise RuntimeError(f"{module} failed:\n{output}")


def run_review_authority_gate(repo_root: Path = REPO_ROOT) -> None:
    for module in REVIEW_AUTHORITY_GATE_MODULES:
        result = subprocess.run(
            [sys.executable, "-m", module],
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if result.returncode != 0:
            output = f"{result.stdout}\n{result.stderr}".strip()
            raise RuntimeError(f"{module} failed:\n{output}")


def run_analysis_suite_gate(repo_root: Path = REPO_ROOT) -> None:
    for module in ANALYSIS_SUITE_GATE_MODULES:
        result = subprocess.run(
            [sys.executable, "-m", module],
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if result.returncode != 0:
            output = f"{result.stdout}\n{result.stderr}".strip()
            raise RuntimeError(f"{module} failed:\n{output}")


def run_demo_smoke_gate(repo_root: Path = REPO_ROOT) -> None:
    for module in DEMO_SMOKE_GATE_MODULES:
        result = subprocess.run(
            [sys.executable, "-m", module],
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if result.returncode != 0:
            output = f"{result.stdout}\n{result.stderr}".strip()
            raise RuntimeError(f"{module} failed:\n{output}")


def collect_pytest_count(repo_root: Path = REPO_ROOT) -> int:
    try:
        test_result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=PYTEST_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"pytest quality gate timed out after {PYTEST_TIMEOUT_SECONDS} seconds"
        ) from exc
    test_output = f"{test_result.stdout}\n{test_result.stderr}"
    if test_result.returncode != 0:
        raise RuntimeError("pytest quality gate failed:\n" + test_output.strip())
    passed_count = parse_pytest_passed_count(test_output)

    with tempfile.TemporaryDirectory(prefix="package-smoke-") as temp_dir:
        package_smoke.build_wheel_and_smoke_imports(Path(temp_dir), repo_root)
    control_center_evidence = package_smoke.verify_control_center_evidence_report(
        repo_root
        / "analysis"
        / "artifacts"
        / "control-center-browser-evidence-report.json"
    )
    if not _summary_has_token(control_center_evidence, "desktop+mobile"):
        raise RuntimeError(
            "control-center quality gate missing normal desktop/mobile browser evidence"
        )
    if not _summary_has_field_prefix(control_center_evidence, "error=desktop:1440x960:dom"):
        raise RuntimeError(
            "control-center quality gate missing backend-error browser evidence"
        )
    if not _summary_has_field_prefix(control_center_evidence, "frontend_error=desktop:1440x960:dom"):
        raise RuntimeError(
            "control-center quality gate missing frontend-error browser evidence"
        )
    if not _summary_has_token(
        control_center_evidence,
        "manifest_records=normal+backend_error+frontend_error",
    ):
        raise RuntimeError(
            "control-center quality gate missing manifest-record browser evidence"
        )
    if not _summary_has_token(
        control_center_evidence,
        "manifest_replay=normal+backend_error+frontend_error",
    ):
        raise RuntimeError(
            "control-center quality gate missing manifest replay evidence"
        )
    contract_depth_part = next(
        (
            part.strip()
            for part in control_center_evidence.split(";")
            if part.strip().startswith("contract_depth=")
        ),
        "",
    )
    missing_contract_depth_keys = [
        key
        for key in EXPECTED_CONTROL_CENTER_CONTRACT_DEPTH_KEYS
        if f"{key}:" not in contract_depth_part
    ]
    if not contract_depth_part or missing_contract_depth_keys:
        raise RuntimeError(
            "control-center quality gate missing contract-depth browser evidence"
        )

    try:
        collect_result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests", "--collect-only", "-q"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=PYTEST_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"pytest quality gate timed out after {PYTEST_TIMEOUT_SECONDS} seconds"
        ) from exc
    collect_output = f"{collect_result.stdout}\n{collect_result.stderr}"
    if collect_result.returncode != 0:
        raise RuntimeError("pytest collection failed:\n" + collect_output.strip())
    collected_count = parse_collected_count(collect_output)
    if passed_count != collected_count:
        raise RuntimeError(
            f"pytest quality gate count mismatch: {passed_count} passed, "
            f"{collected_count} collected"
        )
    return passed_count


def _write_updated(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _read_target_texts(repo_root: Path) -> dict[str, str]:
    return {
        relative_path: (repo_root / relative_path).read_text(encoding="utf-8-sig")
        for relative_path in sorted(
            {target.relative_path for target in QUALITY_GATE_TARGETS}
        )
    }


def _apply_quality_gate_targets(texts: dict[str, str], count: int) -> dict[str, str]:
    label = render_pytest_label(count)
    updated = dict(texts)
    for target in QUALITY_GATE_TARGETS:
        try:
            updated[target.relative_path] = replace_once(
                updated[target.relative_path],
                target.pattern,
                target.replacement(count, label),
                target.label,
            )
        except RuntimeError as exc:
            raise RuntimeError(f"{target.relative_path}: {exc}") from exc
    return updated


def update_quality_gate_docs(
    repo_root: Path = REPO_ROOT, count: int | None = None
) -> int:
    if count is None:
        run_browser_evidence_gate(repo_root)
        current_count = collect_pytest_count(repo_root)
        run_analysis_suite_gate(repo_root)
        run_evidence_artifact_gates(repo_root)
        run_package_smoke_gate(repo_root)
        run_integration_audit_gate(repo_root)
        run_review_authority_gate(repo_root)
        run_demo_smoke_gate(repo_root)
    else:
        current_count = count

    require_quality_gate_commands(
        [
            (
                relative_path,
                (repo_root / relative_path).read_text(encoding="utf-8-sig"),
            )
            for relative_path in QUALITY_GATE_COMMAND_DOCS
        ]
    )

    texts = _read_target_texts(repo_root)
    updated_texts = _apply_quality_gate_targets(texts, current_count)
    for relative_path, text in updated_texts.items():
        _write_updated(repo_root / relative_path, text)
    return current_count


def check_quality_gate_docs(
    repo_root: Path = REPO_ROOT,
    count: int | None = None,
    *,
    skip_expensive: bool = False,
) -> int | None:
    if count is None and skip_expensive:
        current_count = None
    elif count is None:
        run_browser_evidence_gate(repo_root)
        current_count = collect_pytest_count(repo_root)
        run_analysis_suite_gate(repo_root)
        run_evidence_artifact_gates(repo_root)
        run_package_smoke_gate(repo_root)
        run_integration_audit_gate(repo_root)
        run_review_authority_gate(repo_root)
        run_demo_smoke_gate(repo_root)
    else:
        current_count = count

    require_quality_gate_commands(
        [
            (
                relative_path,
                (repo_root / relative_path).read_text(encoding="utf-8-sig"),
            )
            for relative_path in QUALITY_GATE_COMMAND_DOCS
        ]
    )

    texts = _read_target_texts(repo_root)
    probe_count = current_count if current_count is not None else 0
    updated_texts = _apply_quality_gate_targets(texts, probe_count)
    if current_count is not None:
        drifted = [
            relative_path
            for relative_path, text in texts.items()
            if updated_texts[relative_path] != text
        ]
        if drifted:
            raise RuntimeError(
                "quality gate docs drift; run python -m scripts.quality_gate_counts "
                "to update: " + ", ".join(drifted)
            )
    return current_count


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Update current quality-gate test counts."
    )
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify gates and docs drift without writing files.",
    )
    parser.add_argument(
        "--skip-expensive",
        action="store_true",
        help="With --check, only validate documented command/target shape.",
    )
    args = parser.parse_args(argv)
    if args.skip_expensive and not args.check:
        parser.error("--skip-expensive requires --check")
    if args.check:
        count = check_quality_gate_docs(
            args.repo_root,
            skip_expensive=args.skip_expensive,
        )
        if count is None:
            print("quality gate docs check passed")
        else:
            print(f"quality gate docs check passed: {count}")
        return
    count = update_quality_gate_docs(args.repo_root)
    print(f"quality gate pytest count: {count}")


if __name__ == "__main__":
    main()
