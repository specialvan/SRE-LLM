from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import subprocess
import urllib.request
import zlib
from dataclasses import dataclass
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

from scripts.control_center_server import (
    API_PATH,
    ControlCenterHandler,
    require_loopback_bind_host,
    validate_control_center_payload,
)
from analysis.control_center_data import build_control_center_payload

try:  # pragma: no cover - exercised when optional dependency is installed.
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - deterministic branch covered by tests via monkeypatch.
    sync_playwright = None


@dataclass(frozen=True)
class SmokeViewport:
    name: str
    width: int
    height: int


@dataclass(frozen=True)
class LiveApiResponse:
    payload: dict
    metadata: dict


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCREENSHOT = ROOT / "analysis" / "artifacts" / "control-center-browser-smoke.png"
DEFAULT_DOM_DUMP = ROOT / "analysis" / "artifacts" / "control-center-browser-smoke.html"
DEFAULT_ERROR_SCREENSHOT = ROOT / "analysis" / "artifacts" / "control-center-browser-error-smoke.png"
DEFAULT_ERROR_DOM_DUMP = ROOT / "analysis" / "artifacts" / "control-center-browser-error-smoke.html"
DEFAULT_FRONTEND_ERROR_SCREENSHOT = ROOT / "analysis" / "artifacts" / "control-center-browser-frontend-error-smoke.png"
DEFAULT_FRONTEND_ERROR_DOM_DUMP = ROOT / "analysis" / "artifacts" / "control-center-browser-frontend-error-smoke.html"
DEFAULT_API_SNAPSHOT = ROOT / "analysis" / "artifacts" / "control-center-browser-smoke-api.json"
DEFAULT_MANIFEST = ROOT / "analysis" / "artifacts" / "control-center-browser-smoke-manifest.json"
DEFAULT_ERROR_MANIFEST = ROOT / "analysis" / "artifacts" / "control-center-browser-error-smoke-manifest.json"
DEFAULT_FRONTEND_ERROR_MANIFEST = ROOT / "analysis" / "artifacts" / "control-center-browser-frontend-error-smoke-manifest.json"
DEFAULT_REPORT_JSON = ROOT / "analysis" / "artifacts" / "control-center-browser-evidence-report.json"
SMOKE_VIEWPORTS = [
    SmokeViewport("desktop", 1440, 960),
    SmokeViewport("mobile", 390, 844),
]
SYSTEM_BROWSER_CANDIDATES = [
    Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
    Path("C:/Program Files/Microsoft/Edge/Application/msedge.exe"),
    Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
    Path("C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
]
REQUIRED_SELECTORS = [
    "#frontend-contract-version",
    "#series-chart svg",
    "#timeline-list .timeline-row",
    "#tick-event-details",
    "#tick-alloc-shares",
    "#event-kind-lens-list button",
    "#safety-budget-list .budget-item",
    "#capacity-budget-list .capacity-item",
]



def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a real-browser smoke test against the control center."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument(
        "--allow-non-loopback",
        action="store_true",
        help="Allow binding the temporary smoke server to a non-loopback host.",
    )
    parser.add_argument("--screenshot", type=Path, default=DEFAULT_SCREENSHOT)
    parser.add_argument("--dom-dump", type=Path, default=DEFAULT_DOM_DUMP)
    parser.add_argument("--api-snapshot", type=Path, default=DEFAULT_API_SNAPSHOT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--error-manifest", type=Path, default=DEFAULT_ERROR_MANIFEST)
    parser.add_argument("--frontend-error-manifest", type=Path, default=DEFAULT_FRONTEND_ERROR_MANIFEST)
    parser.add_argument(
        "--verify-manifest",
        type=Path,
        help="Replay an existing evidence manifest without starting the browser smoke server.",
    )
    parser.add_argument(
        "--verify-error-manifest",
        type=Path,
        help="Replay an existing contract-error evidence manifest without starting the browser smoke server.",
    )
    parser.add_argument(
        "--verify-frontend-error-manifest",
        type=Path,
        help="Replay an existing frontend-contract-error evidence manifest without starting the browser smoke server.",
    )
    parser.add_argument(
        "--verify-all-manifests",
        action="store_true",
        help="Replay the normal, backend contract-error, and frontend contract-error evidence manifests without starting the browser smoke server.",
    )
    parser.add_argument(
        "--report-manifests",
        action="store_true",
        help="Replay all evidence manifests and print a compact integration evidence report.",
    )
    parser.add_argument("--report-json", type=Path, default=DEFAULT_REPORT_JSON)
    parser.add_argument("--browser-path", type=Path)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument(
        "--expect-contract-error",
        action="store_true",
        help="Serve a deliberately invalid API payload and assert the frontend renders the failure.",
    )
    parser.add_argument(
        "--expect-frontend-contract-error",
        action="store_true",
        help="Serve a malformed HTTP-200 API payload and assert the frontend validator renders the failure.",
    )
    return parser.parse_args(argv)


def find_system_browser() -> Path | None:
    for candidate in SYSTEM_BROWSER_CANDIDATES:
        if candidate.exists():
            return candidate
    return None










def _artifact_ref(path: Path, base_dir: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return resolved.relative_to(base_dir.resolve()).as_posix()


def _artifact_record(path: Path, base_dir: Path | None = None) -> dict:
    base = path.parent if base_dir is None else base_dir
    path = path.resolve()
    data = path.read_bytes()
    return {
        "path": _artifact_ref(path, base),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _resolve_manifest_artifact(manifest_path: Path, path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        raise AssertionError(f"absolute artifact path is not portable: {path_text}")
    if any(part == ".." for part in path.parts):
        raise AssertionError(f"parent traversal in artifact path: {path_text}")
    manifest_candidate = (manifest_path.resolve().parent / path).resolve()
    if manifest_candidate.exists():
        return manifest_candidate
    repo_candidate = (ROOT / path).resolve()
    try:
        repo_candidate.relative_to(ROOT)
    except ValueError as exc:  # pragma: no cover - guarded by '..' check.
        raise AssertionError(f"artifact path escapes repository: {path_text}") from exc
    return repo_candidate


def _png_metadata(data: bytes) -> dict:
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise AssertionError("screenshot is not a PNG")
    offset = 8
    width = height = None
    color_type = None
    idat = bytearray()
    while offset + 8 <= len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        chunk_data = data[offset + 8 : offset + 8 + length]
        offset += 12 + length
        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type = struct.unpack(">IIBB", chunk_data[:10])
            if bit_depth != 8 or color_type not in {2, 6}:
                raise AssertionError("screenshot PNG must be 8-bit RGB or RGBA")
        elif chunk_type == b"IDAT":
            idat.extend(chunk_data)
        elif chunk_type == b"IEND":
            break
    if width is None or height is None:
        raise AssertionError("screenshot PNG missing IHDR")
    channels = 4 if color_type == 6 else 3
    raw = zlib.decompress(bytes(idat))
    stride = width * channels
    pixels = bytearray()
    previous = bytearray(stride)
    offset = 0
    for _ in range(height):
        filter_type = raw[offset]
        offset += 1
        row = bytearray(raw[offset : offset + stride])
        offset += stride
        if filter_type == 1:
            for index in range(stride):
                row[index] = (row[index] + (row[index - channels] if index >= channels else 0)) & 0xFF
        elif filter_type == 2:
            for index in range(stride):
                row[index] = (row[index] + previous[index]) & 0xFF
        elif filter_type == 3:
            for index in range(stride):
                left = row[index - channels] if index >= channels else 0
                row[index] = (row[index] + ((left + previous[index]) // 2)) & 0xFF
        elif filter_type == 4:
            for index in range(stride):
                left = row[index - channels] if index >= channels else 0
                up = previous[index]
                up_left = previous[index - channels] if index >= channels else 0
                predictor = left + up - up_left
                choices = (abs(predictor - left), abs(predictor - up), abs(predictor - up_left))
                paeth = (left, up, up_left)[choices.index(min(choices))]
                row[index] = (row[index] + paeth) & 0xFF
        elif filter_type != 0:
            raise AssertionError(f"unsupported PNG filter: {filter_type}")
        pixels.extend(row)
        previous = row
    first_pixel = bytes(pixels[:channels])
    blank = all(
        bytes(pixels[index : index + channels]) == first_pixel
        for index in range(0, len(pixels), channels)
    )
    return {"width": width, "height": height, "blank": blank}


def _screenshot_record(path: Path, base_dir: Path | None = None) -> dict:
    record = _artifact_record(path, base_dir=base_dir)
    record["png"] = _png_metadata(path.read_bytes())
    return record


def write_evidence_manifest(
    path: Path,
    *,
    url: str,
    payload: dict,
    api_snapshot: Path,
    viewport_artifacts: list[dict],
    api_response: dict | None = None,
    health_response: dict | None = None,
    frontend_response: dict | None = None,
) -> None:
    base_dir = path.resolve().parent
    default_health_response = {
        "status": 200,
        "content_type": "application/json; charset=utf-8",
        "cache_control": "no-store",
        "contract_header": payload["frontend_contract"]["version"],
        "api_header": payload["frontend_contract"]["api_path"],
        "payload": {
            "status": "ok",
            "contract": {
                "version": payload["frontend_contract"]["version"],
                "api_path": payload["frontend_contract"]["api_path"],
            },
            "routes": {"frontend": "/control-center", "api": payload["frontend_contract"]["api_path"]},
        },
    }
    manifest = {
        "url": url,
        "contract": {
            "version": payload["frontend_contract"]["version"],
            "api_path": payload["frontend_contract"]["api_path"],
        },
        "summary": {
            "ticks": payload["summary"]["ticks"],
            "timeline_rows": len(payload["timeline"]),
            "events_total": payload["events"]["total"],
        },
        "api_response": api_response
        or {
            "status": 200,
            "content_type": "application/json; charset=utf-8",
            "cache_control": "no-store",
            "contract_header": payload["frontend_contract"]["version"],
            "api_header": payload["frontend_contract"]["api_path"],
        },
        "health_response": health_response or default_health_response,
        "frontend_response": frontend_response
        or {
            "status": 200,
            "content_type": "text/html; charset=utf-8",
            "cache_control": "no-store",
            "contract_header": payload["frontend_contract"]["version"],
            "api_header": payload["frontend_contract"]["api_path"],
            "api_url": payload["frontend_contract"]["api_path"],
        },
        "api_snapshot": _artifact_record(api_snapshot, base_dir=base_dir),
        "viewports": [],
    }
    for item in viewport_artifacts:
        viewport = item["viewport"]
        manifest["viewports"].append(
            {
                "name": viewport.name,
                "width": viewport.width,
                "height": viewport.height,
                "screenshot": _screenshot_record(item["screenshot"], base_dir=base_dir),
                "dom_dump": _artifact_record(item["dom_dump"], base_dir=base_dir),
            }
        )
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        ) + "\n",
        encoding="utf-8",
    )


def write_error_evidence_manifest(
    path: Path,
    *,
    url: str,
    viewport: SmokeViewport,
    screenshot: Path,
    dom_dump: Path,
) -> None:
    base_dir = path.resolve().parent
    manifest = {
        "mode": "contract-error",
        "url": url,
        "viewport": {"name": viewport.name, "width": viewport.width, "height": viewport.height},
        "screenshot": _screenshot_record(screenshot, base_dir=base_dir),
        "dom_dump": _artifact_record(dom_dump, base_dir=base_dir),
    }
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        ) + "\n",
        encoding="utf-8",
    )


def write_frontend_error_evidence_manifest(
    path: Path,
    *,
    url: str,
    viewport: SmokeViewport,
    screenshot: Path,
    dom_dump: Path,
) -> None:
    base_dir = path.resolve().parent
    manifest = {
        "mode": "frontend-contract-error",
        "url": url,
        "viewport": {"name": viewport.name, "width": viewport.width, "height": viewport.height},
        "screenshot": _screenshot_record(screenshot, base_dir=base_dir),
        "dom_dump": _artifact_record(dom_dump, base_dir=base_dir),
    }
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        ) + "\n",
        encoding="utf-8",
    )



