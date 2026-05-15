from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from analysis.control_center_data import build_control_center_payload

ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "docs"
API_PATH = "/api/control-center"
HTML_PATHS = frozenset({"/", "/control-center", "/control-center.html"})
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def is_allowed_host(host_header: str | None, port: int) -> bool:
    if not host_header:
        return False
    normalized = host_header.lower()
    allowed_hosts = {
        f"127.0.0.1:{port}",
        f"localhost:{port}",
    }
    return normalized in allowed_hosts


def resolve_control_center_route(path: str) -> str | None:
    if path in HTML_PATHS:
        return "html"
    if path == API_PATH:
        return "api"
    return None


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
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404, "Not Found")

    def log_message(self, format: str, *args) -> None:
        return

    def _serve_file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self.send_error(404, "Not Found")
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
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
