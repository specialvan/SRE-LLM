"""HTTP service layer.

The SRE self-iteration pipeline is typically called from a deployment
system rather than imported directly. This package exposes a minimal
standard-library HTTP server (``stdlib``-only for operators that can't
install external runtimes easily) and a cleaner ASGI adapter guarded
behind an optional import.

Endpoints
---------

``POST /v1/observe``
    Record one release outcome. Body::

        { "service_id": "svc-a", "success": true,
          "duration_seconds": 12.5, "correlation_id": "optional" }

``POST /v1/decide``
    Return a decision for a candidate set. Body matches
    :meth:`gan_matchmaking.sre.ReleaseContext.from_dict`.

``GET /v1/services/{id}``
    Return the current rating for one service.

``GET /v1/dashboard/state``
    Return compact JSON used by the runtime dashboard.

``GET /dashboard``
    Serve the no-build runtime dashboard HTML.

``GET /dashboard/assets/{asset}``
    Serve allowlisted dashboard CSS/JS assets.

``GET /healthz``
    Liveness probe.

``GET /readyz``
    Readiness probe — returns 503 while the circuit breaker is open.

``GET /metrics``
    Prometheus exposition text.
"""

from .app import DecisionApp, build_app, run_wsgi

__all__ = ["DecisionApp", "build_app", "run_wsgi"]