def _verify_artifact_record(record: dict, manifest_path: Path) -> Path:
    path = _resolve_manifest_artifact(manifest_path, record["path"])
    if not path.exists():
        raise AssertionError(f"manifest artifact missing: {path}")
    data = path.read_bytes()
    actual = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    if record.get("bytes") != actual["bytes"] or record.get("sha256") != actual["sha256"]:
        raise AssertionError(
            "manifest artifact mismatch: "
            f"{path} expected bytes={record.get('bytes')} sha256={record.get('sha256')}, "
            f"got bytes={actual['bytes']} sha256={actual['sha256']}"
        )
    return path


def _verify_screenshot_record(
    record: dict,
    *,
    expected_width: int,
    expected_height: int,
    manifest_path: Path,
) -> Path:
    path = _verify_artifact_record(record, manifest_path)
    actual_png = _png_metadata(path.read_bytes())
    if record.get("png") != actual_png:
        raise AssertionError("manifest screenshot PNG metadata does not match artifact")
    if actual_png["width"] != expected_width or actual_png["height"] != expected_height:
        raise AssertionError(
            "manifest screenshot dimensions do not match viewport: "
            f"expected {expected_width}x{expected_height}, got {actual_png['width']}x{actual_png['height']}"
        )
    if actual_png["blank"]:
        raise AssertionError("blank screenshot artifact")
    return path


