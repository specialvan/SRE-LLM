"""Regenerate the factual parts of state.json from the live repo.

Run from repo root:

    python docs/V2_Knowledge/_regenerate_state.py

What it (re-)computes (non-destructive, dry-run by default):

    repository.head_commit_short       from git log
    repository.head_commit_subject     from git log
    health.tests_total                 from pytest --collect-only
    health.demos_total                 from examples/demo_*.py + compare_*.py
    demos                              from examples/ file list
    docs                               from docs/ + docs/*/ file listing
    public_api_symbols                 from `attention_residuals/__init__.py`'s __all__

What it deliberately DOES NOT touch:

    hard_invariants        — semantic; reviewer-curated
    pr_review_guardrails   — semantic; reviewer-curated
    open_actions           — reviewer-curated
    open_gaps              — reviewer-curated
    layers                 — structural; reviewer-curated
    closed_loops           — reviewer-curated
    notes_for_next_agent   — reviewer-curated
    snapshot_date          — you update this manually when cutting a snapshot
    snapshot_author        — you update this manually

Use --write to persist the diff; default is --dry-run.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List


REPO_ROOT = Path(__file__).resolve().parents[2]
STATE_PATH = REPO_ROOT / "docs" / "V2_Knowledge" / "state.json"

# Fields this tool may rewrite.
FACTUAL_KEYS = {
    ("repository", "head_commit_short"),
    ("repository", "head_commit_subject"),
    ("health", "tests_total"),
    ("health", "demos_total"),
    ("demos",),
    ("docs",),
    ("public_api_symbols",),
}


def git_head_short() -> str:
    return _run("git", "log", "-1", "--format=%h").strip()


def git_head_subject() -> str:
    return _run("git", "log", "-1", "--format=%s").strip()


def _run(*cmd: str) -> str:
    result = subprocess.run(
        list(cmd), cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    )
    return result.stdout


def count_tests() -> int:
    """Count pytest-collected tests via `pytest --collect-only -q`.

    Filters out ``tests/skill/`` — those belong to a parallel
    skill-research feature and are not part of the attention-residuals
    spec scope tracked by this state.json."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    if result.returncode != 0:
        # collect-only returns 5 on failures; try parsing anyway
        pass
    # Lines like "tests/test_foo.py: 7" — sum the trailing integers.
    # Skip anything under tests/skill/ (not part of this project).
    total = 0
    for line in result.stdout.splitlines():
        m = re.match(r"^tests/([\w/.]+)\.py:\s*(\d+)\s*$", line)
        if m:
            path = m.group(1)
            if path.startswith("skill/"):
                continue
            total += int(m.group(2))
    return total


def list_demos() -> List[Dict[str, str]]:
    """Discover examples/demo_*.py and compare_*.py. Purpose is preserved from
    the existing state.json when possible; new scripts get a stub purpose.

    Filters out scripts that belong to a parallel feature (e.g.
    ``demo_skillops_*``) and not to this attention-residuals spec.
    If you add a new demo for this spec, name it ``demo_<feature>.py``
    where ``<feature>`` is already referenced in this state's layers or
    open_actions."""
    examples = REPO_ROOT / "examples"
    scripts = sorted(
        p.stem for p in examples.glob("*.py")
        if p.stem != "__init__"
        and (p.stem.startswith("demo_") or p.stem.startswith("compare_"))
        and not p.stem.startswith("demo_skillops")
    )
    # Preserve existing purposes.
    old = _load_state().get("demos", [])
    old_map = {d["name"]: d.get("purpose", "") for d in old}
    return [{"name": s, "purpose": old_map.get(s, "(new — please add purpose)")}
            for s in scripts]


def list_docs() -> List[Dict[str, str]]:
    """Discover docs/*.md and docs/*/ (top-level markdown + directories)."""
    docs_dir = REPO_ROOT / "docs"
    entries: List[Dict[str, str]] = []
    # Top-level markdowns + the html knowledge base
    for p in sorted(docs_dir.iterdir()):
        if p.is_file() and p.suffix in {".md", ".html"}:
            entries.append({"path": f"docs/{p.name}", "purpose": ""})
        elif p.is_dir() and not p.name.startswith("."):
            entries.append({"path": f"docs/{p.name}/", "purpose": ""})
    # Preserve existing purposes.
    old = _load_state().get("docs", [])
    old_map = {d["path"]: d.get("purpose", "") for d in old}
    for e in entries:
        if old_map.get(e["path"]):
            e["purpose"] = old_map[e["path"]]
        else:
            e["purpose"] = "(new — please add purpose)"
    return entries


def public_api_symbols() -> List[str]:
    """Parse __all__ from attention_residuals/__init__.py."""
    init_path = REPO_ROOT / "attention_residuals" / "__init__.py"
    tree = ast.parse(init_path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    if isinstance(node.value, (ast.List, ast.Tuple)):
                        names: List[str] = []
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                names.append(elt.value)
                        return names
    return []


def _load_state() -> Dict[str, Any]:
    if not STATE_PATH.exists():
        return {}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def _set(d: Dict[str, Any], path: tuple, value: Any) -> None:
    cur = d
    for k in path[:-1]:
        cur = cur.setdefault(k, {})
    cur[path[-1]] = value


def compute_updates() -> Dict[str, Any]:
    demos = list_demos()
    return {
        ("repository", "head_commit_short"): git_head_short(),
        ("repository", "head_commit_subject"): git_head_subject(),
        ("health", "tests_total"): count_tests(),
        ("health", "demos_total"): len(demos),
        ("demos",): demos,
        ("docs",): list_docs(),
        ("public_api_symbols",): public_api_symbols(),
    }


def _diff(old_val: Any, new_val: Any) -> str:
    if old_val == new_val:
        return "(no change)"
    if isinstance(old_val, list) and isinstance(new_val, list):
        return f"list: {len(old_val)} → {len(new_val)} entries"
    return f"{old_val!r} → {new_val!r}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true",
                        help="Write changes back to state.json (otherwise dry-run).")
    args = parser.parse_args()

    state = _load_state()
    updates = compute_updates()

    print("=" * 78)
    print("V2 state.json regeneration report")
    print("=" * 78)
    print(f"Repo root : {REPO_ROOT}")
    print(f"State path: {STATE_PATH}")
    print(f"Mode      : {'WRITE' if args.write else 'DRY-RUN'}")
    print()

    print("Factual updates:")
    for path, new_val in updates.items():
        # walk state to get old value
        cur: Any = state
        for k in path:
            if isinstance(cur, dict) and k in cur:
                cur = cur[k]
            else:
                cur = None
                break
        tag = ".".join(path)
        print(f"  {tag:<40} {_diff(cur, new_val)}")

    print()
    print("Semantic fields (NOT touched by this script — reviewer-curated):")
    for key in ("hard_invariants", "pr_review_guardrails", "open_actions",
                "open_gaps", "layers", "closed_loops", "notes_for_next_agent"):
        n = len(state.get(key, [])) if isinstance(state.get(key), list) else "—"
        print(f"  {key:<40} entries: {n}")

    if not args.write:
        print()
        print("Dry run complete. Re-run with --write to persist.")
        return

    # Apply updates
    for path, new_val in updates.items():
        _set(state, path, new_val)

    STATE_PATH.write_text(
        json.dumps(state, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print()
    print(f"[OK] Written {STATE_PATH}")
    print("Remember to also manually update:")
    print("  - snapshot_date / snapshot_author at the top")
    print("  - any open_actions that got closed since the last snapshot")
    print("  - any purpose strings marked '(new — please add purpose)'")


if __name__ == "__main__":
    main()
