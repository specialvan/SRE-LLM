from __future__ import annotations

import importlib
import json
import subprocess
import struct
import zlib
from pathlib import Path

import pytest


def _png_bytes(width=8, height=6, color=(20, 40, 60, 255)):
    def chunk(kind, data):
        payload = kind + data
        return struct.pack(">I", len(data)) + payload + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)

    rows = []
    for y in range(height):
        row = bytearray(bytes(color) * width)
        if y == height - 1:
            row[-4:] = bytes(((color[0] + 90) % 256, color[1], color[2], color[3]))
        rows.append(b"\x00" + bytes(row))
    raw_rows = b"".join(rows)
    return b"\x89PNG\r\n\x1a\n" + chunk(
        b"IHDR",
        struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0),
    ) + chunk(b"IDAT", zlib.compress(raw_rows)) + chunk(b"IEND", b"")


def _blank_png_bytes(width=8, height=6):
    def chunk(kind, data):
        payload = kind + data
        return struct.pack(">I", len(data)) + payload + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)

    raw_rows = b"".join(b"\x00" + bytes((255, 255, 255, 255)) * width for _ in range(height))
    return b"\x89PNG\r\n\x1a\n" + chunk(
        b"IHDR",
        struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0),
    ) + chunk(b"IDAT", zlib.compress(raw_rows)) + chunk(b"IEND", b"")


def _valid_dom_for_payload(payload):
    def fmt(value):
        return f"{float(value):.2f}".rstrip("0").rstrip(".")

    summary = payload["summary"]
    events = payload["events"]
    first = payload["timeline"][0]
    selected = payload["timeline"][1]
    event = selected["event_details"][0]
    alloc_html = "".join(f"<p>{share:.2f} RPS</p>" for share in selected["alloc_shares"])
    return f'''
    <p id="hero-subtitle">loaded</p>
    <code id="frontend-contract-version">{payload["frontend_contract"]["version"]} · {payload["frontend_contract"]["api_path"]}</code>
    <strong id="bar-ticks">{summary["ticks"]}</strong>
    <strong id="bar-degraded">{summary["degraded_ticks"]}</strong>
    <strong id="bar-events">{fmt(summary["event_visible_fraction"] * 100)}%</strong>
    <strong id="bar-canary">{fmt(summary["canary_share_pct"])}%</strong>
    <strong id="bar-replicas">{summary["current_replicas"]}</strong>
    <strong id="metric-peak">{summary["peak_forecast_rps"]}</strong>
    <div id="series-chart"><svg></svg></div>
    <div id="timeline-meta">{len(payload["timeline"])} / {len(payload["timeline"])} 拍</div>
    <article class="timeline-row"><strong>{first["replicas_next"]} 个副本 · 观测 {first["observed_rps"]:.0f} RPS</strong><p>预测 {first["forecast_rps"]:.0f} RPS</p><div class="tick">{first["pool_connections"]}<br>连接</div></article>
    <div id="events-meta">{events["distinct_kinds"]} 类事件 · {events["total"]} 条</div>
    <div id="tick-event-details"><strong>{event["kind"]}</strong><p>阶段：{event["stage"]} · {event["detail"]}</p><p>安全动作：{event["safe_action"]}</p></div>
    <div id="tick-alloc-shares">{alloc_html}</div>
    <div id="event-kind-lens-list"><button data-event-kind="{event["kind"]}">kind</button></div>
    <div id="safety-budget-list"><button class="budget-item" data-budget-focus="allocation">分配余量</button></div>
    <div id="capacity-budget-list"><button class="capacity-item" data-capacity-focus="slot">槽位压力</button></div>
    <div data-smoke-budget="allocation" data-smoke-kind-lens="kind" data-smoke-budget="allocation" data-smoke-lens="stage" data-smoke-filter="events" data-smoke-chart="pool" data-smoke-view="modules" data-smoke-density="compact" data-smoke-share-hash="#share=tick%3D1" data-smoke-reset-filter="all" data-smoke-reset-density="comfortable" data-smoke-density="compact" data-smoke-share-hash="#share=tick%3D1" data-smoke-reset-filter="all" data-smoke-reset-density="comfortable" data-smoke-density="compact" data-smoke-share-hash="#share=tick%3D1" data-smoke-reset-filter="all" data-smoke-reset-density="comfortable" data-smoke-selected-tick="1" data-smoke-visible-ticks="12"></div>
    '''