def verify_evidence_manifest(path: Path) -> None:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    api_snapshot_path = _verify_artifact_record(manifest["api_snapshot"], path)
    payload = json.loads(api_snapshot_path.read_text(encoding="utf-8"))
    errors = validate_control_center_payload(payload)
    if errors:
        raise AssertionError(f"manifest API snapshot violates contract: {errors}")
    expected_contract = {
        "version": payload["frontend_contract"]["version"],
        "api_path": payload["frontend_contract"]["api_path"],
    }
    if manifest.get("contract") != expected_contract:
        raise AssertionError("manifest contract does not match API snapshot")
    expected_summary = {
        "ticks": payload["summary"]["ticks"],
        "timeline_rows": len(payload["timeline"]),
        "events_total": payload["events"]["total"],
    }
    if manifest.get("summary") != expected_summary:
        raise AssertionError("manifest summary does not match API snapshot")
    expected_api_response = {
        "status": 200,
        "content_type": "application/json; charset=utf-8",
        "cache_control": "no-store",
        "contract_header": expected_contract["version"],
        "api_header": expected_contract["api_path"],
    }
    if manifest.get("api_response") != expected_api_response:
        raise AssertionError("manifest API response metadata does not match API snapshot contract")
    expected_health_response = {
        **expected_api_response,
        "payload": {
            "status": "ok",
            "contract": expected_contract,
            "routes": {"frontend": "/control-center", "api": expected_contract["api_path"]},
        },
    }
    if manifest.get("health_response") != expected_health_response:
        raise AssertionError("manifest health response does not match API snapshot contract")
    expected_frontend_response = {
        "status": 200,
        "content_type": "text/html; charset=utf-8",
        "cache_control": "no-store",
        "contract_header": expected_contract["version"],
        "api_header": expected_contract["api_path"],
        "api_url": expected_contract["api_path"],
    }
    if manifest.get("frontend_response") != expected_frontend_response:
        raise AssertionError("manifest frontend response does not match API snapshot contract")
    for viewport in manifest.get("viewports", []):
        _verify_screenshot_record(
            viewport["screenshot"],
            expected_width=viewport["width"],
            expected_height=viewport["height"],
            manifest_path=path,
        )
        dom_path = _verify_artifact_record(viewport["dom_dump"], path)
        dom = dom_path.read_text(encoding="utf-8")
        _assert_dumped_dom(
            dom,
            payload,
            context=f"normal manifest {viewport.get('name', 'unknown')} DOM {dom_path} from {path}",
        )
    if not manifest.get("viewports"):
        raise AssertionError("manifest has no viewport artifacts")


def verify_error_evidence_manifest(path: Path) -> None:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("mode") != "contract-error":
        raise AssertionError("error manifest mode mismatch")
    viewport = manifest["viewport"]
    _verify_screenshot_record(
        manifest["screenshot"],
        expected_width=viewport["width"],
        expected_height=viewport["height"],
        manifest_path=path,
    )
    dom_path = _verify_artifact_record(manifest["dom_dump"], path)
    dom = dom_path.read_text(encoding="utf-8")
    _assert_error_dom(dom)


def verify_frontend_error_evidence_manifest(path: Path) -> None:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("mode") != "frontend-contract-error":
        raise AssertionError("frontend error manifest mode mismatch")
    viewport = manifest["viewport"]
    _verify_screenshot_record(
        manifest["screenshot"],
        expected_width=viewport["width"],
        expected_height=viewport["height"],
        manifest_path=path,
    )
    dom_path = _verify_artifact_record(manifest["dom_dump"], path)
    dom = dom_path.read_text(encoding="utf-8")
    _assert_frontend_contract_error_dom(dom)


