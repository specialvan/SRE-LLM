from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PYTEST_TIMEOUT_SECONDS = 120


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


def collect_pytest_count(repo_root: Path = REPO_ROOT) -> int:
    try:
        test_result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests", "-q"],
            cwd=repo_root,
            capture_output=True,
            text=True,
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

    try:
        collect_result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests", "--collect-only", "-q"],
            cwd=repo_root,
            capture_output=True,
            text=True,
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
    return parse_collected_count(collect_output)


def _write_updated(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def update_quality_gate_docs(
    repo_root: Path = REPO_ROOT, count: int | None = None
) -> int:
    current_count = collect_pytest_count(repo_root) if count is None else count
    label = render_pytest_label(current_count)

    pr_path = repo_root / "PR-REQUIREMENTS.md"
    pr_text = pr_path.read_text(encoding="utf-8-sig")
    pr_text = replace_once(
        pr_text,
        r"pytest tests -q\s+# \d+ passed",
        f"pytest tests -q                 # {label}",
        "PR front-matter pytest quality gate",
    )
    pr_text = replace_once(
        pr_text,
        r"\| 单元测试 \| `python -m pytest tests -q` \| \*\*\d+ passed\*\* \|",
        f"| 单元测试 | `python -m pytest tests -q` | **{label}** |",
        "PR NFR pytest quality gate",
    )

    html_path = repo_root / "docs" / "V2_Knowledge" / "knowledge-base.html"
    html_text = html_path.read_text(encoding="utf-8-sig")
    html_text = replace_once(
        html_text,
        r'<div class="chip"><b>tests</b> \d+ passed</div>',
        f'<div class="chip"><b>tests</b> {label}</div>',
        "V2 tests chip",
    )
    html_text = replace_once(
        html_text,
        r"<tr><td><code>python -m pytest tests -q</code></td><td><b>\d+ passed</b></td><td>~1 s</td></tr>",
        f"<tr><td><code>python -m pytest tests -q</code></td><td><b>{label}</b></td><td>~1 s</td></tr>",
        "V2 quality gate row",
    )
    _write_updated(pr_path, pr_text)
    _write_updated(html_path, html_text)
    return current_count


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Update current quality-gate test counts."
    )
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)
    count = update_quality_gate_docs(args.repo_root)
    print(f"quality gate pytest count: {count}")


if __name__ == "__main__":
    main()