def test_control_center_browser_smoke_reports_missing_playwright(monkeypatch, capsys):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")

    monkeypatch.setattr(smoke, "sync_playwright", None)
    monkeypatch.setattr(smoke, "find_system_browser", lambda: None)

    exit_code = smoke.main(["--port", "0"])
    output = capsys.readouterr().out

    assert exit_code == 2
    assert "playwright is not installed" in output
    assert "python -m scripts.control_center_browser_smoke" in output


def test_control_center_browser_smoke_rejects_non_loopback_host_by_default(monkeypatch):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")

    monkeypatch.setattr(smoke, "sync_playwright", None)
    monkeypatch.setattr(smoke, "find_system_browser", lambda: Path("C:/Browser/browser.exe"))

    with pytest.raises(ValueError, match="Refusing to bind"):
        smoke.main(["--host", "0.0.0.0", "--port", "0"])


def test_control_center_browser_smoke_allows_explicit_non_loopback_override(monkeypatch, tmp_path):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    calls = []

    monkeypatch.setattr(smoke, "sync_playwright", None)
    monkeypatch.setattr(smoke, "find_system_browser", lambda: Path("C:/Browser/browser.exe"))
    monkeypatch.setattr(smoke, "fetch_live_control_center_api_response", lambda url: smoke.LiveApiResponse(payload=smoke.build_control_center_payload(), metadata={}))
    monkeypatch.setattr(
        smoke,
        "fetch_live_control_center_health_response",
        lambda url: smoke.LiveApiResponse(payload={"status": "ok"}, metadata={}),
    )
    monkeypatch.setattr(smoke, "fetch_live_control_center_frontend_response", lambda url: {})
    monkeypatch.setattr(smoke, "write_api_snapshot", lambda *args, **kwargs: None)
    monkeypatch.setattr(smoke, "write_evidence_manifest", lambda *args, **kwargs: None)
    monkeypatch.setattr(smoke, "verify_evidence_manifest", lambda path: None)
    monkeypatch.setattr(smoke, "_run_system_browser_smoke", lambda **kwargs: calls.append(kwargs))

    exit_code = smoke.main([
        "--host",
        "0.0.0.0",
        "--allow-non-loopback",
        "--port",
        "0",
        "--screenshot",
        str(tmp_path / "shot.png"),
        "--dom-dump",
        str(tmp_path / "dom.html"),
        "--api-snapshot",
        str(tmp_path / "api.json"),
        "--manifest",
        str(tmp_path / "manifest.json"),
    ])

    assert exit_code == 0
    assert calls


def test_control_center_browser_smoke_exposes_real_browser_assertions():
    smoke = importlib.import_module("scripts.control_center_browser_smoke")

    assert smoke.REQUIRED_SELECTORS == [
        "#frontend-contract-version",
        "#series-chart svg",
        "#timeline-list .timeline-row",
        "#tick-event-details",
        "#tick-alloc-shares",
        "#event-kind-lens-list button",
        "#safety-budget-list .budget-item",
        "#capacity-budget-list .capacity-item",
    ]
    assert "control-center-browser-smoke.png" in smoke.DEFAULT_SCREENSHOT.name
    assert "control-center-browser-smoke.html" in smoke.DEFAULT_DOM_DUMP.name
    assert "control-center-browser-smoke-api.json" in smoke.DEFAULT_API_SNAPSHOT.name
    assert "control-center-browser-smoke-manifest.json" in smoke.DEFAULT_MANIFEST.name
    assert smoke.SMOKE_VIEWPORTS == [
        smoke.SmokeViewport("desktop", 1440, 960),
        smoke.SmokeViewport("mobile", 390, 844),
    ]








def test_control_center_browser_smoke_verifies_evidence_manifest(monkeypatch, tmp_path):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    live_payload = smoke.build_control_center_payload()
    verified = []

    def fake_run_system_browser_smoke(**kwargs):
        kwargs["screenshot_path"].write_bytes(
            _png_bytes(width=kwargs["viewport"].width, height=kwargs["viewport"].height)
        )
        kwargs["dom_dump_path"].write_text("dom", encoding="utf-8")

    monkeypatch.setattr(smoke, "sync_playwright", None)
    monkeypatch.setattr(smoke, "find_system_browser", lambda: Path("C:/Browser/browser.exe"))
    monkeypatch.setattr(smoke, "fetch_live_control_center_payload", lambda url: live_payload)
    monkeypatch.setattr(smoke, "_run_system_browser_smoke", fake_run_system_browser_smoke)
    monkeypatch.setattr(smoke, "verify_evidence_manifest", lambda path: verified.append(path))

    exit_code = smoke.main([
        "--port",
        "0",
        "--screenshot",
        str(tmp_path / "shot.png"),
        "--dom-dump",
        str(tmp_path / "dom.html"),
        "--api-snapshot",
        str(tmp_path / "api.json"),
        "--manifest",
        str(tmp_path / "manifest.json"),
    ])

    assert exit_code == 0
    assert verified == [tmp_path / "manifest.json"]

