"""Tests for the HTTP service."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from gan_matchmaking.persistence import InMemoryPipelineStore
from gan_matchmaking.service import build_app
from gan_matchmaking.service.app import _Handler


@pytest.fixture
def server():
    app = build_app(store=InMemoryPipelineStore())

    class Bound(_Handler):
        pass

    Bound.app = app

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Bound)
    host, port = httpd.server_address
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://{host}:{port}", app
    finally:
        httpd.shutdown()
        httpd.server_close()


@pytest.fixture
def non_loopback_server():
    app = build_app(store=InMemoryPipelineStore())

    class Bound(_Handler):
        def _dispatch(self):
            original = self.client_address
            self.client_address = ("192.0.2.10", original[1])
            try:
                super()._dispatch()
            finally:
                self.client_address = original

    Bound.app = app

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Bound)
    host, port = httpd.server_address
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://{host}:{port}", app
    finally:
        httpd.shutdown()
        httpd.server_close()


def _get(url: str, extra_headers: dict | None = None):
    req = urllib.request.Request(url, headers=extra_headers or {})
    try:
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            return resp.status, resp.read().decode("utf-8"), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8"), dict(e.headers or {})


def _post(url: str, payload: dict, extra_headers: dict | None = None):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", **(extra_headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            return (
                resp.status,
                json.loads(resp.read().decode("utf-8")),
                dict(resp.headers),
            )
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = body
        return e.code, parsed, dict(e.headers or {})


def test_healthz(server):
    url, _ = server
    status, body, _ = _get(f"{url}/healthz")
    assert status == 200
    assert json.loads(body)["status"] == "ok"


def test_readyz_allows_when_breaker_closed(server):
    url, _ = server
    status, body, _ = _get(f"{url}/readyz")
    assert status == 200
    assert json.loads(body)["status"] == "ready"


def test_readyz_http_reflects_lease_failure(server):
    url, app = server

    app.mark_lease_unhealthy(RuntimeError("boom"))

    status, body, _ = _get(f"{url}/readyz")
    payload = json.loads(body)
    assert status == 503
    assert payload["status"] == "not_ready"
    assert payload["reason"] == "lease_unhealthy"
    assert payload["details"]["reason"] == "RuntimeError"

    status, body, _ = _get(f"{url}/healthz")
    assert status == 200
    assert json.loads(body)["status"] == "ok"


def test_metrics_endpoint_returns_text(server):
    url, _ = server
    status, body, headers = _get(f"{url}/metrics")
    assert status == 200
    assert headers["Content-Type"].startswith("text/plain")


def test_observe_and_get_service(server):
    url, app = server

    status, body, _ = _post(
        f"{url}/v1/observe",
        {
            "service_id": "svc-a",
            "success": True,
            "duration_seconds": 5.0,
            "correlation_id": "obs-1",
        },
    )
    assert status == 422  # unknown service — observe_release raises DataError.
    # Seed a service via decide first.
    payload = {
        "service": {"id": "svc-a", "mu": 0.99, "sigma": 0.02},
        "candidates": [
            {
                "id": "canary",
                "strategy": "canary",
                "canary_fraction": 0.05,
                "rollback_budget_seconds": 180,
                "expected_success": 0.99,
            }
        ],
        "correlation_id": "decide-1",
    }
    status, body, headers = _post(f"{url}/v1/decide", payload)
    assert status == 200, body
    assert body["correlation_id"] == "decide-1"
    assert headers["X-Correlation-Id"] == "decide-1"

    # Now observe works.
    status, body, _ = _post(
        f"{url}/v1/observe",
        {
            "service_id": "svc-a",
            "success": True,
            "duration_seconds": 5.0,
            "dependencies": ["dep-a"],
        },
    )
    assert status == 200
    assert app.pipeline.store is not None
    assert app.pipeline.store.synergy.stats("svc-a", "dep-a") == (1, 1)

    status, body, _ = _get(f"{url}/v1/services/svc-a")
    assert status == 200
    payload = json.loads(body)
    assert payload["id"] == "svc-a"
    assert payload["total_releases"] == 1


def test_unknown_endpoint_404(server):
    url, _ = server
    status, _, _ = _get(f"{url}/does-not-exist")
    assert status == 404


def test_malformed_json_gives_400(server):
    url, _ = server
    # Send junk payload.
    req = urllib.request.Request(
        f"{url}/v1/decide",
        data=b"not-json",
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=5.0)
        assert False, "should have raised"
    except urllib.error.HTTPError as e:
        assert e.code == 400
        body = json.loads(e.read().decode("utf-8"))
        assert body["error"]["code"] == "gan.http.bad_request"


def test_correlation_id_autogenerated_when_missing(server):
    url, _ = server
    status, _, headers = _get(f"{url}/healthz")
    assert status == 200
    assert headers.get("X-Correlation-Id")


def test_correlation_id_rejects_unsafe_values():
    assert _Handler._safe_correlation_id("ok-123._") == "ok-123._"
    generated = _Handler._safe_correlation_id("bad\r\nX-Bad: 1")
    assert generated != "bad\r\nX-Bad: 1"
    assert len(generated) == 16


def test_dashboard_html_served(server):
    url, _ = server
    status, body, headers = _get(f"{url}/dashboard")

    assert status == 200
    assert headers["Content-Type"].startswith("text/html")
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert "default-src 'none'" in headers["Content-Security-Policy"]
    assert "GAN Runtime Dashboard" in body
    assert "<main" in body
    assert "/dashboard/assets/dashboard.css" in body
    assert "/dashboard/assets/dashboard.js" in body


def test_dashboard_static_assets_served(server):
    url, _ = server

    status, body, headers = _get(f"{url}/dashboard/assets/dashboard.css")
    assert status == 200
    assert headers["Content-Type"].startswith("text/css")
    assert "prefers-reduced-motion" in body

    status, body, headers = _get(f"{url}/dashboard/assets/dashboard.js")
    assert status == 200
    assert headers["Content-Type"].startswith("application/javascript")
    assert "fetchDashboardState" in body


def test_dashboard_unknown_and_traversal_assets_404(server):
    url, _ = server

    status, _, _ = _get(f"{url}/dashboard/assets/missing.js")
    assert status == 404

    status, _, _ = _get(f"{url}/dashboard/assets/../app.py")
    assert status == 404

    status, _, _ = _get(f"{url}/dashboard/assets/%2e%2e/app.py")
    assert status == 404


def test_dashboard_peer_gate_uses_socket_address_not_host_header():
    pipeline = build_app(store=InMemoryPipelineStore())
    assert pipeline.dashboard_enabled_for_peer("127.0.0.1") is True
    assert pipeline.dashboard_enabled_for_peer("::1") is True
    assert pipeline.dashboard_enabled_for_peer("192.0.2.10") is False
    assert pipeline.dashboard_enabled_for_peer("not-an-ip") is False


def test_dashboard_endpoints_forbid_non_loopback_peer(non_loopback_server):
    url, _ = non_loopback_server

    status, body, _ = _get(f"{url}/healthz", {"Host": "localhost"})
    assert status == 200
    assert json.loads(body)["status"] == "ok"

    for path in (
        "/dashboard",
        "/dashboard/assets/dashboard.css",
        "/dashboard/assets/dashboard.js",
        "/v1/dashboard/state",
    ):
        status, body, headers = _get(f"{url}{path}", {"Host": "localhost"})
        payload = json.loads(body)
        assert status == 403
        assert headers["Content-Type"].startswith("application/json")
        assert payload["error"]["code"] == "gan.http.forbidden"
        assert payload["error"]["message"] == "dashboard is only available on localhost"


def test_dashboard_state_empty_store(server):
    url, _ = server

    status, body, headers = _get(f"{url}/v1/dashboard/state")
    payload = json.loads(body)

    assert status == 200
    assert headers["Content-Type"].startswith("application/json")
    assert payload["status"]["health"] == "ok"
    assert payload["status"]["ready"] is True
    assert payload["status"]["reason"] is None
    assert payload["services"] == []
    assert payload["synergy"] == []
    assert payload["limits"]["services_truncated"] is False
    assert payload["limits"]["synergy_truncated"] is False
    assert isinstance(payload["generated_at"], float)


def test_dashboard_state_reflects_decide_only_service(server):
    url, _ = server
    decide_payload = {
        "service": {"id": "svc-a", "mu": 0.99, "sigma": 0.02},
        "candidates": [
            {
                "id": "canary",
                "strategy": "canary",
                "canary_fraction": 0.05,
                "rollback_budget_seconds": 180,
                "expected_success": 0.99,
            }
        ],
        "correlation_id": "dashboard-decide-1",
    }
    status, body, _ = _post(f"{url}/v1/decide", decide_payload)
    assert status == 200, body

    status, body, _ = _get(f"{url}/v1/dashboard/state")
    payload = json.loads(body)

    assert status == 200
    assert len(payload["services"]) == 1
    service = payload["services"][0]
    assert service["id"] == "svc-a"
    assert service["tier"] == "standard"
    assert service["win_streak"] == 0
    assert service["loss_streak"] == 0
    assert service["total_releases"] == 0
    assert service["mu"] == 0.99
    assert service["sigma"] == 0.02
    assert payload["synergy"] == []


def test_dashboard_state_reflects_observed_synergy(server):
    url, _ = server
    decide_payload = {
        "service": {"id": "svc-a", "mu": 0.99, "sigma": 0.02},
        "candidates": [
            {
                "id": "canary",
                "strategy": "canary",
                "canary_fraction": 0.05,
                "rollback_budget_seconds": 180,
                "expected_success": 0.99,
            }
        ],
        "correlation_id": "dashboard-decide-2",
    }
    status, body, _ = _post(f"{url}/v1/decide", decide_payload)
    assert status == 200, body

    status, body, _ = _post(
        f"{url}/v1/observe",
        {
            "service_id": "svc-a",
            "success": True,
            "duration_seconds": 5.0,
            "dependencies": ["dep-a"],
        },
    )
    assert status == 200, body

    status, body, _ = _get(f"{url}/v1/dashboard/state")
    payload = json.loads(body)

    assert status == 200
    assert payload["synergy"] == [
        {
            "a": "dep-a",
            "b": "svc-a",
            "games": 1,
            "wins": 1,
        }
    ]
