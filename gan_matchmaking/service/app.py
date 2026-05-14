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

import ipaddress
import json
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, Optional, Tuple
from urllib.parse import urlparse

from .assets import load_dashboard_asset
from ..core import AppConfig, MetricsRegistry
from ..core.errors import GanError
from ..core.tracing import with_correlation_id
from ..persistence import PipelineStore
from ..sre import ReleaseContext, SelfIterationPipeline
from ..sre.circuit import CircuitBreaker


JsonDict = Dict[str, Any]
_DASHBOARD_SERVICE_LIMIT = 200
_DASHBOARD_SYNERGY_LIMIT = 500
_DASHBOARD_CSP = (
    "default-src 'none'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "connect-src 'self'; "
    "base-uri 'none'; "
    "frame-ancestors 'none'"
)
_CORRELATION_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def _make_healthy_event() -> threading.Event:
    evt = threading.Event()
    evt.set()
    return evt


@dataclass
class DecisionApp:
    """WSGI-ish app. Handlers receive parsed JSON and return (status, body)."""

    pipeline: SelfIterationPipeline
    readiness_breaker: Optional[CircuitBreaker] = None
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    _lease_healthy: threading.Event = field(
        default_factory=_make_healthy_event, init=False
    )
    _lease_unhealthy_details: JsonDict = field(default_factory=dict, init=False)
    _lease_path: Optional[str] = field(default=None, init=False)
    _lease_owner: Optional[str] = field(default=None, init=False)
    m_lease_refresh_failures: Any = field(default=None, init=False)

    def __post_init__(self) -> None:
        self.m_lease_refresh_failures = self.pipeline.metrics.counter(
            "gan_lease_refresh_failures_total",
            "Number of lease refresh failures seen by the HTTP service.",
            label_names=("reason",),
        )

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    def handle_health(self, _body: Optional[JsonDict]) -> Tuple[int, JsonDict]:
        return 200, {"status": "ok"}

    def handle_ready(self, _body: Optional[JsonDict]) -> Tuple[int, JsonDict]:
        if not self._lease_healthy.is_set():
            return 503, {
                "status": "not_ready",
                "reason": "lease_unhealthy",
                "details": dict(self._lease_unhealthy_details),
            }
        breaker = self.readiness_breaker or self.pipeline.circuit_breaker
        if breaker is None or breaker.allow():
            return 200, {"status": "ready"}
        return 503, {"status": "not_ready", "breaker": breaker.snapshot()}

    def handle_metrics(self, _body: Optional[JsonDict]) -> Tuple[int, str]:
        text = self.pipeline.metrics.export_prometheus()
        return 200, text

    def handle_observe(self, body: JsonDict) -> Tuple[int, JsonDict]:
        required = {"service_id", "success"}
        missing = required - set(body or {})
        if missing:
            return 400, {
                "error": {
                    "code": "gan.http.bad_request",
                    "message": f"missing fields: {sorted(missing)}",
                }
            }
        dependencies = body.get("dependencies", [])
        if dependencies is None:
            dependencies = []
        if not isinstance(dependencies, list):
            return 400, {
                "error": {
                    "code": "gan.http.bad_request",
                    "message": "dependencies must be a list",
                }
            }
        with self._lock:
            self.pipeline.observe_release(
                service_id=str(body["service_id"]),
                success=bool(body["success"]),
                duration_seconds=float(body.get("duration_seconds", 0.0)),
                features=body.get("features"),
                correlation_id=body.get("correlation_id"),
                dependencies=[str(dep) for dep in dependencies],
            )
        return 200, {"status": "recorded"}

    def handle_decide(self, body: JsonDict) -> Tuple[int, JsonDict]:
        ctx = ReleaseContext.from_dict(body)
        decision = self.pipeline.decide(ctx)
        return 200, decision.to_dict()

    def handle_get_service(self, service_id: str) -> Tuple[int, JsonDict]:
        svc = self.pipeline.service_snapshot(service_id)
        if svc is None and self.pipeline.store is not None:
            stored = self.pipeline.store.services.get(service_id)
            if stored is not None:
                svc = stored.as_dict()
        if svc is None:
            return 404, {
                "error": {
                    "code": "gan.http.not_found",
                    "message": f"unknown service {service_id!r}",
                }
            }
        return 200, svc

    def handle_dashboard_state(self) -> Tuple[int, JsonDict]:
        ready_status, ready_body = self.handle_ready(None)
        services_by_id = self.pipeline.services_snapshot(
            limit=_DASHBOARD_SERVICE_LIMIT + 1
        )
        services_truncated = len(services_by_id) > _DASHBOARD_SERVICE_LIMIT
        services_by_id = {
            key: services_by_id[key]
            for key in sorted(services_by_id)[:_DASHBOARD_SERVICE_LIMIT]
        }
        synergy = []
        synergy_truncated = False
        if self.pipeline.store is not None:
            remaining = max(0, _DASHBOARD_SERVICE_LIMIT - len(services_by_id))
            for service_id in self.pipeline.store.services.list_ids(
                limit=remaining + 1
            ):
                if service_id in services_by_id:
                    continue
                if len(services_by_id) >= _DASHBOARD_SERVICE_LIMIT:
                    services_truncated = True
                    break
                service = self.pipeline.store.services.get(service_id)
                if service is not None:
                    services_by_id[service.id] = service.as_dict()
            for a, b, games, wins in self.pipeline.store.synergy.edges(
                limit=_DASHBOARD_SYNERGY_LIMIT + 1
            ):
                if len(synergy) >= _DASHBOARD_SYNERGY_LIMIT:
                    synergy_truncated = True
                    break
                synergy.append({"a": a, "b": b, "games": games, "wins": wins})
        services = [services_by_id[key] for key in sorted(services_by_id)]
        return 200, {
            "status": {
                "health": "ok",
                "ready": ready_status == 200,
                "reason": ready_body.get("reason") if ready_status != 200 else None,
            },
            "services": services,
            "synergy": synergy,
            "limits": {
                "max_services": _DASHBOARD_SERVICE_LIMIT,
                "max_synergy_edges": _DASHBOARD_SYNERGY_LIMIT,
                "services_truncated": services_truncated,
                "synergy_truncated": synergy_truncated,
            },
            "generated_at": time.time(),
        }

    def dashboard_enabled_for_peer(self, peer: str) -> bool:
        try:
            return ipaddress.ip_address(peer).is_loopback
        except ValueError:
            return False

    def bind_lease_metadata(self, *, path: str, owner: str) -> None:
        """Record lease identity for later log/metric emission."""
        self._lease_path = path
        self._lease_owner = owner

    def mark_lease_unhealthy(self, exc: BaseException) -> None:
        """Flip readiness, increment metric, and emit a structured log once."""
        with self._lock:
            if not self._lease_healthy.is_set():
                return
            reason = type(exc).__name__
            self._lease_unhealthy_details = {
                "reason": reason,
                "message": str(exc)[:200],
            }
            self.m_lease_refresh_failures.inc(labels={"reason": reason})
            self._lease_healthy.clear()
        self.pipeline.logger.error(
            "lease.refresh.failed",
            lease_path=self._lease_path or "unknown",
            owner=self._lease_owner or "unknown",
            error_type=reason,
        )


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
    @staticmethod
    def _safe_correlation_id(value: Optional[str]) -> str:
        if value is not None and _CORRELATION_ID_RE.fullmatch(value):
            return value
        return uuid.uuid4().hex[:16]

    def _send_response(
        self,
        status: int,
        payload: bytes,
        content_type: str,
        correlation_id: str,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("X-Correlation-Id", correlation_id)
        self.send_header("X-Content-Type-Options", "nosniff")
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(payload)

    def _send_json(self, status: int, body: Any, correlation_id: str) -> None:
        if isinstance(body, str):
            payload = body.encode("utf-8")
            content_type = "text/plain; version=0.0.4; charset=utf-8"
        else:
            payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
            content_type = "application/json"
        self._send_response(status, payload, content_type, correlation_id)

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
        cid = self._safe_correlation_id(self.headers.get("X-Correlation-Id"))
        peer = self.client_address[0]
        dashboard_request = (
            path == "/dashboard"
            or path.startswith("/dashboard/assets/")
            or path == "/v1/dashboard/state"
        )
        body_cache = None
        try:
            # Peek at the request body's correlation_id so logs / response
            # headers stay consistent with the payload the caller supplied.
            if self.command == "POST":
                body_cache = self._read_body()
                if isinstance(body_cache, dict):
                    body_cid = body_cache.get("correlation_id")
                    if body_cid:
                        cid = self._safe_correlation_id(str(body_cid))
            with with_correlation_id(cid):
                if dashboard_request and not self.app.dashboard_enabled_for_peer(peer):
                    status, body = 403, {
                        "error": {
                            "code": "gan.http.forbidden",
                            "message": "dashboard is only available on localhost",
                        }
                    }
                elif path == "/healthz" and self.command == "GET":
                    status, body = self.app.handle_health(None)
                elif path == "/readyz" and self.command == "GET":
                    status, body = self.app.handle_ready(None)
                elif path == "/metrics" and self.command == "GET":
                    status, body = self.app.handle_metrics(None)
                elif path == "/dashboard" and self.command == "GET":
                    asset = load_dashboard_asset("dashboard.html")
                    if asset is None:
                        status, body = 404, {
                            "error": {
                                "code": "gan.http.not_found",
                                "message": "dashboard asset missing",
                            }
                        }
                    else:
                        payload, content_type = asset
                        self._send_response(
                            200,
                            payload,
                            content_type,
                            cid,
                            {"Content-Security-Policy": _DASHBOARD_CSP},
                        )
                        return
                elif path.startswith("/dashboard/assets/") and self.command == "GET":
                    name = path[len("/dashboard/assets/") :]
                    asset = load_dashboard_asset(name)
                    if asset is None:
                        status, body = 404, {
                            "error": {
                                "code": "gan.http.not_found",
                                "message": f"unknown dashboard asset {name!r}",
                            }
                        }
                    else:
                        payload, content_type = asset
                        self._send_response(
                            200,
                            payload,
                            content_type,
                            cid,
                            {"Content-Security-Policy": _DASHBOARD_CSP},
                        )
                        return
                elif path == "/v1/dashboard/state" and self.command == "GET":
                    status, body = self.app.handle_dashboard_state()
                elif path == "/v1/observe" and self.command == "POST":
                    status, body = self.app.handle_observe(body_cache or {})
                elif path == "/v1/decide" and self.command == "POST":
                    status, body = self.app.handle_decide(body_cache or {})
                elif path.startswith("/v1/services/") and self.command == "GET":
                    svc_id = path[len("/v1/services/") :]
                    status, body = self.app.handle_get_service(svc_id)
                else:
                    status, body = 404, {
                        "error": {
                            "code": "gan.http.not_found",
                            "message": f"unknown path {path!r}",
                        }
                    }
                self._send_json(status, body, cid)
        except _BadRequest as exc:
            self._send_json(
                400,
                {"error": {"code": "gan.http.bad_request", "message": str(exc)}},
                cid,
            )
        except GanError as exc:
            self._send_json(422, {"error": exc.to_dict()}, cid)
        except Exception as exc:  # pragma: no cover  (catch-all for the HTTP boundary)
            self.app.pipeline.logger.error(
                "http.unhandled",
                path=path,
                method=self.command,
                error_type=type(exc).__name__,
            )
            self._send_json(
                500,
                {
                    "error": {
                        "code": "gan.http.unhandled",
                        "message": "internal server error",
                    }
                },
                cid,
            )

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
        config=cfg,
        metrics=metrics,
        store=store,
        circuit_breaker=breaker,
    )
    return DecisionApp(pipeline=pipeline, readiness_breaker=breaker)


def run_wsgi(app: DecisionApp, host: str = "127.0.0.1", port: int = 8080) -> None:
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