def test_control_center_browser_smoke_writes_evidence_manifest(monkeypatch, tmp_path):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    live_payload = smoke.build_control_center_payload()
    live_response = smoke.LiveApiResponse(
        payload=live_payload,
        metadata={
            "status": 200,
            "content_type": "application/json; charset=utf-8",
            "cache_control": "no-store",
            "contract_header": "control-center.v1",
            "api_header": "/api/control-center",
        },
    )
    health_response = smoke.LiveApiResponse(
        payload={
            "status": "ok",
            "contract": {"version": "control-center.v1", "api_path": "/api/control-center"},
            "routes": {"frontend": "/control-center", "api": "/api/control-center"},
        },
        metadata=live_response.metadata,
    )
    frontend_response = {"status": 200, "content_type": "text/html; charset=utf-8", "api_url": "/api/control-center"}
    manifests = []

    def fake_run_system_browser_smoke(**kwargs):
        kwargs["screenshot_path"].write_bytes(b"png")
        kwargs["dom_dump_path"].write_text("dom", encoding="utf-8")

    monkeypatch.setattr(smoke, "sync_playwright", None)
    monkeypatch.setattr(smoke, "find_system_browser", lambda: Path("C:/Browser/browser.exe"))
    monkeypatch.setattr(smoke, "fetch_live_control_center_api_response", lambda url: live_response)
    monkeypatch.setattr(smoke, "fetch_live_control_center_health_response", lambda url: health_response)
    monkeypatch.setattr(smoke, "fetch_live_control_center_frontend_response", lambda url: frontend_response)
    monkeypatch.setattr(smoke, "write_api_snapshot", lambda path, payload: path.write_text(json.dumps(payload), encoding="utf-8"))
    monkeypatch.setattr(smoke, "_run_system_browser_smoke", fake_run_system_browser_smoke)
    monkeypatch.setattr(smoke, "write_evidence_manifest", lambda *args, **kwargs: manifests.append((args, kwargs)))
    monkeypatch.setattr(smoke, "verify_evidence_manifest", lambda path: None)

    exit_code = smoke.main([
        "--port",
        "0",
        "--screenshot",
        str(tmp_path / "shot.png"),
        "--dom-dump",
        str(tmp_path / "dom.html"),
        "--api-snapshot",
        str(tmp_path / "api.json"),
        "--manifest",
        str(tmp_path / "manifest.json"),
    ])

    assert exit_code == 0
    assert len(manifests) == 1
    args, kwargs = manifests[0]
    assert args[0] == tmp_path / "manifest.json"
    assert kwargs["payload"] is live_payload
    assert kwargs["api_snapshot"] == tmp_path / "api.json"
    assert kwargs["api_response"] == live_response.metadata
    assert kwargs["health_response"] == {**health_response.metadata, "payload": health_response.payload}
    assert kwargs["frontend_response"] == frontend_response
    assert [item["viewport"].name for item in kwargs["viewport_artifacts"]] == ["desktop", "mobile"]

def test_write_api_snapshot_validates_contract(tmp_path):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    payload = smoke.build_control_center_payload()
    path = tmp_path / "api.json"

    smoke.write_api_snapshot(path, payload)

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["frontend_contract"]["version"] == "control-center.v1"
    assert saved["summary"]["ticks"] == payload["summary"]["ticks"]


def test_write_api_snapshot_rejects_invalid_contract(tmp_path):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    payload = smoke.build_broken_control_center_payload()

    try:
        smoke.write_api_snapshot(tmp_path / "api.json", payload)
    except AssertionError as exc:
        assert "live API payload violates contract" in str(exc)
    else:
        raise AssertionError("invalid API snapshot was not rejected")


def test_control_center_browser_smoke_writes_live_api_snapshot(monkeypatch, tmp_path):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    live_payload = smoke.build_control_center_payload()
    live_response = smoke.LiveApiResponse(payload=live_payload, metadata={})
    snapshots = []

    monkeypatch.setattr(smoke, "sync_playwright", None)
    monkeypatch.setattr(smoke, "find_system_browser", lambda: Path("C:/Browser/browser.exe"))
    monkeypatch.setattr(smoke, "fetch_live_control_center_api_response", lambda url: live_response)
    monkeypatch.setattr(smoke, "write_api_snapshot", lambda path, payload: snapshots.append((path, payload)))
    monkeypatch.setattr(smoke, "write_evidence_manifest", lambda *args, **kwargs: None)
    monkeypatch.setattr(smoke, "verify_evidence_manifest", lambda path: None)
    monkeypatch.setattr(smoke, "_run_system_browser_smoke", lambda **kwargs: None)

    exit_code = smoke.main([
        "--port",
        "0",
        "--screenshot",
        str(tmp_path / "shot.png"),
        "--dom-dump",
        str(tmp_path / "dom.html"),
        "--api-snapshot",
        str(tmp_path / "api.json"),
    ])

    assert exit_code == 0
    assert snapshots == [(tmp_path / "api.json", live_payload)]