def build_evidence_report(
    manifest_path: Path,
    error_manifest_path: Path,
    frontend_error_manifest_path: Path,
) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    error_manifest = json.loads(error_manifest_path.read_text(encoding="utf-8"))
    frontend_error_manifest = json.loads(frontend_error_manifest_path.read_text(encoding="utf-8"))
    api_snapshot_path = _resolve_manifest_artifact(
        manifest_path,
        manifest["api_snapshot"]["path"],
    )
    api_snapshot = json.loads(api_snapshot_path.read_text(encoding="utf-8"))
    frontend_contract = api_snapshot["frontend_contract"]
    object_required_fields = frontend_contract["object_required_fields"]
    array_item_required_fields = frontend_contract["array_item_required_fields"]
    contract_depth = {
        "top_level": len(frontend_contract["top_level_required_fields"]),
        "object_groups": len(object_required_fields),
        "object_fields": sum(len(fields) for fields in object_required_fields.values()),
        "array_item_groups": len(array_item_required_fields),
        "array_item_fields": sum(len(fields) for fields in array_item_required_fields.values()),
        "timeline_fields": len(frontend_contract["timeline_required_fields"]),
    }
    contract = manifest["contract"]
    summary = manifest["summary"]
    normal_viewports = []
    for viewport in manifest["viewports"]:
        png = viewport["screenshot"]["png"]
        normal_viewports.append(
            f"{viewport['name']}:{png['width']}x{png['height']}:dom{viewport['dom_dump']['bytes']}"
        )
    error_viewport = error_manifest["viewport"]
    error_png = error_manifest["screenshot"]["png"]
    frontend_error_viewport = frontend_error_manifest["viewport"]
    frontend_error_png = frontend_error_manifest["screenshot"]["png"]
    return {
        "contract": f"{contract['version']} @ {contract['api_path']}",
        "manifest_paths": {
            "normal": _report_manifest_path(manifest_path),
            "backend_error": _report_manifest_path(error_manifest_path),
            "frontend_error": _report_manifest_path(frontend_error_manifest_path),
        },
        "manifest_records": {
            "normal": _report_manifest_record(manifest_path),
            "backend_error": _report_manifest_record(error_manifest_path),
            "frontend_error": _report_manifest_record(frontend_error_manifest_path),
        },
        "frontend_api_url": manifest["frontend_response"]["api_url"],
        "health_status": manifest["health_response"]["payload"]["status"],
        "timeline": f"{summary['timeline_rows']} rows / {summary['ticks']} ticks / {summary['events_total']} events",
        "normal_viewports": normal_viewports,
        "error_viewport": f"{error_viewport['name']}:{error_png['width']}x{error_png['height']}:dom{error_manifest['dom_dump']['bytes']}",
        "frontend_error_viewport": f"{frontend_error_viewport['name']}:{frontend_error_png['width']}x{frontend_error_png['height']}:dom{frontend_error_manifest['dom_dump']['bytes']}",
        "contract_depth": contract_depth,
    }


def _report_manifest_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def _report_manifest_record(path: Path) -> dict:
    return _artifact_record(path, base_dir=path.parent)


def format_evidence_report(report: dict) -> str:
    manifest_paths = report.get("manifest_paths", {})
    manifest_records = report.get("manifest_records", {})
    return (
        "evidence report:\n"
        f"contract={report['contract']}\n"
        f"frontend_api_url={report['frontend_api_url']} health={report['health_status']}\n"
        f"timeline={report['timeline']}\n"
        f"normal={', '.join(report['normal_viewports'])}\n"
        f"error={report['error_viewport']}\n"
        f"frontend_error={report['frontend_error_viewport']}\n"
        "manifest_paths="
        + " ".join(f"{key}:{manifest_paths[key]}" for key in ("normal", "backend_error", "frontend_error"))
        + "\n"
        "manifest_records="
        + " ".join(
            f"{key}:{manifest_records[key]['bytes']}:{manifest_records[key]['sha256'][:12]}"
            for key in ("normal", "backend_error", "frontend_error")
        )
        + "\n"
        "manifest_replay=normal+backend_error+frontend_error\n"
        "contract_depth="
        + " ".join(f"{key}:{value}" for key, value in report["contract_depth"].items())
    )

def write_api_snapshot(path: Path, payload: dict) -> None:
    errors = validate_control_center_payload(payload)
    if errors:
        raise AssertionError(f"live API payload violates contract: {errors}")
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        ) + "\n",
        encoding="utf-8",
    )

def _fetch_live_json_response(url: str) -> LiveApiResponse:
    host = url.split("//", 1)[1].split("/", 1)[0]
    request = urllib.request.Request(url, headers={"Host": host})
    with urllib.request.urlopen(request, timeout=10) as response:
        if response.status != 200:
            raise AssertionError(f"live API payload fetch failed: HTTP {response.status}")
        payload = json.loads(response.read().decode("utf-8"))
        return LiveApiResponse(
            payload=payload,
            metadata={
                "status": response.status,
                "content_type": response.getheader("Content-Type"),
                "cache_control": response.getheader("Cache-Control"),
                "contract_header": response.getheader("X-Control-Center-Contract"),
                "api_header": response.getheader("X-Control-Center-API"),
            },
        )


def fetch_live_control_center_api_response(control_center_url: str) -> LiveApiResponse:
    api_url = control_center_url.rsplit("/", 1)[0] + API_PATH
    return _fetch_live_json_response(api_url)


