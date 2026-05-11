from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.append(node.module or "")
    return modules


def _is_under(module: str, package: str) -> bool:
    return module == package or module.startswith(f"{package}.")


def test_starship_does_not_import_sre_control():
    for path in (ROOT / "starship").rglob("*.py"):
        for module in _imported_modules(path):
            assert not _is_under(module, "sre_control"), (
                f"{path.relative_to(ROOT)} illegally imports {module}"
            )


def test_sre_event_schema_does_not_import_starship_layer():
    for module in _imported_modules(ROOT / "sre_control" / "events.py"):
        assert not _is_under(module, "starship"), (
            "sre_control/events.py must remain a migration-layer schema "
            f"without starship imports; found {module}"
        )