def test_fetch_live_payload_reads_running_api(monkeypatch):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    captured = {}

    class FakeResponse:
        status = 200

        def getheader(self, name, default=None):
            headers = {
                "Content-Type": "application/json; charset=utf-8",
                "Cache-Control": "no-store",
                "X-Control-Center-Contract": "control-center.v1",
                "X-Control-Center-API": "/api/control-center",
            }
            return headers.get(name, default)

        def read(self):
            return json.dumps({"summary": {"ticks": 3}}).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["host"] = request.headers.get("Host")
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(smoke.urllib.request, "urlopen", fake_urlopen)

    payload = smoke.fetch_live_control_center_payload("http://127.0.0.1:1234/control-center")

    assert payload == {"summary": {"ticks": 3}}
    assert captured == {
        "url": "http://127.0.0.1:1234/api/control-center",
        "host": "127.0.0.1:1234",
        "timeout": 10,
    }


def test_fetch_live_control_center_api_response_captures_http_metadata(monkeypatch):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")

    class FakeResponse:
        status = 200

        def getheader(self, name, default=None):
            headers = {
                "Content-Type": "application/json; charset=utf-8",
                "Cache-Control": "no-store",
                "X-Control-Center-Contract": "control-center.v1",
                "X-Control-Center-API": "/api/control-center",
            }
            return headers.get(name, default)

        def read(self):
            return json.dumps({"summary": {"ticks": 3}}).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(smoke.urllib.request, "urlopen", lambda request, timeout: FakeResponse())

    api_response = smoke.fetch_live_control_center_api_response("http://127.0.0.1:1234/control-center")

    assert api_response.payload == {"summary": {"ticks": 3}}
    assert api_response.metadata == {
        "status": 200,
        "content_type": "application/json; charset=utf-8",
        "cache_control": "no-store",
        "contract_header": "control-center.v1",
        "api_header": "/api/control-center",
    }


def test_fetch_live_control_center_health_response_captures_payload_and_metadata(monkeypatch):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")

    class FakeResponse:
        status = 200

        def getheader(self, name, default=None):
            headers = {
                "Content-Type": "application/json; charset=utf-8",
                "Cache-Control": "no-store",
                "X-Control-Center-Contract": "control-center.v1",
                "X-Control-Center-API": "/api/control-center",
            }
            return headers.get(name, default)

        def read(self):
            return json.dumps({"status": "ok", "contract": {"version": "control-center.v1", "api_path": "/api/control-center"}}).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        return FakeResponse()

    monkeypatch.setattr(smoke.urllib.request, "urlopen", fake_urlopen)

    health_response = smoke.fetch_live_control_center_health_response("http://127.0.0.1:1234/control-center")

    assert captured["url"] == "http://127.0.0.1:1234/api/control-center/health"
    assert health_response.payload["status"] == "ok"
    assert health_response.metadata["contract_header"] == "control-center.v1"


def test_fetch_live_control_center_frontend_response_captures_api_url(monkeypatch):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")

    class FakeResponse:
        status = 200

        def getheader(self, name, default=None):
            headers = {
                "Content-Type": "text/html; charset=utf-8",
                "Cache-Control": "no-store",
                "X-Control-Center-Contract": "control-center.v1",
                "X-Control-Center-API": "/api/control-center",
            }
            return headers.get(name, default)

        def read(self):
            return b'<script>const API_URL = "/api/control-center";</script>'

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["host"] = request.headers.get("Host")
        return FakeResponse()

    monkeypatch.setattr(smoke.urllib.request, "urlopen", fake_urlopen)

    frontend_response = smoke.fetch_live_control_center_frontend_response("http://127.0.0.1:1234/control-center")

    assert captured == {"url": "http://127.0.0.1:1234/control-center", "host": "127.0.0.1:1234"}
    assert frontend_response == {
        "status": 200,
        "content_type": "text/html; charset=utf-8",
        "cache_control": "no-store",
        "contract_header": "control-center.v1",
        "api_header": "/api/control-center",
        "api_url": "/api/control-center",
    }


