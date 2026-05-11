# Patch 05 · CI Invariant 扫描

- **Action item**：[AI-11](../05-action-items.md#ai-11)
- **Target**：把 [INV-G2](../03-invariants-catalog.md#inv-g2)（唯一执行入口）变成可自动化检查。

## 动机

INV-G2 现在只靠代码 review 守。任何 PR 若在 planner / cbf / lyapunov 以外新引入 `dynamics.step` / `dyn.step` 调用，都可能悄悄绕过硬约束。

## 新建 `scripts/check_invariants.py`

```python
"""Static checks for project-wide invariants.

Run::

    python scripts/check_invariants.py

Exits 0 iff every invariant passes.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent.parent

# INV-G2: sanctioned callers of dynamics.step
ALLOWED_FILES_CONTAINING_STEP_CALL = {
    "auto_decide/planner.py",
    "auto_decide/cbf.py",
    "auto_decide/lyapunov.py",
    "auto_decide/reachable.py",
    "auto_decide/invariant.py",        # future (if uses finite-diff)
    "examples/compare_e2e_vs_structural.py",  # intentional bypass baseline
    "tests/test_dynamics.py",
}

STEP_PATTERNS = (
    re.compile(r"\bdynamics\.step\("),
    re.compile(r"\bdyn\.step\("),
    re.compile(r"\bself\.dynamics\.step\("),
)


def iter_python_files(root: Path) -> Iterable[Path]:
    for p in root.rglob("*.py"):
        if any(skip in p.parts for skip in (".venv", "__pycache__", "build", "dist")):
            continue
        yield p


def check_inv_g2() -> list[str]:
    """Check INV-G2: no unsanctioned callers of dynamics.step."""
    violations: list[str] = []
    for path in iter_python_files(ROOT):
        rel = path.relative_to(ROOT).as_posix()
        if rel in ALLOWED_FILES_CONTAINING_STEP_CALL:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for i, line in enumerate(text.splitlines(), start=1):
            for pat in STEP_PATTERNS:
                if pat.search(line):
                    violations.append(f"{rel}:{i}: {line.strip()}")
    return violations


def check_inv_g10_params_frozen() -> list[str]:
    """Check INV-G10: VehicleParams must remain a frozen dataclass."""
    types_file = (ROOT / "auto_decide" / "types.py").read_text(encoding="utf-8")
    if "@dataclass(frozen=True)" not in types_file:
        return ["auto_decide/types.py: VehicleParams must be @dataclass(frozen=True)"]
    # Best-effort: look for `class VehicleParams` directly following the decorator
    if not re.search(
        r"@dataclass\(frozen=True\)\s*\nclass\s+VehicleParams\b",
        types_file,
    ):
        return [
            "auto_decide/types.py: @dataclass(frozen=True) must directly precede "
            "class VehicleParams",
        ]
    return []


def check_inv_g9_lyapunov_pure_speed() -> list[str]:
    """Check INV-G9: Lyapunov V must not reference distance fields."""
    lyap = (ROOT / "auto_decide" / "lyapunov.py").read_text(encoding="utf-8")
    bad_tokens = ["d_min", "min_distance", "obstacle", "manifold.signed_distance"]
    class_body = lyap.split("class QuadraticLyapunov")[-1] if "class QuadraticLyapunov" in lyap else ""
    found = [tok for tok in bad_tokens if tok in class_body]
    if found:
        return [
            f"auto_decide/lyapunov.py: QuadraticLyapunov references distance-like "
            f"tokens {found} — INV-G9 violated, V must be pure speed-tracking."
        ]
    return []


def main() -> int:
    all_violations: list[str] = []

    print("[check] INV-G2  unique executor entry ...", end=" ")
    v = check_inv_g2()
    print(f"{'OK' if not v else 'FAIL'}")
    for line in v:
        all_violations.append(f"INV-G2: {line}")

    print("[check] INV-G10 VehicleParams frozen ...", end=" ")
    v = check_inv_g10_params_frozen()
    print(f"{'OK' if not v else 'FAIL'}")
    for line in v:
        all_violations.append(f"INV-G10: {line}")

    print("[check] INV-G9  Lyapunov V pure-speed ...", end=" ")
    v = check_inv_g9_lyapunov_pure_speed()
    print(f"{'OK' if not v else 'FAIL'}")
    for line in v:
        all_violations.append(f"INV-G9: {line}")

    if all_violations:
        print("\n=== Violations ===")
        for v in all_violations:
            print(" - " + v)
        return 1
    print("\nAll invariants pass.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

## 如何接入 pytest

在 `conftest.py` 或 `tests/test_invariants.py` 加：

```python
"""Runtime sanity: the grep-level invariants must hold."""
import subprocess
import sys
from pathlib import Path


def test_invariant_script_passes():
    root = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / "check_invariants.py")],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f"check_invariants.py failed.\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
```

## 验收

- `python scripts/check_invariants.py` 当前仓库返回 0；
- 故意加一条 `dynamics.step(...)` 到 `auto_decide/potential.py` 测试脚本会 FAIL；
- `pytest tests/test_invariants.py` 作为 CI 的一部分运行。

## 之后可以扩充的检查

- INV-G4: fallback `Control(0, -jerk_max)` 的构造字符串在 invariant.py 里出现（防止 refactor 把兜底换成别的）；
- INV-G8: 硬约束不软化——扫描 `loss` / `penalty` 关键字是否出现在 cbf.py / invariant.py 里（应该完全不出现）；
- INV-M-TRACE-1: `TRACE_SCHEMA_VERSION = "1.0"` 这一行是否被改动（bump 必须走 CHANGELOG）。
