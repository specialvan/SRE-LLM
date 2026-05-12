"""Regression tests for project-wide invariant scanners."""

import subprocess
import sys
from pathlib import Path


def test_invariant_script_passes():
    root = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / "check_invariants.py")],
        capture_output=True,
        text=True,
        cwd=root,
        check=False,
    )

    assert result.returncode == 0, (
        "check_invariants.py failed\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