def test_control_center_browser_smoke_uses_live_api_payload(monkeypatch, tmp_path):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    live_payload = smoke.build_control_center_payload()
    live_response = smoke.LiveApiResponse(payload=live_payload, metadata={})
    calls = []

    monkeypatch.setattr(smoke, "sync_playwright", None)
    monkeypatch.setattr(smoke, "find_system_browser", lambda: Path("C:/Browser/browser.exe"))
    monkeypatch.setattr(smoke, "fetch_live_control_center_api_response", lambda url: live_response)
    monkeypatch.setattr(smoke, "write_evidence_manifest", lambda *args, **kwargs: None)
    monkeypatch.setattr(smoke, "verify_evidence_manifest", lambda path: None)
    monkeypatch.setattr(smoke, "_run_system_browser_smoke", lambda **kwargs: calls.append(kwargs))

    exit_code = smoke.main([
        "--port",
        "0",
        "--screenshot",
        str(tmp_path / "shot.png"),
        "--dom-dump",
        str(tmp_path / "dom.html"),
        "--api-snapshot",
        str(tmp_path / "api.json"),
        "--manifest",
        str(tmp_path / "manifest.json"),
    ])

    assert exit_code == 0
    assert calls
    assert calls[0]["payload"] is live_payload
    assert calls[1]["payload"] is live_payload

def test_control_center_browser_smoke_can_use_system_browser_fallback(monkeypatch, tmp_path):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    calls = []

    monkeypatch.setattr(smoke, "sync_playwright", None)
    monkeypatch.setattr(smoke, "find_system_browser", lambda: Path("C:/Browser/browser.exe"))
    monkeypatch.setattr(
        smoke,
        "_run_system_browser_smoke",
        lambda **kwargs: calls.append(kwargs),
    )
    monkeypatch.setattr(smoke, "write_evidence_manifest", lambda *args, **kwargs: None)
    monkeypatch.setattr(smoke, "verify_evidence_manifest", lambda path: None)

    exit_code = smoke.main([
        "--port",
        "0",
        "--screenshot",
        str(tmp_path / "shot.png"),
        "--dom-dump",
        str(tmp_path / "dom.html"),
        "--api-snapshot",
        str(tmp_path / "api.json"),
        "--manifest",
        str(tmp_path / "manifest.json"),
    ])

    assert exit_code == 0
    assert calls
    assert calls[0]["browser_path"] == Path("C:/Browser/browser.exe")
    assert calls[0]["screenshot_path"] == tmp_path / "shot-desktop.png"
    assert calls[0]["dom_dump_path"] == tmp_path / "dom-desktop.html"
    assert calls[0]["viewport"].name == "desktop"
    assert calls[1]["screenshot_path"] == tmp_path / "shot-mobile.png"
    assert calls[1]["dom_dump_path"] == tmp_path / "dom-mobile.html"
    assert calls[1]["viewport"].name == "mobile"




def test_playwright_smoke_writes_dom_dump_and_checks_payload(monkeypatch, tmp_path):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    calls = []
    payload = {"summary": {"ticks": 2}}

    class FakeLocator:
        @property
        def first(self):
            return self

        def wait_for(self, **kwargs):
            return None

        def inner_text(self):
            return "control-center.v1 · /api/control-center"

        def count(self):
            return 2

        def nth(self, index):
            return self

        def click(self):
            return None

    class FakePage:
        def on(self, *args, **kwargs):
            return None

        def goto(self, *args, **kwargs):
            return None

        def locator(self, selector):
            return FakeLocator()

        def content(self):
            return "<html><body>rendered</body></html>"

        def screenshot(self, path, full_page):
            Path(path).write_bytes(b"png")

    class FakeBrowser:
        def new_page(self, viewport):
            calls.append(("viewport", viewport))
            return FakePage()

        def close(self):
            calls.append(("closed", True))

    class FakeChromium:
        def launch(self, headless):
            calls.append(("headless", headless))
            return FakeBrowser()

    class FakePlaywright:
        chromium = FakeChromium()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(smoke, "sync_playwright", lambda: FakePlaywright())
    monkeypatch.setattr(
        smoke,
        "_assert_dumped_dom",
        lambda dom, got_payload=None: calls.append(("asserted", dom, got_payload)),
    )

    smoke._run_browser_smoke(
        url="http://127.0.0.1:1/control-center",
        screenshot_path=tmp_path / "shot.png",
        dom_dump_path=tmp_path / "dom.html",
        headed=False,
        viewport=smoke.SmokeViewport("desktop", 1440, 960),
        payload=payload,
    )

    assert ("asserted", "<html><body>rendered</body></html>", payload) in calls
    assert (tmp_path / "dom.html").read_text(encoding="utf-8") == "<html><body>rendered</body></html>"
    assert (tmp_path / "shot.png").read_bytes() == b"png"

