from __future__ import annotations

import re
import tomllib
from pathlib import Path

import sre_control
import starship


def _project_version() -> str:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    return pyproject["project"]["version"]


def _spec_version() -> str:
    text = Path("PR-REQUIREMENTS.md").read_text(encoding="utf-8-sig")
    match = re.search(r"(?m)^version:\s*([0-9]+(?:\.[0-9]+)+)\s*$", text)
    assert match is not None
    return match.group(1)


def test_package_version_surfaces_move_together() -> None:
    package_version = _project_version()

    assert starship.__version__ == package_version
    assert sre_control.__version__ == package_version


def test_spec_ledger_version_is_not_a_package_release_promise() -> None:
    text = Path("PR-REQUIREMENTS.md").read_text(encoding="utf-8-sig")

    assert _spec_version() != _project_version()
    assert "spec / review-ledger" in text
    assert "Python package" in text
    assert "Git tag" in text
    assert "package / release artifact" in text
    assert not re.search(r"(?m)^head-commit:\s*[0-9a-f]{7,40}\s*$", text)