def fetch_live_control_center_health_response(control_center_url: str) -> LiveApiResponse:
    health_url = control_center_url.rsplit("/", 1)[0] + f"{API_PATH}/health"
    return _fetch_live_json_response(health_url)


def fetch_live_control_center_frontend_response(control_center_url: str) -> dict:
    host = control_center_url.split("//", 1)[1].split("/", 1)[0]
    request = urllib.request.Request(control_center_url, headers={"Host": host})
    with urllib.request.urlopen(request, timeout=10) as response:
        if response.status != 200:
            raise AssertionError(f"live frontend fetch failed: HTTP {response.status}")
        html = response.read().decode("utf-8")
        match = re.search(r'const\s+API_URL\s*=\s*"(?P<api>[^"]+)"', html)
        if not match:
            raise AssertionError("live frontend did not declare API_URL")
        return {
            "status": response.status,
            "content_type": response.getheader("Content-Type"),
            "cache_control": response.getheader("Cache-Control"),
            "contract_header": response.getheader("X-Control-Center-Contract"),
            "api_header": response.getheader("X-Control-Center-API"),
            "api_url": match.group("api"),
        }


def fetch_live_control_center_payload(control_center_url: str) -> dict:
    return fetch_live_control_center_api_response(control_center_url).payload

def _viewport_artifact_path(path: Path, viewport: SmokeViewport) -> Path:
    return path.with_name(f"{path.stem}-{viewport.name}{path.suffix}")

