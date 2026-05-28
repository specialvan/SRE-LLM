from __future__ import annotations

import hashlib
import os
import json
import re
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from scripts import control_center_browser_smoke


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_IMPORTS = ("starship", "sre_control")
PACKAGE_SMOKE_TIMEOUT_SECONDS = 120
CONTROL_CENTER_EVIDENCE_REPORT = REPO_ROOT / "analysis" / "artifacts" / "control-center-browser-evidence-report.json"
EXPECTED_CONTROL_CENTER_MANIFEST_PATHS = {
    "normal": "analysis/artifacts/control-center-browser-smoke-manifest.json",
    "backend_error": "analysis/artifacts/control-center-browser-error-smoke-manifest.json",
    "frontend_error": "analysis/artifacts/control-center-browser-frontend-error-smoke-manifest.json",
}
EXPECTED_CONTROL_CENTER_REPORT = {
    "contract": "control-center.v1 @ /api/control-center",
    "frontend_api_url": "/api/control-center",
    "health_status": "ok",
    "timeline": "12 rows / 12 ticks / 23 events",
}
EXPECTED_CONTROL_CENTER_CONTRACT_DEPTH_KEYS = (
    "top_level",
    "object_groups",
    "object_fields",
    "array_item_groups",
    "array_item_fields",
    "timeline_fields",
)


@dataclass(frozen=True)
class PackageSmokeResult:
    wheel_path: Path
    wheel_members: frozenset[str]
    package_imports: tuple[str, ...]


def _run(command: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=PACKAGE_SMOKE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"command timed out after {PACKAGE_SMOKE_TIMEOUT_SECONDS} seconds: "
            f"{' '.join(command)}"
        ) from exc
    if result.returncode != 0:
        output = f"{result.stdout}\n{result.stderr}".strip()
        raise RuntimeError(f"command failed: {' '.join(command)}\n{output}")


def _build_wheel(repo_root: Path, work_dir: Path) -> Path:
    wheel_dir = work_dir / "wheelhouse"
    wheel_dir.mkdir(parents=True, exist_ok=True)
    _run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            ".",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(wheel_dir),
        ],
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


def _artifact_record(path: Path, root: Path) -> dict[str, object]:
    data = path.read_bytes()
    return {
        "path": path.resolve().relative_to(root.resolve()).as_posix(),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def verify_control_center_evidence_report(
    path: Path = CONTROL_CENTER_EVIDENCE_REPORT,
    repo_root: Path = REPO_ROOT,
) -> str:
    if not path.exists():
        raise RuntimeError(f"control-center evidence report missing: {path}")
    report = json.loads(path.read_text(encoding="utf-8"))
    for key, expected in EXPECTED_CONTROL_CENTER_REPORT.items():
        if report.get(key) != expected:
            raise RuntimeError(
                f"control-center evidence report mismatch: {key} expected {expected!r}, got {report.get(key)!r}"
            )
    manifest_paths = report.get("manifest_paths")
    if manifest_paths != EXPECTED_CONTROL_CENTER_MANIFEST_PATHS:
        raise RuntimeError(
            "control-center evidence report mismatch: missing manifest provenance"
        )
    manifest_records = report.get("manifest_records")
    if not isinstance(manifest_records, dict):
        raise RuntimeError(
            "control-center evidence report mismatch: missing manifest records"
        )
    for key, expected_path in EXPECTED_CONTROL_CENTER_MANIFEST_PATHS.items():
        record = manifest_records.get(key)
        if not isinstance(record, dict) or record.get("path") != expected_path:
            raise RuntimeError(
                f"control-center evidence report mismatch: invalid manifest record for {key}"
            )
        if not isinstance(record.get("bytes"), int) or record["bytes"] <= 0:
            raise RuntimeError(
                f"control-center evidence report mismatch: invalid manifest record for {key}"
            )
        sha256 = record.get("sha256")
        if not isinstance(sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise RuntimeError(
                f"control-center evidence report mismatch: invalid manifest record for {key}"
            )
        actual_record = _artifact_record(repo_root / expected_path, repo_root)
        if record != actual_record:
            raise RuntimeError(
                f"control-center evidence report mismatch: stale manifest record for {key}"
            )
    control_center_browser_smoke.verify_evidence_manifest(
        repo_root / EXPECTED_CONTROL_CENTER_MANIFEST_PATHS["normal"]
    )
    control_center_browser_smoke.verify_error_evidence_manifest(
        repo_root / EXPECTED_CONTROL_CENTER_MANIFEST_PATHS["backend_error"]
    )
    control_center_browser_smoke.verify_frontend_error_evidence_manifest(
        repo_root / EXPECTED_CONTROL_CENTER_MANIFEST_PATHS["frontend_error"]
    )
    viewports = report.get("normal_viewports")
    if not isinstance(viewports, list) or not any(item.startswith("desktop:1440x960:dom") for item in viewports) or not any(item.startswith("mobile:390x844:dom") for item in viewports):
        raise RuntimeError("control-center evidence report mismatch: missing desktop/mobile viewport evidence")
    error_viewport = report.get("error_viewport")
    if not isinstance(error_viewport, str) or not error_viewport.startswith("desktop:1440x960:dom"):
        raise RuntimeError("control-center evidence report mismatch: missing contract-error viewport evidence")
    frontend_error_viewport = report.get("frontend_error_viewport")
    if not isinstance(frontend_error_viewport, str) or not frontend_error_viewport.startswith("desktop:1440x960:dom"):
        raise RuntimeError("control-center evidence report mismatch: missing frontend-contract-error viewport evidence")
    contract_depth = report.get("contract_depth")
    if not isinstance(contract_depth, dict):
        raise RuntimeError("control-center evidence report mismatch: missing contract-depth evidence")
    for key in EXPECTED_CONTROL_CENTER_CONTRACT_DEPTH_KEYS:
        value = contract_depth.get(key)
        if not isinstance(value, int) or value <= 0:
            raise RuntimeError(
                f"control-center evidence report mismatch: invalid contract-depth evidence for {key}"
            )
    contract_depth_summary = " ".join(
        f"{key}:{contract_depth[key]}" for key in EXPECTED_CONTROL_CENTER_CONTRACT_DEPTH_KEYS
    )
    return (
        f"{report['contract']}; desktop+mobile; error={error_viewport}; "
        f"frontend_error={frontend_error_viewport}; "
        "manifest_records=normal+backend_error+frontend_error; "
        "manifest_replay=normal+backend_error+frontend_error; "
        f"contract_depth={contract_depth_summary}"
    )


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="package-smoke-") as temp_dir:
        result = build_wheel_and_smoke_imports(Path(temp_dir))
    control_center_summary = verify_control_center_evidence_report()
    print(f"package smoke ok: {result.wheel_path.name}")
    print(f"control-center evidence ok: {control_center_summary}")


if __name__ == "__main__":
    main()
