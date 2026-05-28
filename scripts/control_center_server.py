from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import ip_address
from pathlib import Path

from analysis.control_center_data import build_control_center_payload

ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "docs"
API_PATH = "/api/control-center"
HEALTH_PATH = f"{API_PATH}/health"
CONTRACT_VERSION = "control-center.v1"
HTML_PATHS = frozenset({"/", "/control-center", "/control-center.html"})
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def is_loopback_bind_host(host: str) -> bool:
    normalized = (host or "").strip().lower()
    if normalized == "localhost":
        return True
    try:
        return ip_address(normalized).is_loopback
    except ValueError:
        return False


def require_loopback_bind_host(host: str, *, allow_non_loopback: bool = False) -> None:
    if allow_non_loopback or is_loopback_bind_host(host):
        return
    raise ValueError(
        "Refusing to bind control-center server to non-loopback host "
        f"{host!r}; pass allow_non_loopback=True only for an intentional exposure."
    )


def is_allowed_host(host_header: str | None, port: int) -> bool:
    if not host_header:
        return False
    normalized = host_header.lower()
    allowed_hosts = {
        f"127.0.0.1:{port}",
        f"localhost:{port}",
        f"[::1]:{port}",
    }
    return normalized in allowed_hosts


def resolve_control_center_route(path: str) -> str | None:
    if path in HTML_PATHS:
        return "html"
    if path == API_PATH:
        return "api"
    if path == HEALTH_PATH:
        return "health"
    return None


def build_health_payload() -> dict:
    return {
        "status": "ok",
        "contract": {"version": CONTRACT_VERSION, "api_path": API_PATH},
        "routes": {"frontend": "/control-center", "api": API_PATH},
    }


def _arrays_for_contract_path(payload: dict, path: str) -> list[tuple[str, object]]:
    parts = path.split(".")
    if len(parts) == 1:
        return [(parts[0], payload.get(parts[0]))]
    if len(parts) == 2 and parts[0] == "timeline":
        timeline = payload.get("timeline")
        if not isinstance(timeline, list):
            return [("timeline", timeline)]
        return [
            (f"timeline[{index}].{parts[1]}", row[parts[1]])
            for index, row in enumerate(timeline)
            if isinstance(row, dict) and parts[1] in row
        ]
    parent = payload.get(parts[0])
    if not isinstance(parent, dict):
        return [(parts[0], parent)]
    return [(path, parent.get(parts[1]))]


def _validate_length_consistency(payload: dict) -> list[str]:
    errors: list[str] = []
    timeline = payload.get("timeline")
    summary = payload.get("summary")
    series = payload.get("series")
    load_split = payload.get("load_split")

    if not isinstance(timeline, list):
        return errors
    timeline_length = len(timeline)

    if isinstance(summary, dict):
        ticks = summary.get("ticks")
        if isinstance(ticks, int) and ticks != timeline_length:
            errors.append(f"summary.ticks {ticks} does not match timeline length {timeline_length}")

    if isinstance(series, dict):
        for name in ("replicas", "observed_rps", "forecast_rps", "pool_connections", "degraded_mask"):
            values = series.get(name)
            if isinstance(values, list) and len(values) != timeline_length:
                errors.append(
                    f"series.{name} length {len(values)} does not match timeline length {timeline_length}"
                )

    if isinstance(load_split, list):
        load_split_length = len(load_split)
        for index, row in enumerate(timeline):
            if not isinstance(row, dict):
                continue
            alloc_shares = row.get("alloc_shares")
            if isinstance(alloc_shares, list) and len(alloc_shares) != load_split_length:
                errors.append(
                    f"timeline[{index}].alloc_shares length {len(alloc_shares)} "
                    f"does not match load_split length {load_split_length}"
                )
    return errors


