"""Standard-library HTTP wrapper around :class:`SelfIterationPipeline`.

Design notes
------------

- Stdlib only: ``http.server.ThreadingHTTPServer`` + a thin WSGI-compatible
  view class. No Flask / FastAPI dependency.
- Thread-safe: the pipeline already has per-service locks; we just reuse one
  pipeline per process.
- JSON everywhere. Every error response has ``{"error": {"code", "message", ...}}``
  so operators can parse it without regex.
- Always emits a ``X-Correlation-Id`` header mirrored from the request body
  or generated locally.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, Optional, Tuple
from urllib.parse import urlparse

from ..cli import _ctx_from_dict
from ..core import AppConfig, MetricsRegistry
from ..core.errors import GanError
from ..core.tracing import with_correlation_id
from ..persistence import PipelineStore
from ..sre import SelfIterationPipeline
from ..sre.circuit import CircuitBreaker


JsonDict = Dict[str, Any]


@dataclass
class DecisionApp:
    """WSGI-ish app. Handlers receive parsed JSON and return (status, body)."""

    pipeline: SelfIterationPipeline
    readiness_breaker: Optional[CircuitBreaker] = None
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    def handle_health(self, _body: Optional[JsonDict]) -> Tuple[int, JsonDict]:
        return 200, {"status": "ok"}

    def handle_ready(self, _body: Optional[JsonDict]) -> Tuple[int, JsonDict]:
        breaker = self.readiness_breaker or self.pipeline.circuit_breaker
        if breaker is None or breaker.allow():
            return 200, {"status": "ready"}
        return 503, {"status": "not_ready",
                     "breaker": breaker.snapshot()}

    def handle_metrics(self, _body: Optional[JsonDict]) -> Tuple[int, str]:
        text = self.pipeline.metrics.export_prometheus()
        return 200, text

    def handle_observe(self, body: JsonDict) -> Tuple[int, JsonDict]:
        required = {"service_id", "success"}
        missing = required - set(body or {})
        if missing:
            return 400, {"error": {"code": "gan.http.bad_request",
                                    "message": f"missing fields: {sorted(missing)}"}}
        with self._lock:
            self.pipeline.observe_release(
                service_id=str(body["service_id"]),
                success=bool(body["success"]),
                duration_seconds=float(body.get("duration_seconds", 0.0)),
                features=body.get("features"),
                correlation_id=body.get("correlation_id"),
            )
        return 200, {"status": "recorded"}

    def handle_decide(self, body: JsonDict) -> Tuple[int, JsonDict]:
        ctx = _ctx_from_dict(body)
        decision = self.pipeline.decide(ctx)
        return 200, decision.to_dict()

    def handle_get_service(self, service_id: str) -> Tuple[int, JsonDict]:
        svc = self.pipeline._services.get(service_id)  # noqa: SLF001
        if svc is None and self.pipeline.store is not None:
            svc = self.pipeline.store.services.get(service_id)
        if svc is None:
            return 404, {"error": {"code": "gan.http.not_found",
                                    "message": f"unknown service {service_id!r}"}}
        return 200, svc.as_dict()


# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------
class _Handler(BaseHTTPRequestHandler):
    app: DecisionApp = None  # type: ignore[assignment]

    # Silence the default stderr access log; we rely on the pipeline logger.
    def log_message(self, format: str, *args: Any) -> None:
        return

    # ------------------------------------------------------------------
    # Dispatcher
    # ------------------------------------------------------------------
    def _send_json(self, status: int, body: Any, correlation_id: str) -> None:
        if isinstance(body, str):
            payload = body.encode("utf-8")
            content_type = "text/plain; version=0.0.4; charset=utf-8"
        else:
            payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
            content_type = "application/json"
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("X-Correlation-Id", correlation_id)
        self.end_headers()
        self.wfile.write(payload)

    def _read_body(self) -> Optional[JsonDict]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return None
        raw = self.rfile.read(length)
        if not raw:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise _BadRequest(str(exc))

    def _dispatch(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        cid = self.headers.get("X-Correlation-Id") or uuid.uuid4().hex[:16]
        body_cache = None
        try:
            # Peek at the request body's correlation_id so logs / response
            # headers stay consistent with the payload the caller supplied.
            if self.command == "POST":
                body_cache = self._read_body()
                if isinstance(body_cache, dict):
                    body_cid = body_cache.get("correlation_id")
                    if body_cid:
                        cid = str(body_cid)
            with with_correlation_id(cid):
                if path == "/healthz" and self.command == "GET":
                    status, body = self.app.handle_health(None)
                elif path == "/readyz" and self.command == "GET":
                    status, body = self.app.handle_ready(None)
                elif path == "/metrics" and self.command == "GET":
                    status, body = self.app.handle_metrics(None)
                elif path == "/v1/observe" and self.command == "POST":
                    status, body = self.app.handle_observe(body_cache or {})
                elif path == "/v1/decide" and self.command == "POST":
                    status, body = self.app.handle_decide(body_cache or {})
                elif path.startswith("/v1/services/") and self.command == "GET":
                    svc_id = path[len("/v1/services/"):]
                    status, body = self.app.handle_get_service(svc_id)
                else:
                    status, body = 404, {"error": {"code": "gan.http.not_found",
                                                    "message": f"unknown path {path!r}"}}
                self._send_json(status, body, cid)
        except _BadRequest as exc:
            self._send_json(400, {"error": {"code": "gan.http.bad_request",
                                             "message": str(exc)}}, cid)
        except GanError as exc:
            self._send_json(422, {"error": exc.to_dict()}, cid)
        except Exception as exc:  # pragma: no cover  (catch-all for the HTTP boundary)
            self._send_json(500, {"error": {"code": "gan.http.unhandled",
                                             "message": str(exc),
                                             "type": type(exc).__name__}}, cid)

    def do_GET(self) -> None:
        self._dispatch()

    def do_POST(self) -> None:
        self._dispatch()


class _BadRequest(Exception):
    pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def build_app(
    config: Optional[AppConfig] = None,
    store: Optional[PipelineStore] = None,
    metrics: Optional[MetricsRegistry] = None,
) -> DecisionApp:
    metrics = metrics or MetricsRegistry()
    cfg = config or AppConfig()
    breaker = CircuitBreaker(failure_threshold=5, recovery_seconds=30.0)
    pipeline = SelfIterationPipeline(
        config=cfg, metrics=metrics, store=store, circuit_breaker=breaker,
    )
    return DecisionApp(pipeline=pipeline, readiness_breaker=breaker)


def run_wsgi(app: DecisionApp, host: str = "0.0.0.0", port: int = 8080) -> None:
    """Blocking server entry point. Use a SIGTERM handler in production."""
    class _App(_Handler):
        pass
    _App.app = app
    httpd = ThreadingHTTPServer((host, port), _App)
    app.pipeline.logger.info("http.listening", host=host, port=port)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