def test_system_browser_smoke_decodes_utf8_dom_dump(monkeypatch, tmp_path):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    screenshot = tmp_path / "shot.png"

    def fake_run(*args, **kwargs):
        screenshot.write_bytes(b"png")
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout=(
                "control-center.v1 timeline-row series-chart tick-event-details "
                "tick-alloc-shares event-kind-lens-list safety-budget-list data-budget-focus capacity-budget-list data-capacity-focus data-smoke-kind-lens=\"kind\" data-smoke-budget=\"allocation\" data-smoke-lens=\"stage\" "
                "data-smoke-filter=\"events\" data-smoke-chart=\"pool\" data-smoke-view=\"modules\" data-smoke-density=\"compact\" data-smoke-share-hash=\"#share=tick%3D1\" data-smoke-reset-filter=\"all\" data-smoke-reset-density=\"comfortable\" data-smoke-selected-tick=\"1\" data-smoke-visible-ticks=\"12\" 星舰"
            ).encode("utf-8"),
            stderr=b"",
        )

    monkeypatch.setattr(smoke.subprocess, "run", fake_run)

    smoke._run_system_browser_smoke(
        url="http://127.0.0.1:1/control-center",
        browser_path=Path("C:/Browser/browser.exe"),
        screenshot_path=screenshot,
        dom_dump_path=tmp_path / "dom.html",
    )

    assert "星舰" in (tmp_path / "dom.html").read_text(encoding="utf-8")


def test_system_browser_smoke_gives_async_fetch_time(monkeypatch, tmp_path):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    screenshot = tmp_path / "shot.png"
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        screenshot.write_bytes(b"png")
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=(
                "control-center.v1 timeline-row series-chart tick-event-details "
                "tick-alloc-shares event-kind-lens-list safety-budget-list data-budget-focus capacity-budget-list data-capacity-focus data-smoke-kind-lens=\"kind\" data-smoke-budget=\"allocation\" data-smoke-lens=\"stage\" "
                "data-smoke-filter=\"events\" data-smoke-chart=\"pool\" data-smoke-view=\"modules\" data-smoke-density=\"compact\" data-smoke-share-hash=\"#share=tick%3D1\" data-smoke-reset-filter=\"all\" data-smoke-reset-density=\"comfortable\" data-smoke-selected-tick=\"1\" data-smoke-visible-ticks=\"12\""
            ).encode("utf-8"),
            stderr=b"",
        )

    monkeypatch.setattr(smoke.subprocess, "run", fake_run)

    smoke._run_system_browser_smoke(
        url="http://127.0.0.1:1/control-center",
        browser_path=Path("C:/Browser/browser.exe"),
        screenshot_path=screenshot,
        dom_dump_path=tmp_path / "dom.html",
    )

    assert "--virtual-time-budget=10000" in captured["command"]
    assert "--run-all-compositor-stages-before-draw" in captured["command"]




def test_system_browser_smoke_uses_viewport_window_size(monkeypatch, tmp_path):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    screenshot = tmp_path / "shot.png"
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        screenshot.write_bytes(b"png")
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=(
                'control-center.v1 timeline-row series-chart tick-event-details '
                'tick-alloc-shares event-kind-lens-list safety-budget-list data-budget-focus capacity-budget-list data-capacity-focus data-smoke-budget="allocation" data-smoke-kind-lens="kind" data-smoke-lens="kind" '
                'data-smoke-filter="events" data-smoke-chart="pool" '
                'data-smoke-view="modules" data-smoke-density="compact" data-smoke-share-hash="#share=tick%3D1" data-smoke-reset-filter="all" data-smoke-reset-density="comfortable" data-smoke-selected-tick="1" '
                'data-smoke-visible-ticks="12"'
            ).encode("utf-8"),
            stderr=b"",
        )

    monkeypatch.setattr(smoke.subprocess, "run", fake_run)

    smoke._run_system_browser_smoke(
        url="http://127.0.0.1:1/control-center",
        browser_path=Path("C:/Browser/browser.exe"),
        screenshot_path=screenshot,
        dom_dump_path=tmp_path / "dom.html",
        viewport=smoke.SmokeViewport("mobile", 390, 844),
    )

    assert "--window-size=390,844" in captured["command"]

