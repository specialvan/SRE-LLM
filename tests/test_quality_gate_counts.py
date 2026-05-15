from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.quality_gate_counts as quality_gate_counts
from scripts.quality_gate_counts import (
    collect_pytest_count,
    parse_collected_count,
    parse_pytest_passed_count,
    render_pytest_label,
    replace_once,
    update_quality_gate_docs,
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
    smoke_dirs: list[Path] = []

    def fake_run(
        command: list[str], *args: object, **kwargs: object
    ) -> SimpleNamespace:
        calls.append(command)
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

    assert collect_pytest_count(Path("/repo")) == 90
    assert len(smoke_dirs) == 1
    assert calls == [
        [sys.executable, "-m", "pytest", "tests"],
        [sys.executable, "-m", "pytest", "tests", "--collect-only", "-q"],
    ]


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


def test_update_quality_gate_docs_updates_only_current_fields(tmp_path: Path):
    pr = tmp_path / "PR-REQUIREMENTS.md"
    html = tmp_path / "docs" / "V2_Knowledge" / "knowledge-base.html"
    html.parent.mkdir(parents=True)
    pr.write_text(
        """
quality-gates:
  - python -m pytest tests          # 83 passed

| 单元测试 | `python -m pytest tests` | **83 passed** |

historical snapshot: 51 passed
""".lstrip(),
        encoding="utf-8",
    )
    html.write_text(
        """
<div class="chip"><b>tests</b> 83 passed</div>
<tr><td><code>python -m pytest tests</code></td><td><b>83 passed</b></td><td>~1 s</td></tr>
<p>historical snapshot: 51 passed</p>
""".lstrip(),
        encoding="utf-8",
    )

    update_quality_gate_docs(tmp_path, 85)

    pr_text = pr.read_text(encoding="utf-8")
    html_text = html.read_text(encoding="utf-8")
    assert "# 85 passed" in pr_text
    assert "**85 passed**" in pr_text
    assert "historical snapshot: 51 passed" in pr_text
    assert '<div class="chip"><b>tests</b> 85 passed</div>' in html_text
    assert "<td><b>85 passed</b></td>" in html_text
    assert "historical snapshot: 51 passed" in html_text


def test_update_quality_gate_docs_does_not_partially_write_on_replacement_failure(
    tmp_path: Path,
):
    pr = tmp_path / "PR-REQUIREMENTS.md"
    html = tmp_path / "docs" / "V2_Knowledge" / "knowledge-base.html"
    html.parent.mkdir(parents=True)
    original_pr = """
quality-gates:
  - python -m pytest tests          # 83 passed

| 单元测试 | `python -m pytest tests` | **83 passed** |
""".lstrip()
    pr.write_text(original_pr, encoding="utf-8")
    html.write_text("<p>missing current quality gate fields</p>", encoding="utf-8")

    with pytest.raises(RuntimeError, match="missing V2 tests chip"):
        update_quality_gate_docs(tmp_path, 85)

    assert pr.read_text(encoding="utf-8") == original_pr
