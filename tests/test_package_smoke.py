from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts import package_smoke
from scripts.package_smoke import build_wheel_and_smoke_imports


def test_built_wheel_contains_and_imports_public_packages(tmp_path: Path):
    result = build_wheel_and_smoke_imports(tmp_path)

    assert result.wheel_path.exists()
    assert result.package_imports == ("starship", "sre_control")
    assert "starship/__init__.py" in result.wheel_members
    assert "sre_control/__init__.py" in result.wheel_members


def test_package_smoke_run_fails_loudly_on_timeout(monkeypatch: pytest.MonkeyPatch):
    def fake_run(*args: object, **kwargs: object):
        raise subprocess.TimeoutExpired(cmd=["python"], timeout=1)

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="command timed out"):
        package_smoke._run(["python"], Path("/repo"))