def test_system_browser_smoke_opens_smoke_interaction_hash(monkeypatch, tmp_path):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    screenshot = tmp_path / "shot.png"
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        screenshot.write_bytes(b"png")
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=(
                'control-center.v1 timeline-row series-chart tick-event-details '
                'tick-alloc-shares event-kind-lens-list safety-budget-list data-budget-focus capacity-budget-list data-capacity-focus data-smoke-budget="allocation" data-smoke-kind-lens="kind" data-smoke-lens="kind" '
                'data-smoke-filter="events" data-smoke-chart="pool" data-smoke-view="modules" data-smoke-density="compact" data-smoke-share-hash="#share=tick%3D1" data-smoke-reset-filter="all" data-smoke-reset-density="comfortable" data-smoke-selected-tick="1" data-smoke-visible-ticks="12"'
            ).encode("utf-8"),
            stderr=b"",
        )

    monkeypatch.setattr(smoke.subprocess, "run", fake_run)

    smoke._run_system_browser_smoke(
        url="http://127.0.0.1:1/control-center",
        browser_path=Path("C:/Browser/browser.exe"),
        screenshot_path=screenshot,
        dom_dump_path=tmp_path / "dom.html",
    )

    assert captured["command"][-1].endswith("/control-center#smoke-interaction")
    assert not any(item.startswith("--script=") for item in captured["command"])


