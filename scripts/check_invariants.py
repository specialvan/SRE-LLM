"""Static checks for project-wide invariants.

Run:

    python scripts/check_invariants.py

The checks are intentionally lightweight. They catch easy-to-miss
contract drift before the heavier planner tests run.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent.parent

ALLOWED_STEP_CALLERS = {
    "auto_decide/cbf.py",
    "auto_decide/invariant.py",
    "auto_decide/lyapunov.py",
    "auto_decide/planner.py",
    "auto_decide/reachable.py",
    "examples/compare_e2e_vs_structural.py",
    "tests/test_dynamics.py",
}

SKIP_DIRS = {".git", ".venv", "__pycache__", "build", "dist", ".pytest_cache"}


def iter_python_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*.py"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


def _is_sanctioned_step_call(node: ast.Call) -> bool:
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr != "step":
        return False
    target = func.value
    if isinstance(target, ast.Name):
        return target.id in {"dyn", "dynamics"}
    if (
        isinstance(target, ast.Attribute)
        and target.attr == "dynamics"
        and isinstance(target.value, ast.Name)
        and target.value.id == "self"
    ):
        return True
    return False


def check_inv_g2() -> list[str]:
    """INV-G2: dynamics.step cannot be called from business paths."""
    violations: list[str] = []
    for path in iter_python_files(ROOT):
        rel = path.relative_to(ROOT).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        except SyntaxError as exc:
            violations.append(f"{rel}:{exc.lineno}: syntax error while scanning")
            continue

        if rel in ALLOWED_STEP_CALLERS:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _is_sanctioned_step_call(node):
                violations.append(f"{rel}:{node.lineno}: unauthorized dynamics.step call")
    return violations


def _class_source(path: Path, class_name: str) -> str:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=path.as_posix())
    lines = text.splitlines()
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            start = node.lineno
            if node.decorator_list:
                start = min(decorator.lineno for decorator in node.decorator_list)
            return "\n".join(lines[start - 1:node.end_lineno])
    return ""


def check_inv_g9_lyapunov_pure_speed() -> list[str]:
    """INV-G9: QuadraticLyapunov.V must stay pure speed-tracking."""
    source = _class_source(ROOT / "auto_decide" / "lyapunov.py", "QuadraticLyapunov")
    bad_tokens = ("d_min", "min_distance", "obstacle", "signed_distance")
    found = [token for token in bad_tokens if token in source]
    if found:
        return [
            "auto_decide/lyapunov.py: QuadraticLyapunov references "
            f"distance-like tokens {found}; V must remain pure speed-tracking"
        ]
    return []


def check_inv_g10_params_frozen() -> list[str]:
    """INV-G10: VehicleParams must remain a frozen dataclass."""
    source = _class_source(ROOT / "auto_decide" / "types.py", "VehicleParams")
    if not source:
        return ["auto_decide/types.py: class VehicleParams not found"]
    if not source.startswith("@dataclass(frozen=True)\nclass VehicleParams"):
        return [
            "auto_decide/types.py: VehicleParams must be directly decorated "
            "with @dataclass(frozen=True)"
        ]
    return []


def run_check(name: str, check) -> list[str]:
    print(f"[check] {name} ...", end=" ")
    violations = check()
    print("OK" if not violations else "FAIL")
    return [f"{name}: {item}" for item in violations]


def main() -> int:
    violations: list[str] = []
    violations.extend(run_check("INV-G2 unique executor entry", check_inv_g2))
    violations.extend(run_check("INV-G9 Lyapunov pure speed", check_inv_g9_lyapunov_pure_speed))
    violations.extend(run_check("INV-G10 VehicleParams frozen", check_inv_g10_params_frozen))

    if violations:
        print("\n=== Invariant Violations ===")
        for item in violations:
            print(f"- {item}")
        return 1

    print("\nAll invariant checks pass.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
