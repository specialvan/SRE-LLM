from __future__ import annotations

from pathlib import Path

from scripts.package_smoke import build_wheel_and_smoke_imports


def test_built_wheel_contains_and_imports_public_packages(tmp_path: Path):
    result = build_wheel_and_smoke_imports(tmp_path)

    assert result.wheel_path.exists()
    assert result.package_imports == ("starship", "sre_control")
    assert "starship/__init__.py" in result.wheel_members
    assert "sre_control/__init__.py" in result.wheel_members