def test_control_center_browser_smoke_can_run_error_path(monkeypatch, tmp_path):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    calls = []
    manifests = []

    monkeypatch.setattr(smoke, "sync_playwright", None)
    monkeypatch.setattr(smoke, "find_system_browser", lambda: Path("C:/Browser/browser.exe"))
    monkeypatch.setattr(smoke, "_run_system_browser_error_smoke", lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(smoke, "write_error_evidence_manifest", lambda *args, **kwargs: manifests.append((args, kwargs)))
    monkeypatch.setattr(smoke, "verify_error_evidence_manifest", lambda path: None)

    exit_code = smoke.main([
        "--port",
        "0",
        "--expect-contract-error",
        "--screenshot",
        str(tmp_path / "error.png"),
        "--dom-dump",
        str(tmp_path / "error.html"),
        "--error-manifest",
        str(tmp_path / "error-manifest.json"),
    ])

    assert exit_code == 0
    assert len(calls) == 1
    assert calls[0]["viewport"].name == "desktop"
    assert calls[0]["screenshot_path"] == tmp_path / "error-desktop.png"
    assert calls[0]["dom_dump_path"] == tmp_path / "error-desktop.html"
    assert len(manifests) == 1
    assert manifests[0][0][0] == tmp_path / "error-manifest.json"


def test_control_center_browser_smoke_can_run_frontend_contract_error_path(monkeypatch, tmp_path):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    calls = []
    manifests = []

    monkeypatch.setattr(smoke, "sync_playwright", None)
    monkeypatch.setattr(smoke, "find_system_browser", lambda: Path("C:/Browser/browser.exe"))
    monkeypatch.setattr(smoke, "_run_system_browser_frontend_contract_smoke", lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(smoke, "write_frontend_error_evidence_manifest", lambda *args, **kwargs: manifests.append((args, kwargs)))
    monkeypatch.setattr(smoke, "verify_frontend_error_evidence_manifest", lambda path: None)

    exit_code = smoke.main([
        "--port",
        "0",
        "--expect-frontend-contract-error",
        "--screenshot",
        str(tmp_path / "frontend-error.png"),
        "--dom-dump",
        str(tmp_path / "frontend-error.html"),
        "--frontend-error-manifest",
        str(tmp_path / "frontend-error-manifest.json"),
    ])

    assert exit_code == 0
    assert len(calls) == 1
    assert calls[0]["viewport"].name == "desktop"
    assert calls[0]["screenshot_path"] == tmp_path / "frontend-error-desktop.png"
    assert calls[0]["dom_dump_path"] == tmp_path / "frontend-error-desktop.html"
    assert len(manifests) == 1
    assert manifests[0][0][0] == tmp_path / "frontend-error-manifest.json"


def test_frontend_contract_error_defaults_do_not_reuse_normal_artifacts():
    smoke = importlib.import_module("scripts.control_center_browser_smoke")

    assert smoke.DEFAULT_ERROR_SCREENSHOT != smoke.DEFAULT_SCREENSHOT
    assert smoke.DEFAULT_ERROR_DOM_DUMP != smoke.DEFAULT_DOM_DUMP
    assert smoke.DEFAULT_FRONTEND_ERROR_SCREENSHOT != smoke.DEFAULT_SCREENSHOT
    assert smoke.DEFAULT_FRONTEND_ERROR_DOM_DUMP != smoke.DEFAULT_DOM_DUMP
    assert "error" in smoke.DEFAULT_ERROR_SCREENSHOT.name
    assert "error" in smoke.DEFAULT_ERROR_DOM_DUMP.name
    assert "frontend-error" in smoke.DEFAULT_FRONTEND_ERROR_SCREENSHOT.name
    assert "frontend-error" in smoke.DEFAULT_FRONTEND_ERROR_DOM_DUMP.name


def test_control_center_browser_smoke_can_verify_frontend_error_manifest_without_browser(monkeypatch, tmp_path, capsys):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    manifest_path = tmp_path / "frontend-error-manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")
    verified = []

    monkeypatch.setattr(smoke, "sync_playwright", None)
    monkeypatch.setattr(smoke, "find_system_browser", lambda: (_ for _ in ()).throw(AssertionError("browser lookup should not run")))
    monkeypatch.setattr(smoke, "_start_server", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("server should not start")))
    monkeypatch.setattr(smoke, "verify_frontend_error_evidence_manifest", lambda path: verified.append(path))

    exit_code = smoke.main(["--verify-frontend-error-manifest", str(manifest_path)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert verified == [manifest_path]
    assert f"frontend error manifest replay passed: {manifest_path}" in output

def test_control_center_handoff_documents_browser_smoke_command():
    handoff = (Path(__file__).resolve().parents[1] / "docs" / "CONTROL_CENTER_HANDOFF.md").read_text(
        encoding="utf-8"
    )

    assert "python -m scripts.control_center_browser_smoke" in handoff
    assert "python -m playwright install chromium" in handoff
    assert "--expect-contract-error" in handoff
    assert "--expect-frontend-contract-error" in handoff
    assert "--verify-all-manifests" in handoff
    assert "normal, backend contract-error, and frontend contract-error manifests" in handoff
    assert "--verify-frontend-error-manifest analysis/artifacts/control-center-browser-frontend-error-smoke-manifest.json" in handoff
    assert "--report-manifests" in handoff
    assert "--report-json" in handoff
    assert "control-center-browser-evidence-report.json" in handoff
    assert "python -m scripts.package_smoke" in handoff
    assert "control-center evidence report" in handoff
    assert "manifest_paths" in handoff
    assert "manifest_records" in handoff
    assert "manifest_paths=" in handoff
    assert "manifest_records=" in handoff
    assert "manifest_replay=normal+backend_error+frontend_error" in handoff
    assert "manifest_records=normal+backend_error+frontend_error" in handoff
    assert "manifest_replay=normal+backend_error+frontend_error" in handoff
    assert "replays the normal, backend contract-error, and frontend contract-error manifests" in handoff
    assert "verify_error_evidence_manifest" in handoff
    assert "--verify-error-manifest analysis/artifacts/control-center-browser-error-smoke-manifest.json" in handoff
    assert "control-center-browser-smoke-desktop.png" in handoff
    assert "control-center-browser-error-smoke-manifest.json" in handoff
    assert "control-center-browser-frontend-error-smoke-manifest.json" in handoff
    assert "control-center-browser-frontend-error-smoke-desktop.png" in handoff
    assert "control-center-browser-frontend-error-smoke-desktop.html" in handoff
    assert "control-center-browser-smoke-mobile.png" in handoff
    assert "control-center-browser-smoke-api.json" in handoff
    assert "control-center-browser-smoke-manifest.json" in handoff
    assert "--verify-manifest analysis/artifacts/control-center-browser-smoke-manifest.json" in handoff
    assert "verify_evidence_manifest" in handoff
    assert "/api/control-center/health" in handoff
    assert "api_response" in handoff
    assert "health_response" in handoff
    assert "frontend_response" in handoff
    assert "API_URL" in handoff
    assert "X-Control-Center-Contract" in handoff
    assert "PNG dimensions" in handoff
    assert "nonblank" in handoff
    assert "selected tick" in handoff
    assert "event details" in handoff
    assert "allocation shares" in handoff
    assert "control_center_contract_violation" in handoff
    assert "missing required frontend field" in handoff
    assert "前端契约校验失败" in handoff
    assert "malformed HTTP-200" in handoff
    assert "verify_frontend_error_evidence_manifest" in handoff
    assert "frontend_error" in handoff
    assert "contract_depth" in handoff
    assert "top_level" in handoff
    assert "object_groups" in handoff
    assert "object_fields" in handoff
    assert "array_item_groups" in handoff
    assert "array_item_fields" in handoff
    assert "timeline_fields" in handoff
    assert "DOM dumps" in handoff
    assert "payload-aware assertions" in handoff
    assert "live API payload" in handoff
    assert "sha256" in handoff