def validate_control_center_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    contract = payload.get("frontend_contract")
    if not isinstance(contract, dict):
        return ["missing frontend_contract"]

    required_fields = contract.get("timeline_required_fields")
    if not isinstance(required_fields, list):
        errors.append("frontend_contract.timeline_required_fields must be a list")
        required_fields = []

    top_level_required_fields = contract.get("top_level_required_fields")
    if not isinstance(top_level_required_fields, list):
        errors.append("frontend_contract.top_level_required_fields must be a list")
        top_level_required_fields = []
    for field in top_level_required_fields:
        if field not in payload:
            errors.append(f"missing required frontend field: {field}")

    object_required_fields = contract.get("object_required_fields")
    if not isinstance(object_required_fields, dict):
        errors.append("frontend_contract.object_required_fields must be an object")
        object_required_fields = {}
    for object_name, object_fields in object_required_fields.items():
        obj = payload.get(object_name)
        if not isinstance(obj, dict):
            errors.append(f"{object_name} must be an object")
            continue
        if not isinstance(object_fields, list):
            errors.append(f"frontend_contract.object_required_fields.{object_name} must be a list")
            continue
        for field in object_fields:
            if field not in obj:
                errors.append(f"{object_name} missing required frontend field: {field}")

    array_item_required_fields = contract.get("array_item_required_fields")
    if not isinstance(array_item_required_fields, dict):
        errors.append("frontend_contract.array_item_required_fields must be an object")
        array_item_required_fields = {}
    for array_path, item_fields in array_item_required_fields.items():
        if not isinstance(item_fields, list):
            errors.append(f"frontend_contract.array_item_required_fields.{array_path} must be a list")
            continue
        for resolved_path, array_value in _arrays_for_contract_path(payload, array_path):
            if not isinstance(array_value, list):
                errors.append(f"{resolved_path} must be a list")
                continue
            for index, item in enumerate(array_value):
                if not isinstance(item, dict):
                    errors.append(f"{resolved_path}[{index}] must be an object")
                    continue
                for field in item_fields:
                    if field not in item:
                        errors.append(f"{resolved_path}[{index}] missing required frontend field: {field}")

    timeline = payload.get("timeline")
    if not isinstance(timeline, list) or not timeline:
        errors.append("timeline must be a non-empty list")
        return errors

    for index, row in enumerate(timeline):
        if not isinstance(row, dict):
            errors.append(f"timeline[{index}] must be an object")
            continue
        for field in required_fields:
            if field not in row:
                errors.append(f"timeline[{index}] missing required frontend field: {field}")
    errors.extend(_validate_length_consistency(payload))
    return errors


class ControlCenterHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if not is_allowed_host(self.headers.get("Host"), self.server.server_port):
            self.send_error(403, "Forbidden")
            return
        route = resolve_control_center_route(self.path)
        if route == "html":
            self._serve_file(DOCS_DIR / "control-center.html", "text/html; charset=utf-8")
            return
        if route == "api":
            payload = build_control_center_payload()
            errors = validate_control_center_payload(payload)
            if errors:
                self._serve_json(
                    {"error": "control_center_contract_violation", "details": errors},
                    500,
                )
                return
            self._serve_json(payload, 200)
            return
        if route == "health":
            self._serve_json(build_health_payload(), 200)
            return
        self.send_error(404, "Not Found")

    def log_message(self, format: str, *args) -> None:
        return

    def _serve_json(self, payload: dict, status: int) -> None:
            body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self._send_contract_headers()
            self.end_headers()
            self.wfile.write(body)

    def _send_contract_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Control-Center-Contract", CONTRACT_VERSION)
        self.send_header("X-Control-Center-API", API_PATH)

    def _serve_file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self.send_error(404, "Not Found")
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self._send_contract_headers()
        self.end_headers()
        self.wfile.write(body)


def main(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    *,
    allow_non_loopback: bool = False,
) -> None:
    require_loopback_bind_host(host, allow_non_loopback=allow_non_loopback)
    server = ThreadingHTTPServer((host, port), ControlCenterHandler)
    print(f"Control Center running at http://{host}:{port}/control-center")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