def _start_server(
    host: str,
    port: int,
    handler: type[ControlCenterHandler] = ControlCenterHandler,
    *,
    allow_non_loopback: bool = False,
) -> tuple[ThreadingHTTPServer, threading.Thread]:
    require_loopback_bind_host(host, allow_non_loopback=allow_non_loopback)
    server = ThreadingHTTPServer((host, port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _run_browser_smoke(
    *,
    url: str,
    screenshot_path: Path,
    dom_dump_path: Path,
    headed: bool,
    viewport: SmokeViewport,
    payload: dict | None = None,
) -> None:
    assert sync_playwright is not None
    screenshot_path = screenshot_path.resolve()
    dom_dump_path = dom_dump_path.resolve()
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    dom_dump_path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not headed)
        page = browser.new_page(viewport={"width": viewport.width, "height": viewport.height})
        errors: list[str] = []
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
        page.goto(url, wait_until="networkidle")
        for selector in REQUIRED_SELECTORS:
            page.locator(selector).first.wait_for(state="visible", timeout=10_000)

        contract_text = page.locator("#frontend-contract-version").inner_text()
        if "control-center.v1" not in contract_text:
            raise AssertionError(f"frontend contract version not rendered: {contract_text}")

        rows = page.locator("#timeline-list .timeline-row")
        if rows.count() < 2:
            raise AssertionError("timeline did not render multiple rows")
        rows.nth(1).click()

        event_buttons = page.locator("#event-kind-lens-list button")
        if event_buttons.count() < 1:
            raise AssertionError("event kind lens controls did not render")
        event_buttons.nth(0).click()

        if errors:
            raise AssertionError(f"browser console errors: {errors}")
        dom = page.content()
        dom_dump_path.write_text(dom, encoding="utf-8")
        _assert_dumped_dom(dom, payload)
        page.screenshot(path=str(screenshot_path), full_page=True)
        browser.close()




def build_broken_control_center_payload() -> dict:
    payload = build_control_center_payload()
    payload = dict(payload)
    timeline = [dict(row) for row in payload["timeline"]]
    if timeline:
        timeline[0].pop("observed_rps", None)
    payload["timeline"] = timeline
    return payload


def build_frontend_broken_control_center_payload() -> dict:
    payload = build_control_center_payload()
    payload = dict(payload)
    series = dict(payload["series"])
    series["replicas"] = list(series["replicas"][:-1])
    payload["series"] = series
    return payload


class BrokenContractHandler(ControlCenterHandler):
    def do_GET(self) -> None:
        if self.path == API_PATH:
            self._serve_json(
                {
                    "error": "control_center_contract_violation",
                    "details": validate_control_center_payload(
                        build_broken_control_center_payload()
                    ),
                },
                500,
            )
            return
        super().do_GET()


class FrontendBrokenContractHandler(ControlCenterHandler):
    def do_GET(self) -> None:
        if self.path == API_PATH:
            self._serve_json(build_frontend_broken_control_center_payload(), 200)
            return
        super().do_GET()



def _normalize_dom_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _text_by_id(dom: str, element_id: str) -> str | None:
    match = re.search(
        rf'<[^>]*id="{re.escape(element_id)}"[^>]*>(?P<text>.*?)</[^>]+>',
        dom,
        re.DOTALL,
    )
    return _normalize_dom_text(match.group("text")) if match else None


def _fmt(value: float | int) -> str:
    return f"{float(value):.2f}".rstrip("0").rstrip(".")


def _assert_payload_values_rendered(dom: str, payload: dict) -> None:
    summary = payload["summary"]
    timeline = payload["timeline"]
    events = payload["events"]
    first = timeline[0]
    expected_by_id = {
        "frontend-contract-version": f"{payload['frontend_contract']['version']} · {payload['frontend_contract']['api_path']}",
        "bar-ticks": str(summary["ticks"]),
        "bar-degraded": str(summary["degraded_ticks"]),
        "bar-events": f"{_fmt(summary['event_visible_fraction'] * 100)}%",
        "bar-canary": f"{_fmt(summary['canary_share_pct'])}%",
        "bar-replicas": str(summary["current_replicas"]),
        "metric-peak": str(summary["peak_forecast_rps"]),
        "timeline-meta": f"{len(timeline)} / {len(timeline)} 拍",
        "events-meta": f"{events['distinct_kinds']} 类事件 · {events['total']} 条",
    }
    mismatches = []
    for element_id, expected in expected_by_id.items():
        actual = _text_by_id(dom, element_id)
        if actual != expected:
            mismatches.append(f"#{element_id} expected {expected!r}, got {actual!r}")

    required_fragments = [
        f"{first['replicas_next']} 个副本 · 观测 {first['observed_rps']:.0f} RPS",
        f"预测 {first['forecast_rps']:.0f} RPS",
        f"{first['pool_connections']}<br>连接",
    ]
    for fragment in required_fragments:
        if fragment not in dom:
            mismatches.append(f"missing timeline fragment {fragment!r}")
    selected_match = re.search(r'data-smoke-selected-tick="(?P<index>\d+)"', dom)
    if selected_match:
        selected_index = int(selected_match.group("index"))
        if selected_index >= len(timeline):
            if len(timeline) > 1:
                mismatches.append(f"selected tick {selected_index} is outside payload timeline")
        else:
            selected = timeline[selected_index]
            selected_fragments = []
            for event in selected.get("event_details", []):
                selected_fragments.extend(
                    [
                        str(event["kind"]),
                        f"阶段：{event['stage']} · {event['detail']}",
                        f"安全动作：{event['safe_action']}",
                    ]
                )
            selected_fragments.extend(f"{share:.2f} RPS" for share in selected.get("alloc_shares", []))
            for fragment in selected_fragments:
                if fragment not in dom:
                    mismatches.append(f"selected tick DOM missing {fragment!r}")
    if mismatches:
        raise AssertionError("frontend DOM does not match backend payload: " + "; ".join(mismatches))

def _dom_assertion_message(message: str, context: str | None) -> str:
    if context is None:
        return message
    return (
        f"{context}: {message}. Regenerate with "
        "python -m scripts.control_center_browser_smoke --report-manifests "
        "--report-json analysis/artifacts/control-center-browser-evidence-report.json"
    )


def _raise_dom_assertion(message: str, context: str | None) -> None:
    raise AssertionError(_dom_assertion_message(message, context))


def _assert_dumped_dom(
    dom: str,
    payload: dict | None = None,
    *,
    context: str | None = None,
) -> None:
    hero_subtitle = re.search(r'<p id="hero-subtitle">(?P<text>.*?)</p>', dom, re.DOTALL)
    if hero_subtitle and (
        "数据加载失败" in hero_subtitle.group("text")
        or "前端契约校验失败" in hero_subtitle.group("text")
    ):
        _raise_dom_assertion("browser DOM dump contains rendered frontend load failure", context)
    required_text = [
        "control-center.v1",
        "timeline-row",
        "series-chart",
        "tick-event-details",
        "tick-alloc-shares",
        "event-kind-lens-list",
        "safety-budget-list",
        "data-budget-focus",
        "capacity-budget-list",
        "data-capacity-focus",
    ]
    missing = [text for text in required_text if text not in dom]
    if missing:
        _raise_dom_assertion(f"browser DOM dump missing: {missing}", context)
    if 'data-smoke-kind-lens="kind"' not in dom or 'data-smoke-filter="events"' not in dom:
        _raise_dom_assertion("browser interaction probe did not run", context)
    if 'data-smoke-chart="pool"' not in dom or 'data-smoke-view="modules"' not in dom or 'data-smoke-budget="allocation"' not in dom:
        _raise_dom_assertion("browser interaction probe incomplete", context)
    if 'data-smoke-density="compact"' not in dom or 'data-smoke-share-hash="#share=' not in dom:
        _raise_dom_assertion("browser interaction probe did not exercise persistent view state", context)
    if 'data-smoke-reset-filter="all"' not in dom or 'data-smoke-reset-density="comfortable"' not in dom:
        _raise_dom_assertion("browser interaction probe did not verify dashboard reset", context)
    selected_tick = re.search(r'data-smoke-selected-tick="(?P<index>\d+)"', dom)
    if not selected_tick or int(selected_tick.group("index")) < 1:
        _raise_dom_assertion("browser interaction probe incomplete", context)
    visible_ticks = re.search(r'data-smoke-visible-ticks="(?P<count>\d+)"', dom)
    if not visible_ticks or int(visible_ticks.group("count")) < 1:
        _raise_dom_assertion("browser interaction probe did not leave visible ticks", context)
    if payload is not None:
        try:
            _assert_payload_values_rendered(dom, payload)
        except AssertionError as exc:
            _raise_dom_assertion(str(exc), context)


def _run_system_browser_smoke(
    *,
    url: str,
    browser_path: Path,
    screenshot_path: Path,
    dom_dump_path: Path,
    viewport: SmokeViewport = SMOKE_VIEWPORTS[0],
    payload: dict | None = None,
) -> None:
    screenshot_path = screenshot_path.resolve()
    dom_dump_path = dom_dump_path.resolve()
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    dom_dump_path.parent.mkdir(parents=True, exist_ok=True)
    user_data_dir = ROOT / "build" / "control-center-browser-smoke-profile"
    user_data_dir.mkdir(parents=True, exist_ok=True)

    command = [
        str(browser_path),
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        f"--user-data-dir={user_data_dir}",
        f"--window-size={viewport.width},{viewport.height}",
        "--virtual-time-budget=10000",
        "--run-all-compositor-stages-before-draw",
        f"--screenshot={screenshot_path}",
        "--dump-dom",
        f"{url}#smoke-interaction",
    ]
    result = subprocess.run(command, capture_output=True, timeout=60)
    stdout = result.stdout.decode("utf-8", errors="replace")
    stderr = result.stderr.decode("utf-8", errors="replace")
    if result.returncode != 0:
        raise AssertionError(
            "system browser smoke failed: "
            f"exit={result.returncode} stderr={stderr.strip()}"
        )

    dom_dump_path.write_text(stdout, encoding="utf-8")
    _assert_dumped_dom(stdout, payload)
    if not screenshot_path.exists() or screenshot_path.stat().st_size == 0:
        raise AssertionError(f"screenshot was not written: {screenshot_path}")




def _assert_error_dom(dom: str) -> None:
    hero_subtitle = re.search(r'<p id="hero-subtitle">(?P<text>.*?)</p>', dom, re.DOTALL)
    if not hero_subtitle or "数据加载失败" not in hero_subtitle.group("text"):
        raise AssertionError("browser DOM dump did not render backend contract failure")
    text = hero_subtitle.group("text")
    if "HTTP 500" not in text:
        raise AssertionError("browser DOM dump did not include backend HTTP 500 failure")
    if "control_center_contract_violation" not in text or "missing required frontend field" not in text:
        raise AssertionError("browser DOM dump did not include backend contract violation details")


def _assert_frontend_contract_error_dom(dom: str) -> None:
    hero_subtitle = re.search(r'<p id="hero-subtitle">(?P<text>.*?)</p>', dom, re.DOTALL)
    if not hero_subtitle or "数据加载失败" not in hero_subtitle.group("text"):
        raise AssertionError("browser DOM dump did not render frontend contract failure")
    text = hero_subtitle.group("text")
    if "前端契约校验失败" not in text:
        raise AssertionError("browser DOM dump did not include frontend contract validation failure")
    if "series.replicas length" not in text and "does not match timeline length" not in text:
        raise AssertionError("browser DOM dump did not include frontend contract validation details")


def _run_system_browser_frontend_contract_smoke(
    *,
    url: str,
    browser_path: Path,
    screenshot_path: Path,
    dom_dump_path: Path,
    viewport: SmokeViewport = SMOKE_VIEWPORTS[0],
) -> None:
    screenshot_path = screenshot_path.resolve()
    dom_dump_path = dom_dump_path.resolve()
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    dom_dump_path.parent.mkdir(parents=True, exist_ok=True)
    user_data_dir = ROOT / "build" / "control-center-browser-smoke-profile"
    user_data_dir.mkdir(parents=True, exist_ok=True)

    command = [
        str(browser_path),
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        f"--user-data-dir={user_data_dir}",
        f"--window-size={viewport.width},{viewport.height}",
        "--virtual-time-budget=10000",
        "--run-all-compositor-stages-before-draw",
        f"--screenshot={screenshot_path}",
        "--dump-dom",
        url,
    ]
    result = subprocess.run(command, capture_output=True, timeout=60)
    stdout = result.stdout.decode("utf-8", errors="replace")
    stderr = result.stderr.decode("utf-8", errors="replace")
    if result.returncode != 0:
        raise AssertionError(
            "system browser frontend contract smoke failed: "
            f"exit={result.returncode} stderr={stderr.strip()}"
        )

    dom_dump_path.write_text(stdout, encoding="utf-8")
    _assert_frontend_contract_error_dom(stdout)
    if not screenshot_path.exists() or screenshot_path.stat().st_size == 0:
        raise AssertionError(f"screenshot was not written: {screenshot_path}")


def _run_system_browser_error_smoke(
    *,
    url: str,
    browser_path: Path,
    screenshot_path: Path,
    dom_dump_path: Path,
    viewport: SmokeViewport = SMOKE_VIEWPORTS[0],
    payload: dict | None = None,
) -> None:
    screenshot_path = screenshot_path.resolve()
    dom_dump_path = dom_dump_path.resolve()
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    dom_dump_path.parent.mkdir(parents=True, exist_ok=True)
    user_data_dir = ROOT / "build" / "control-center-browser-smoke-profile"
    user_data_dir.mkdir(parents=True, exist_ok=True)

    command = [
        str(browser_path),
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        f"--user-data-dir={user_data_dir}",
        f"--window-size={viewport.width},{viewport.height}",
        "--virtual-time-budget=10000",
        "--run-all-compositor-stages-before-draw",
        f"--screenshot={screenshot_path}",
        "--dump-dom",
        url,
    ]
    result = subprocess.run(command, capture_output=True, timeout=60)
    stdout = result.stdout.decode("utf-8", errors="replace")
    stderr = result.stderr.decode("utf-8", errors="replace")
    if result.returncode != 0:
        raise AssertionError(
            "system browser error smoke failed: "
            f"exit={result.returncode} stderr={stderr.strip()}"
        )

    dom_dump_path.write_text(stdout, encoding="utf-8")
    _assert_error_dom(stdout)
    if not screenshot_path.exists() or screenshot_path.stat().st_size == 0:
        raise AssertionError(f"screenshot was not written: {screenshot_path}")

def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.verify_manifest is not None:
        verify_evidence_manifest(args.verify_manifest)
        print(f"manifest replay passed: {args.verify_manifest}")
        return 0
    if args.verify_error_manifest is not None:
        verify_error_evidence_manifest(args.verify_error_manifest)
        print(f"error manifest replay passed: {args.verify_error_manifest}")
        return 0
    if args.verify_frontend_error_manifest is not None:
        verify_frontend_error_evidence_manifest(args.verify_frontend_error_manifest)
        print(f"frontend error manifest replay passed: {args.verify_frontend_error_manifest}")
        return 0
    if args.verify_all_manifests:
        verify_evidence_manifest(args.manifest)
        verify_error_evidence_manifest(args.error_manifest)
        verify_frontend_error_evidence_manifest(args.frontend_error_manifest)
        print(f"all manifests replay passed: {args.manifest} + {args.error_manifest} + {args.frontend_error_manifest}")
        return 0
    if args.report_manifests:
        verify_evidence_manifest(args.manifest)
        verify_error_evidence_manifest(args.error_manifest)
        verify_frontend_error_evidence_manifest(args.frontend_error_manifest)
        report = build_evidence_report(args.manifest, args.error_manifest, args.frontend_error_manifest)
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(
            json.dumps(
                report,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            ) + "\n",
            encoding="utf-8",
        )
        print(format_evidence_report(report))
        print(f"evidence report json: {args.report_json}")
        return 0

    browser_path = args.browser_path or find_system_browser()
    if sync_playwright is None and browser_path is None:
        print(
            "playwright is not installed and no system browser was found; install it and run "
            "python -m scripts.control_center_browser_smoke"
        )
        return 2

    if args.expect_contract_error and args.expect_frontend_contract_error:
        raise ValueError("choose only one contract-error mode")
    handler = ControlCenterHandler
    if args.expect_contract_error:
        handler = BrokenContractHandler
    elif args.expect_frontend_contract_error:
        handler = FrontendBrokenContractHandler
    server, thread = _start_server(
        args.host,
        args.port,
        handler,
        allow_non_loopback=args.allow_non_loopback,
    )
    try:
        port = server.server_port
        url = f"http://{args.host}:{port}/control-center"
        error_mode = args.expect_contract_error or args.expect_frontend_contract_error
        api_response = None if error_mode else fetch_live_control_center_api_response(url)
        health_response = None if error_mode else fetch_live_control_center_health_response(url)
        frontend_response = None if error_mode else fetch_live_control_center_frontend_response(url)
        expected_payload = None if api_response is None else api_response.payload
        if expected_payload is not None:
            write_api_snapshot(args.api_snapshot, expected_payload)
        viewports = [SMOKE_VIEWPORTS[0]] if error_mode else SMOKE_VIEWPORTS
        viewport_artifacts = []
        for viewport in viewports:
            screenshot_base = args.screenshot
            dom_dump_base = args.dom_dump
            if args.expect_contract_error and args.screenshot == DEFAULT_SCREENSHOT:
                screenshot_base = DEFAULT_ERROR_SCREENSHOT
            if args.expect_contract_error and args.dom_dump == DEFAULT_DOM_DUMP:
                dom_dump_base = DEFAULT_ERROR_DOM_DUMP
            if args.expect_frontend_contract_error and args.screenshot == DEFAULT_SCREENSHOT:
                screenshot_base = DEFAULT_FRONTEND_ERROR_SCREENSHOT
            if args.expect_frontend_contract_error and args.dom_dump == DEFAULT_DOM_DUMP:
                dom_dump_base = DEFAULT_FRONTEND_ERROR_DOM_DUMP
            screenshot = _viewport_artifact_path(screenshot_base, viewport)
            dom_dump = _viewport_artifact_path(dom_dump_base, viewport)
            if args.expect_contract_error:
                assert browser_path is not None
                _run_system_browser_error_smoke(
                    url=url,
                    browser_path=browser_path,
                    screenshot_path=screenshot,
                    dom_dump_path=dom_dump,
                    viewport=viewport,
                )
            elif args.expect_frontend_contract_error:
                assert browser_path is not None
                _run_system_browser_frontend_contract_smoke(
                    url=url,
                    browser_path=browser_path,
                    screenshot_path=screenshot,
                    dom_dump_path=dom_dump,
                    viewport=viewport,
                )
            elif sync_playwright is not None:
                _run_browser_smoke(
                    url=url,
                    screenshot_path=screenshot,
                    dom_dump_path=dom_dump,
                    headed=args.headed,
                    viewport=viewport,
                    payload=expected_payload,
                )
            else:
                assert browser_path is not None
                _run_system_browser_smoke(
                    url=url,
                    browser_path=browser_path,
                    screenshot_path=screenshot,
                    dom_dump_path=dom_dump,
                    viewport=viewport,
                    payload=expected_payload,
                )
            viewport_artifacts.append({"viewport": viewport, "screenshot": screenshot, "dom_dump": dom_dump})
            print(f"{viewport.name} screenshot: {screenshot}")
            print(f"{viewport.name} dom dump: {dom_dump}")
        if expected_payload is not None:
            write_evidence_manifest(
                args.manifest,
                url=url,
                payload=expected_payload,
                api_snapshot=args.api_snapshot,
                viewport_artifacts=viewport_artifacts,
                api_response=api_response.metadata,
                health_response={**health_response.metadata, "payload": health_response.payload},
                frontend_response=frontend_response,
            )
            verify_evidence_manifest(args.manifest)
            print(f"manifest: {args.manifest}")
        elif args.expect_contract_error and viewport_artifacts:
            artifact = viewport_artifacts[0]
            write_error_evidence_manifest(
                args.error_manifest,
                url=url,
                viewport=artifact["viewport"],
                screenshot=artifact["screenshot"],
                dom_dump=artifact["dom_dump"],
            )
            verify_error_evidence_manifest(args.error_manifest)
            print(f"error manifest: {args.error_manifest}")
        elif args.expect_frontend_contract_error and viewport_artifacts:
            artifact = viewport_artifacts[0]
            write_frontend_error_evidence_manifest(
                args.frontend_error_manifest,
                url=url,
                viewport=artifact["viewport"],
                screenshot=artifact["screenshot"],
                dom_dump=artifact["dom_dump"],
            )
            verify_frontend_error_evidence_manifest(args.frontend_error_manifest)
            print(f"frontend error manifest: {args.frontend_error_manifest}")
        print(f"control center browser smoke passed: {url}")
        return 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
