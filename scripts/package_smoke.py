from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_IMPORTS = ("starship", "sre_control")


@dataclass(frozen=True)
class PackageSmokeResult:
    wheel_path: Path
    wheel_members: frozenset[str]
    package_imports: tuple[str, ...]


def _run(command: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        output = f"{result.stdout}\n{result.stderr}".strip()
        raise RuntimeError(f"command failed: {' '.join(command)}\n{output}")


def _build_wheel(repo_root: Path, work_dir: Path) -> Path:
    wheel_dir = work_dir / "wheelhouse"
    wheel_dir.mkdir(parents=True, exist_ok=True)
    _run(
        [sys.executable, "-m", "pip", "wheel", ".", "--no-deps", "--wheel-dir", str(wheel_dir)],
        cwd=repo_root,
    )
    wheels = sorted(wheel_dir.glob("*.whl"))
    if len(wheels) != 1:
        raise RuntimeError(f"expected one wheel in {wheel_dir}, found {len(wheels)}")
    return wheels[0]


def _smoke_import_from_wheel(repo_root: Path, wheel_path: Path) -> None:
    code = "\n".join(
        [
            "import importlib",
            f"packages = {PACKAGE_IMPORTS!r}",
            "for package in packages:",
            "    module = importlib.import_module(package)",
            "    assert module.__file__",
            "    assert '.whl' in module.__file__.replace('\\\\', '/')",
        ]
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(wheel_path)
    _run([sys.executable, "-c", code], cwd=wheel_path.parent, env=env)


def build_wheel_and_smoke_imports(
    work_dir: Path, repo_root: Path = REPO_ROOT
) -> PackageSmokeResult:
    wheel_path = _build_wheel(repo_root, work_dir)
    with zipfile.ZipFile(wheel_path) as wheel:
        members = frozenset(wheel.namelist())

    for package in PACKAGE_IMPORTS:
        init_path = f"{package}/__init__.py"
        if init_path not in members:
            raise RuntimeError(f"wheel is missing {init_path}")

    _smoke_import_from_wheel(repo_root, wheel_path)
    return PackageSmokeResult(
        wheel_path=wheel_path,
        wheel_members=members,
        package_imports=PACKAGE_IMPORTS,
    )


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="package-smoke-") as temp_dir:
        result = build_wheel_and_smoke_imports(Path(temp_dir))
    print(f"package smoke ok: {result.wheel_path.name}")


if __name__ == "__main__":
    main()
