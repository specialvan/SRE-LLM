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








def test_write_evidence_manifest_records_artifacts(tmp_path):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    api = tmp_path / "api.json"
    desktop_png = tmp_path / "desktop.png"
    desktop_html = tmp_path / "desktop.html"
    mobile_png = tmp_path / "mobile.png"
    mobile_html = tmp_path / "mobile.html"
    manifest_path = tmp_path / "manifest.json"
    payload = smoke.build_control_center_payload()
    api.write_text(json.dumps(payload), encoding="utf-8")
    desktop_png.write_bytes(_png_bytes(width=1440, height=960))
    desktop_html.write_text("desktop-dom", encoding="utf-8")
    mobile_png.write_bytes(_png_bytes(width=390, height=844))
    mobile_html.write_text("mobile-dom", encoding="utf-8")

    smoke.write_evidence_manifest(
        manifest_path,
        url="http://127.0.0.1:8765/control-center",
        payload=payload,
        api_snapshot=api,
        viewport_artifacts=[
            {
                "viewport": smoke.SmokeViewport("desktop", 1440, 960),
                "screenshot": desktop_png,
                "dom_dump": desktop_html,
            },
            {
                "viewport": smoke.SmokeViewport("mobile", 390, 844),
                "screenshot": mobile_png,
                "dom_dump": mobile_html,
            },
        ],
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["url"] == "http://127.0.0.1:8765/control-center"
    assert manifest["contract"] == {"version": "control-center.v1", "api_path": "/api/control-center"}
    assert manifest["api_response"] == {
        "status": 200,
        "content_type": "application/json; charset=utf-8",
        "cache_control": "no-store",
        "contract_header": "control-center.v1",
        "api_header": "/api/control-center",
    }
    assert manifest["health_response"] == {
        "status": 200,
        "content_type": "application/json; charset=utf-8",
        "cache_control": "no-store",
        "contract_header": "control-center.v1",
        "api_header": "/api/control-center",
        "payload": {
            "status": "ok",
            "contract": {"version": "control-center.v1", "api_path": "/api/control-center"},
            "routes": {"frontend": "/control-center", "api": "/api/control-center"},
        },
    }
    assert manifest["frontend_response"] == {
        "status": 200,
        "content_type": "text/html; charset=utf-8",
        "cache_control": "no-store",
        "contract_header": "control-center.v1",
        "api_header": "/api/control-center",
        "api_url": "/api/control-center",
    }
    assert manifest["api_snapshot"]["path"].endswith("api.json")
    assert manifest["api_snapshot"]["bytes"] == api.stat().st_size
    assert len(manifest["viewports"]) == 2
    assert manifest["viewports"][0]["name"] == "desktop"
    assert manifest["viewports"][0]["width"] == 1440
    assert manifest["viewports"][0]["screenshot"]["png"] == {
        "width": 1440,
        "height": 960,
        "blank": False,
    }
    assert manifest["viewports"][0]["screenshot"]["sha256"]
    assert manifest["viewports"][0]["dom_dump"]["bytes"] == desktop_html.stat().st_size


def test_write_evidence_manifest_uses_relative_artifact_paths(tmp_path):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    api = tmp_path / "api.json"
    shot = tmp_path / "desktop.png"
    dom = tmp_path / "desktop.html"
    manifest_path = tmp_path / "manifest.json"
    payload = smoke.build_control_center_payload()
    smoke.write_api_snapshot(api, payload)
    shot.write_bytes(_png_bytes(width=1440, height=960))
    dom.write_text(_valid_dom_for_payload(payload), encoding="utf-8")

    smoke.write_evidence_manifest(
        manifest_path,
        url="http://127.0.0.1:8765/control-center",
        payload=payload,
        api_snapshot=api,
        viewport_artifacts=[
            {"viewport": smoke.SmokeViewport("desktop", 1440, 960), "screenshot": shot, "dom_dump": dom}
        ],
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifact_paths = [
        manifest["api_snapshot"]["path"],
        manifest["viewports"][0]["screenshot"]["path"],
        manifest["viewports"][0]["dom_dump"]["path"],
    ]
    assert artifact_paths == ["api.json", "desktop.png", "desktop.html"]
    assert all(not Path(path).is_absolute() for path in artifact_paths)




def test_verify_evidence_manifest_accepts_complete_manifest(tmp_path):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    api = tmp_path / "api.json"
    shot = tmp_path / "desktop.png"
    dom = tmp_path / "desktop.html"
    manifest_path = tmp_path / "manifest.json"
    payload = smoke.build_control_center_payload()
    smoke.write_api_snapshot(api, payload)
    shot.write_bytes(_png_bytes(width=1440, height=960))
    dom.write_text(_valid_dom_for_payload(payload), encoding="utf-8")
    smoke.write_evidence_manifest(
        manifest_path,
        url="http://127.0.0.1:8765/control-center",
        payload=payload,
        api_snapshot=api,
        viewport_artifacts=[
            {"viewport": smoke.SmokeViewport("desktop", 1440, 960), "screenshot": shot, "dom_dump": dom}
        ],
    )

    smoke.verify_evidence_manifest(manifest_path)


def test_verify_evidence_manifest_rejects_hash_mismatch(tmp_path):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    api = tmp_path / "api.json"
    shot = tmp_path / "desktop.png"
    dom = tmp_path / "desktop.html"
    manifest_path = tmp_path / "manifest.json"
    payload = smoke.build_control_center_payload()
    smoke.write_api_snapshot(api, payload)
    shot.write_bytes(_png_bytes(width=1440, height=960))
    dom.write_text("control-center.v1", encoding="utf-8")
    smoke.write_evidence_manifest(
        manifest_path,
        url="http://127.0.0.1:8765/control-center",
        payload=payload,
        api_snapshot=api,
        viewport_artifacts=[
            {"viewport": smoke.SmokeViewport("desktop", 1440, 960), "screenshot": shot, "dom_dump": dom}
        ],
    )
    shot.write_bytes(_png_bytes(width=1400, height=900))

    try:
        smoke.verify_evidence_manifest(manifest_path)
    except AssertionError as exc:
        assert "manifest artifact mismatch" in str(exc)
    else:
        raise AssertionError("tampered artifact was not rejected")


def test_verify_evidence_manifest_rejects_absolute_artifact_paths(tmp_path):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    api = tmp_path / "api.json"
    shot = tmp_path / "desktop.png"
    dom = tmp_path / "desktop.html"
    manifest_path = tmp_path / "manifest.json"
    payload = smoke.build_control_center_payload()
    smoke.write_api_snapshot(api, payload)
    shot.write_bytes(_png_bytes(width=1440, height=960))
    dom.write_text(_valid_dom_for_payload(payload), encoding="utf-8")
    smoke.write_evidence_manifest(
        manifest_path,
        url="http://127.0.0.1:8765/control-center",
        payload=payload,
        api_snapshot=api,
        viewport_artifacts=[
            {"viewport": smoke.SmokeViewport("desktop", 1440, 960), "screenshot": shot, "dom_dump": dom}
        ],
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["api_snapshot"]["path"] = str(api.resolve())
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(AssertionError, match="absolute artifact path"):
        smoke.verify_evidence_manifest(manifest_path)


def test_verify_evidence_manifest_rejects_parent_artifact_paths(tmp_path):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    api = tmp_path / "api.json"
    shot = tmp_path / "desktop.png"
    dom = tmp_path / "desktop.html"
    manifest_path = tmp_path / "manifest.json"
    payload = smoke.build_control_center_payload()
    smoke.write_api_snapshot(api, payload)
    shot.write_bytes(_png_bytes(width=1440, height=960))
    dom.write_text(_valid_dom_for_payload(payload), encoding="utf-8")
    smoke.write_evidence_manifest(
        manifest_path,
        url="http://127.0.0.1:8765/control-center",
        payload=payload,
        api_snapshot=api,
        viewport_artifacts=[
            {"viewport": smoke.SmokeViewport("desktop", 1440, 960), "screenshot": shot, "dom_dump": dom}
        ],
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["viewports"][0]["dom_dump"]["path"] = "../desktop.html"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(AssertionError, match="parent traversal"):
        smoke.verify_evidence_manifest(manifest_path)


def test_verify_evidence_manifest_replays_dom_dump_against_api_snapshot(tmp_path):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    api = tmp_path / "api.json"
    shot = tmp_path / "desktop.png"
    dom = tmp_path / "desktop.html"
    manifest_path = tmp_path / "manifest.json"
    payload = smoke.build_control_center_payload()
    smoke.write_api_snapshot(api, payload)
    shot.write_bytes(_png_bytes(width=1440, height=960))
    dom.write_text("control-center.v1", encoding="utf-8")
    smoke.write_evidence_manifest(
        manifest_path,
        url="http://127.0.0.1:8765/control-center",
        payload=payload,
        api_snapshot=api,
        viewport_artifacts=[
            {"viewport": smoke.SmokeViewport("desktop", 1440, 960), "screenshot": shot, "dom_dump": dom}
        ],
    )
    dom.write_text("control-center.v1 timeline-row series-chart tick-event-details", encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["viewports"][0]["dom_dump"] = smoke._artifact_record(dom)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    try:
        smoke.verify_evidence_manifest(manifest_path)
    except AssertionError as exc:
        assert "browser DOM dump" in str(exc) or "frontend DOM" in str(exc)
    else:
        raise AssertionError("DOM dump mismatch was not rejected during manifest replay")


def test_verify_evidence_manifest_dom_error_includes_manifest_context(tmp_path):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    api = tmp_path / "api.json"
    shot = tmp_path / "desktop.png"
    dom = tmp_path / "desktop.html"
    manifest_path = tmp_path / "manifest.json"
    payload = smoke.build_control_center_payload()
    smoke.write_api_snapshot(api, payload)
    shot.write_bytes(_png_bytes(width=1440, height=960))
    dom.write_text("control-center.v1 timeline-row series-chart tick-event-details", encoding="utf-8")
    smoke.write_evidence_manifest(
        manifest_path,
        url="http://127.0.0.1:8765/control-center",
        payload=payload,
        api_snapshot=api,
        viewport_artifacts=[
            {"viewport": smoke.SmokeViewport("desktop", 1440, 960), "screenshot": shot, "dom_dump": dom}
        ],
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["viewports"][0]["dom_dump"] = smoke._artifact_record(dom)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(AssertionError) as excinfo:
        smoke.verify_evidence_manifest(manifest_path)

    message = str(excinfo.value)
    assert "normal manifest desktop DOM" in message
    assert str(manifest_path) in message
    assert str(dom) in message
    assert "python -m scripts.control_center_browser_smoke --report-manifests" in message


def test_verify_evidence_manifest_rejects_blank_screenshot(tmp_path):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    api = tmp_path / "api.json"
    shot = tmp_path / "desktop.png"
    dom = tmp_path / "desktop.html"
    manifest_path = tmp_path / "manifest.json"
    payload = smoke.build_control_center_payload()
    smoke.write_api_snapshot(api, payload)
    shot.write_bytes(_blank_png_bytes(width=1440, height=960))
    dom.write_text("control-center.v1", encoding="utf-8")
    smoke.write_evidence_manifest(
        manifest_path,
        url="http://127.0.0.1:8765/control-center",
        payload=payload,
        api_snapshot=api,
        viewport_artifacts=[
            {"viewport": smoke.SmokeViewport("desktop", 1440, 960), "screenshot": shot, "dom_dump": dom}
        ],
    )

    try:
        smoke.verify_evidence_manifest(manifest_path)
    except AssertionError as exc:
        assert "blank screenshot" in str(exc)
    else:
        raise AssertionError("blank screenshot was not rejected")


def test_verify_evidence_manifest_rejects_api_response_contract_mismatch(tmp_path):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    api = tmp_path / "api.json"
    shot = tmp_path / "desktop.png"
    dom = tmp_path / "desktop.html"
    manifest_path = tmp_path / "manifest.json"
    payload = smoke.build_control_center_payload()
    smoke.write_api_snapshot(api, payload)
    shot.write_bytes(_png_bytes(width=1440, height=960))
    dom.write_text("control-center.v1", encoding="utf-8")
    smoke.write_evidence_manifest(
        manifest_path,
        url="http://127.0.0.1:8765/control-center",
        payload=payload,
        api_snapshot=api,
        viewport_artifacts=[
            {"viewport": smoke.SmokeViewport("desktop", 1440, 960), "screenshot": shot, "dom_dump": dom}
        ],
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["api_response"]["contract_header"] = "stale"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    try:
        smoke.verify_evidence_manifest(manifest_path)
    except AssertionError as exc:
        assert "manifest API response metadata" in str(exc)
    else:
        raise AssertionError("stale API response metadata was not rejected")


def test_verify_evidence_manifest_rejects_health_response_contract_mismatch(tmp_path):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    api = tmp_path / "api.json"
    shot = tmp_path / "desktop.png"
    dom = tmp_path / "desktop.html"
    manifest_path = tmp_path / "manifest.json"
    payload = smoke.build_control_center_payload()
    smoke.write_api_snapshot(api, payload)
    shot.write_bytes(_png_bytes(width=1440, height=960))
    dom.write_text(_valid_dom_for_payload(payload), encoding="utf-8")
    smoke.write_evidence_manifest(
        manifest_path,
        url="http://127.0.0.1:8765/control-center",
        payload=payload,
        api_snapshot=api,
        viewport_artifacts=[
            {"viewport": smoke.SmokeViewport("desktop", 1440, 960), "screenshot": shot, "dom_dump": dom}
        ],
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["health_response"]["payload"]["contract"]["version"] = "stale"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    try:
        smoke.verify_evidence_manifest(manifest_path)
    except AssertionError as exc:
        assert "manifest health response" in str(exc)
    else:
        raise AssertionError("stale health response metadata was not rejected")


def test_verify_evidence_manifest_rejects_frontend_api_url_mismatch(tmp_path):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    api = tmp_path / "api.json"
    shot = tmp_path / "desktop.png"
    dom = tmp_path / "desktop.html"
    manifest_path = tmp_path / "manifest.json"
    payload = smoke.build_control_center_payload()
    smoke.write_api_snapshot(api, payload)
    shot.write_bytes(_png_bytes(width=1440, height=960))
    dom.write_text(_valid_dom_for_payload(payload), encoding="utf-8")
    smoke.write_evidence_manifest(
        manifest_path,
        url="http://127.0.0.1:8765/control-center",
        payload=payload,
        api_snapshot=api,
        viewport_artifacts=[
            {"viewport": smoke.SmokeViewport("desktop", 1440, 960), "screenshot": shot, "dom_dump": dom}
        ],
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["frontend_response"]["api_url"] = "/api/stale"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    try:
        smoke.verify_evidence_manifest(manifest_path)
    except AssertionError as exc:
        assert "manifest frontend response" in str(exc)
    else:
        raise AssertionError("stale frontend API URL was not rejected")


def test_write_error_evidence_manifest_records_error_artifacts(tmp_path):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    shot = tmp_path / "error.png"
    dom = tmp_path / "error.html"
    manifest_path = tmp_path / "error-manifest.json"
    shot.write_bytes(_png_bytes(width=1440, height=960))
    dom.write_text(
        '<p id="hero-subtitle">数据加载失败: HTTP 500 | control_center_contract_violation | timeline[0] missing required frontend field: observed_rps</p>',
        encoding="utf-8",
    )

    smoke.write_error_evidence_manifest(
        manifest_path,
        url="http://127.0.0.1:8765/control-center",
        viewport=smoke.SmokeViewport("desktop", 1440, 960),
        screenshot=shot,
        dom_dump=dom,
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["mode"] == "contract-error"
    assert manifest["url"] == "http://127.0.0.1:8765/control-center"
    assert manifest["viewport"]["name"] == "desktop"
    assert manifest["screenshot"]["png"] == {"width": 1440, "height": 960, "blank": False}
    assert manifest["dom_dump"]["bytes"] == dom.stat().st_size


def test_verify_error_evidence_manifest_rejects_missing_contract_details(tmp_path):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    shot = tmp_path / "error.png"
    dom = tmp_path / "error.html"
    manifest_path = tmp_path / "error-manifest.json"
    shot.write_bytes(_png_bytes(width=1440, height=960))
    dom.write_text('<p id="hero-subtitle">数据加载失败: HTTP 500</p>', encoding="utf-8")
    smoke.write_error_evidence_manifest(
        manifest_path,
        url="http://127.0.0.1:8765/control-center",
        viewport=smoke.SmokeViewport("desktop", 1440, 960),
        screenshot=shot,
        dom_dump=dom,
    )

    try:
        smoke.verify_error_evidence_manifest(manifest_path)
    except AssertionError as exc:
        assert "contract violation details" in str(exc)
    else:
        raise AssertionError("error manifest without contract details was not rejected")


def test_verify_frontend_error_evidence_manifest_rejects_missing_validator_details(tmp_path):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    shot = tmp_path / "frontend-error.png"
    dom = tmp_path / "frontend-error.html"
    manifest_path = tmp_path / "frontend-error-manifest.json"
    shot.write_bytes(_png_bytes(width=1440, height=960))
    dom.write_text('<p id="hero-subtitle">数据加载失败: API shape rejected</p>', encoding="utf-8")
    smoke.write_frontend_error_evidence_manifest(
        manifest_path,
        url="http://127.0.0.1:8765/control-center",
        viewport=smoke.SmokeViewport("desktop", 1440, 960),
        screenshot=shot,
        dom_dump=dom,
    )

    try:
        smoke.verify_frontend_error_evidence_manifest(manifest_path)
    except AssertionError as exc:
        assert "frontend contract validation failure" in str(exc)
    else:
        raise AssertionError("frontend error manifest without validator details was not rejected")


def test_verify_frontend_error_evidence_manifest_accepts_validator_details(tmp_path):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    shot = tmp_path / "frontend-error.png"
    dom = tmp_path / "frontend-error.html"
    manifest_path = tmp_path / "frontend-error-manifest.json"
    shot.write_bytes(_png_bytes(width=1440, height=960))
    dom.write_text(
        '<p id="hero-subtitle">数据加载失败: 前端契约校验失败：series.replicas length 11 does not match timeline length 12</p>',
        encoding="utf-8",
    )
    smoke.write_frontend_error_evidence_manifest(
        manifest_path,
        url="http://127.0.0.1:8765/control-center",
        viewport=smoke.SmokeViewport("desktop", 1440, 960),
        screenshot=shot,
        dom_dump=dom,
    )

    smoke.verify_frontend_error_evidence_manifest(manifest_path)


def test_control_center_browser_smoke_can_verify_manifest_without_browser(monkeypatch, tmp_path, capsys):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")
    verified = []

    monkeypatch.setattr(smoke, "sync_playwright", None)
    monkeypatch.setattr(smoke, "find_system_browser", lambda: (_ for _ in ()).throw(AssertionError("browser lookup should not run")))
    monkeypatch.setattr(smoke, "_start_server", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("server should not start")))
    monkeypatch.setattr(smoke, "verify_evidence_manifest", lambda path: verified.append(path))

    exit_code = smoke.main(["--verify-manifest", str(manifest_path)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert verified == [manifest_path]
    assert f"manifest replay passed: {manifest_path}" in output


def test_control_center_browser_smoke_can_verify_error_manifest_without_browser(monkeypatch, tmp_path, capsys):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    manifest_path = tmp_path / "error-manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")
    verified = []

    monkeypatch.setattr(smoke, "find_system_browser", lambda: (_ for _ in ()).throw(AssertionError("browser lookup should not run")))
    monkeypatch.setattr(smoke, "_start_server", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("server should not start")))
    monkeypatch.setattr(smoke, "verify_error_evidence_manifest", lambda path: verified.append(path))

    exit_code = smoke.main(["--verify-error-manifest", str(manifest_path)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert verified == [manifest_path]
    assert f"error manifest replay passed: {manifest_path}" in output


def test_control_center_browser_smoke_can_verify_all_manifests_without_browser(monkeypatch, tmp_path, capsys):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    normal_manifest = tmp_path / "normal-manifest.json"
    error_manifest = tmp_path / "error-manifest.json"
    frontend_error_manifest = tmp_path / "frontend-error-manifest.json"
    normal_manifest.write_text("{}", encoding="utf-8")
    error_manifest.write_text("{}", encoding="utf-8")
    frontend_error_manifest.write_text("{}", encoding="utf-8")
    verified = []

    monkeypatch.setattr(smoke, "find_system_browser", lambda: (_ for _ in ()).throw(AssertionError("browser lookup should not run")))
    monkeypatch.setattr(smoke, "_start_server", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("server should not start")))
    monkeypatch.setattr(smoke, "verify_evidence_manifest", lambda path: verified.append(("normal", path)))
    monkeypatch.setattr(smoke, "verify_error_evidence_manifest", lambda path: verified.append(("error", path)))
    monkeypatch.setattr(smoke, "verify_frontend_error_evidence_manifest", lambda path: verified.append(("frontend-error", path)))

    exit_code = smoke.main([
        "--verify-all-manifests",
        "--manifest",
        str(normal_manifest),
        "--error-manifest",
        str(error_manifest),
        "--frontend-error-manifest",
        str(frontend_error_manifest),
    ])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert verified == [
        ("normal", normal_manifest),
        ("error", error_manifest),
        ("frontend-error", frontend_error_manifest),
    ]
    assert f"all manifests replay passed: {normal_manifest} + {error_manifest} + {frontend_error_manifest}" in output


def test_build_evidence_report_summarizes_normal_and_error_manifests(tmp_path):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    normal = tmp_path / "normal.json"
    error = tmp_path / "error.json"
    frontend_error = tmp_path / "frontend-error.json"
    normal.write_text(json.dumps({
        "contract": {"version": "control-center.v1", "api_path": "/api/control-center"},
        "api_snapshot": {"path": "api.json"},
        "summary": {"ticks": 12, "timeline_rows": 12, "events_total": 23},
        "frontend_response": {"api_url": "/api/control-center"},
        "health_response": {"payload": {"status": "ok"}},
        "viewports": [
            {"name": "desktop", "screenshot": {"png": {"width": 1440, "height": 960, "blank": False}}, "dom_dump": {"bytes": 100}},
            {"name": "mobile", "screenshot": {"png": {"width": 390, "height": 844, "blank": False}}, "dom_dump": {"bytes": 90}},
        ],
    }), encoding="utf-8")
    (tmp_path / "api.json").write_text(json.dumps({
        "frontend_contract": {
            "top_level_required_fields": ["summary", "timeline", "series"],
            "object_required_fields": {"summary": ["ticks", "current_replicas"], "series": ["replicas"]},
            "array_item_required_fields": {"events.kinds": ["kind", "count"], "timeline.event_details": ["tick"]},
            "timeline_required_fields": ["tick", "observed_rps", "alloc_shares", "event_details"],
        }
    }), encoding="utf-8")
    error.write_text(json.dumps({
        "mode": "contract-error",
        "viewport": {"name": "desktop", "width": 1440, "height": 960},
        "screenshot": {"png": {"width": 1440, "height": 960, "blank": False}},
        "dom_dump": {"bytes": 80},
    }), encoding="utf-8")
    frontend_error.write_text(json.dumps({
        "mode": "frontend-contract-error",
        "viewport": {"name": "desktop", "width": 1440, "height": 960},
        "screenshot": {"png": {"width": 1440, "height": 960, "blank": False}},
        "dom_dump": {"bytes": 70},
    }), encoding="utf-8")

    report = smoke.build_evidence_report(normal, error, frontend_error)

    assert report == {
        "contract": "control-center.v1 @ /api/control-center",
        "manifest_paths": {
            "normal": str(normal),
            "backend_error": str(error),
            "frontend_error": str(frontend_error),
        },
        "manifest_records": {
            "normal": smoke._artifact_record(normal, base_dir=normal.parent),
            "backend_error": smoke._artifact_record(error, base_dir=normal.parent),
            "frontend_error": smoke._artifact_record(frontend_error, base_dir=normal.parent),
        },
        "frontend_api_url": "/api/control-center",
        "health_status": "ok",
        "timeline": "12 rows / 12 ticks / 23 events",
        "normal_viewports": ["desktop:1440x960:dom100", "mobile:390x844:dom90"],
        "error_viewport": "desktop:1440x960:dom80",
        "frontend_error_viewport": "desktop:1440x960:dom70",
        "contract_depth": {
            "top_level": 3,
            "object_groups": 2,
            "object_fields": 3,
            "array_item_groups": 2,
            "array_item_fields": 3,
            "timeline_fields": 4,
        },
    }


def test_control_center_browser_smoke_reports_all_manifest_summary(monkeypatch, tmp_path, capsys):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    normal_manifest = tmp_path / "normal-manifest.json"
    error_manifest = tmp_path / "error-manifest.json"
    report_path = tmp_path / "report.json"
    normal_manifest.write_text("{}", encoding="utf-8")
    error_manifest.write_text("{}", encoding="utf-8")
    report = {
        "contract": "control-center.v1 @ /api/control-center",
        "manifest_paths": {
            "normal": "analysis/artifacts/control-center-browser-smoke-manifest.json",
            "backend_error": "analysis/artifacts/control-center-browser-error-smoke-manifest.json",
            "frontend_error": "analysis/artifacts/control-center-browser-frontend-error-smoke-manifest.json",
        },
        "manifest_records": {
            "normal": {"path": "analysis/artifacts/control-center-browser-smoke-manifest.json", "bytes": 1000, "sha256": "0" * 64},
            "backend_error": {"path": "analysis/artifacts/control-center-browser-error-smoke-manifest.json", "bytes": 500, "sha256": "1" * 64},
            "frontend_error": {"path": "analysis/artifacts/control-center-browser-frontend-error-smoke-manifest.json", "bytes": 600, "sha256": "2" * 64},
        },
        "frontend_api_url": "/api/control-center",
        "health_status": "ok",
        "timeline": "12 rows / 12 ticks / 23 events",
        "normal_viewports": ["desktop:1440x960:dom100"],
        "error_viewport": "desktop:1440x960:dom80",
        "frontend_error_viewport": "desktop:1440x960:dom70",
        "contract_depth": {"top_level": 3, "object_groups": 2, "object_fields": 3, "array_item_groups": 2, "array_item_fields": 3, "timeline_fields": 4},
    }

    monkeypatch.setattr(smoke, "verify_evidence_manifest", lambda path: None)
    monkeypatch.setattr(smoke, "verify_error_evidence_manifest", lambda path: None)
    monkeypatch.setattr(smoke, "verify_frontend_error_evidence_manifest", lambda path: None)
    monkeypatch.setattr(smoke, "build_evidence_report", lambda normal, error, frontend_error: report)
    monkeypatch.setattr(smoke, "find_system_browser", lambda: (_ for _ in ()).throw(AssertionError("browser lookup should not run")))

    exit_code = smoke.main([
        "--report-manifests",
        "--manifest",
        str(normal_manifest),
        "--error-manifest",
        str(error_manifest),
        "--frontend-error-manifest",
        str(tmp_path / "frontend-error-manifest.json"),
        "--report-json",
        str(report_path),
    ])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "evidence report:" in output
    assert "control-center.v1 @ /api/control-center" in output
    assert "desktop:1440x960:dom100" in output
    assert "error=desktop:1440x960:dom80" in output
    assert "frontend_error=desktop:1440x960:dom70" in output
    assert "manifest_paths=normal:analysis/artifacts/control-center-browser-smoke-manifest.json backend_error:analysis/artifacts/control-center-browser-error-smoke-manifest.json frontend_error:analysis/artifacts/control-center-browser-frontend-error-smoke-manifest.json" in output
    assert "manifest_records=normal:1000:000000000000 backend_error:500:111111111111 frontend_error:600:222222222222" in output
    assert "manifest_replay=normal+backend_error+frontend_error" in output
    assert "contract_depth=top_level:3 object_groups:2 object_fields:3 array_item_groups:2 array_item_fields:3 timeline_fields:4" in output


def test_control_center_browser_smoke_writes_json_report_after_replay(monkeypatch, tmp_path, capsys):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    normal_manifest = tmp_path / "normal-manifest.json"
    error_manifest = tmp_path / "error-manifest.json"
    frontend_error_manifest = tmp_path / "frontend-error-manifest.json"
    report_path = tmp_path / "report.json"
    normal_manifest.write_text("{}", encoding="utf-8")
    error_manifest.write_text("{}", encoding="utf-8")
    frontend_error_manifest.write_text("{}", encoding="utf-8")
    report = {
        "contract": "control-center.v1 @ /api/control-center",
        "manifest_paths": {
            "normal": "analysis/artifacts/control-center-browser-smoke-manifest.json",
            "backend_error": "analysis/artifacts/control-center-browser-error-smoke-manifest.json",
            "frontend_error": "analysis/artifacts/control-center-browser-frontend-error-smoke-manifest.json",
        },
        "manifest_records": {
            "normal": {"path": "analysis/artifacts/control-center-browser-smoke-manifest.json", "bytes": 1000, "sha256": "0" * 64},
            "backend_error": {"path": "analysis/artifacts/control-center-browser-error-smoke-manifest.json", "bytes": 500, "sha256": "1" * 64},
            "frontend_error": {"path": "analysis/artifacts/control-center-browser-frontend-error-smoke-manifest.json", "bytes": 600, "sha256": "2" * 64},
        },
        "frontend_api_url": "/api/control-center",
        "health_status": "ok",
        "timeline": "12 rows / 12 ticks / 23 events",
        "normal_viewports": ["desktop:1440x960:dom100"],
        "error_viewport": "desktop:1440x960:dom80",
        "frontend_error_viewport": "desktop:1440x960:dom70",
        "contract_depth": {"top_level": 3, "object_groups": 2, "object_fields": 3, "array_item_groups": 2, "array_item_fields": 3, "timeline_fields": 4},
    }

    monkeypatch.setattr(smoke, "verify_evidence_manifest", lambda path: None)
    monkeypatch.setattr(smoke, "verify_error_evidence_manifest", lambda path: None)
    monkeypatch.setattr(smoke, "verify_frontend_error_evidence_manifest", lambda path: None)
    monkeypatch.setattr(smoke, "build_evidence_report", lambda normal, error, frontend_error: report)
    monkeypatch.setattr(smoke, "find_system_browser", lambda: (_ for _ in ()).throw(AssertionError("browser lookup should not run")))

    exit_code = smoke.main([
        "--report-manifests",
        "--report-json",
        str(report_path),
        "--manifest",
        str(normal_manifest),
        "--error-manifest",
        str(error_manifest),
        "--frontend-error-manifest",
        str(frontend_error_manifest),
    ])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert json.loads(report_path.read_text(encoding="utf-8")) == report
    assert f"evidence report json: {report_path}" in output


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


def test_control_center_frontend_contains_smoke_interaction_hook():
    html = (Path(__file__).resolve().parents[1] / "docs" / "control-center.html").read_text(
        encoding="utf-8"
    )

    assert "function runSmokeInteractionProbe" in html
    assert "#smoke-interaction" in html
    assert "document.body.dataset.smokeLens" in html
    assert "document.body.dataset.smokeKindLens" in html
    assert "document.body.dataset.smokeBudget" in html
    assert "document.body.dataset.smokeDensity" in html
    assert "document.body.dataset.smokeShareHash" in html
    assert "document.body.dataset.smokeResetFilter" in html
    assert '[data-density-mode="compact"]' in html
    assert '[data-share-action="refresh"]' in html
    assert '[data-budget-focus="allocation"]' in html
    assert '[data-dashboard-action="reset"]' in html
    assert "dispatchEvent(new MouseEvent('click'" in html


def test_control_center_smoke_probe_records_final_selected_tick_after_reset():
    html = (Path(__file__).resolve().parents[1] / "docs" / "control-center.html").read_text(
        encoding="utf-8"
    )

    reset_pos = html.index("document.querySelector('[data-dashboard-action=\"reset\"]')")
    final_selected_pos = html.rindex("document.body.dataset.smokeSelectedTick")
    final_visible_pos = html.rindex("document.body.dataset.smokeVisibleTicks")

    assert reset_pos < final_selected_pos < final_visible_pos


def test_dom_assertion_ignores_error_literals_in_script_source():
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    dom = """
    <p id="hero-subtitle">基于 OpenDesign dashboard 设计系统</p>
    <code id="frontend-contract-version">control-center.v1 · /api/control-center</code>
    <div id="series-chart"><svg></svg></div>
    <article class="timeline-row"></article>
    <div id="tick-event-details"></div>
    <div id="tick-alloc-shares"></div>
    <div id="event-kind-lens-list"><button>全部事件</button></div>
    <div id="safety-budget-list"><button class="budget-item" data-budget-focus="allocation">分配余量</button></div>
    <div id="capacity-budget-list"><button class="capacity-item" data-capacity-focus="slot">槽位压力</button></div>
    <div data-smoke-kind-lens="kind" data-smoke-budget="allocation" data-smoke-lens="stage" data-smoke-filter="events" data-smoke-chart="pool" data-smoke-view="modules" data-smoke-density="compact" data-smoke-share-hash="#share=tick%3D1" data-smoke-reset-filter="all" data-smoke-reset-density="comfortable" data-smoke-density="compact" data-smoke-share-hash="#share=tick%3D1" data-smoke-reset-filter="all" data-smoke-reset-density="comfortable" data-smoke-density="compact" data-smoke-share-hash="#share=tick%3D1" data-smoke-reset-filter="all" data-smoke-reset-density="comfortable" data-smoke-selected-tick="1" data-smoke-visible-ticks="12"></div>
    <script>catch(err){setText("hero-subtitle",`数据加载失败：${err.message}`);}</script>
    """

    smoke._assert_dumped_dom(dom)


def test_dom_assertion_rejects_rendered_error_message():
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    dom = """
    <p id="hero-subtitle">数据加载失败：HTTP 500</p>
    <code id="frontend-contract-version">control-center.v1 · /api/control-center</code>
    <div id="series-chart"><svg></svg></div>
    <article class="timeline-row"></article>
    <div id="tick-event-details"></div>
    <div id="tick-alloc-shares"></div>
    <div id="event-kind-lens-list"><button>全部事件</button></div>
    <div id="safety-budget-list"><button class="budget-item" data-budget-focus="allocation">分配余量</button></div>
    """

    try:
        smoke._assert_dumped_dom(dom)
    except AssertionError as exc:
        assert "rendered frontend load failure" in str(exc)
    else:
        raise AssertionError("rendered load failure was not rejected")


def test_control_center_frontend_parses_error_body_details():
    html = (Path(__file__).resolve().parents[1] / "docs" / "control-center.html").read_text(
        encoding="utf-8"
    )

    assert "async function readApiError" in html
    assert "control_center_contract_violation" in html
    assert "details.join" in html


def test_error_dom_requires_backend_contract_error_details():
    smoke = importlib.import_module("scripts.control_center_browser_smoke")

    try:
        smoke._assert_error_dom('<p id="hero-subtitle">数据加载失败：HTTP 500</p>')
    except AssertionError as exc:
        assert "backend contract violation details" in str(exc)
    else:
        raise AssertionError("contract error details were not required")


def test_error_dom_accepts_backend_contract_error_details():
    smoke = importlib.import_module("scripts.control_center_browser_smoke")

    smoke._assert_error_dom(
        '<p id="hero-subtitle">数据加载失败：HTTP 500 · control_center_contract_violation · timeline[0] missing required frontend field: observed_rps</p>'
    )




def test_dom_assertion_requires_backend_payload_values():
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    payload = {
        "summary": {
            "ticks": 12,
            "degraded_ticks": 4,
            "event_visible_fraction": 0.75,
            "current_replicas": 9,
            "canary_share_pct": 12.34,
            "peak_forecast_rps": 1234.56,
        },
        "frontend_contract": {"version": "control-center.v1", "api_path": "/api/control-center"},
        "timeline": [
            {
                "tick": 0,
                "time_s": 0.0,
                "observed_rps": 111.2,
                "forecast_rps": 222.8,
                "replicas_next": 3,
                "pool_connections": 44,
                "degraded": True,
            },
            {
                "tick": 1,
                "time_s": 5.0,
                "observed_rps": 112.2,
                "forecast_rps": 223.8,
                "replicas_next": 4,
                "pool_connections": 45,
                "degraded": False,
            },
        ],
        "events": {"total": 5, "distinct_kinds": 2},
    }
    dom = """
    <p id="hero-subtitle">loaded</p>
    <code id="frontend-contract-version">control-center.v1 · /api/control-center</code>
    <strong id="bar-ticks">11</strong>
    <strong id="bar-degraded">4</strong>
    <strong id="bar-events">75%</strong>
    <strong id="bar-canary">12.34%</strong>
    <strong id="bar-replicas">9</strong>
    <strong id="metric-peak">1234.56</strong>
    <div id="series-chart"><svg></svg></div>
    <div id="timeline-meta">2 / 2 拍</div>
    <article class="timeline-row"><strong>3 个副本 · 观测 111 RPS</strong><p>预测 223 RPS</p><div class="tick">44<br>连接</div></article>
    <div id="events-meta">2 类事件 · 5 条</div>
    <div id="tick-event-details"></div>
    <div id="tick-alloc-shares"></div>
    <div id="event-kind-lens-list"><button>all</button></div>
    <div id="safety-budget-list"><button class="budget-item" data-budget-focus="allocation">分配余量</button></div>
    <div id="capacity-budget-list"><button class="capacity-item" data-capacity-focus="slot">槽位压力</button></div>
    <div data-smoke-budget="allocation" data-smoke-kind-lens="kind" data-smoke-budget="allocation" data-smoke-lens="stage" data-smoke-filter="events" data-smoke-chart="pool" data-smoke-view="modules" data-smoke-density="compact" data-smoke-share-hash="#share=tick%3D1" data-smoke-reset-filter="all" data-smoke-reset-density="comfortable" data-smoke-density="compact" data-smoke-share-hash="#share=tick%3D1" data-smoke-reset-filter="all" data-smoke-reset-density="comfortable" data-smoke-density="compact" data-smoke-share-hash="#share=tick%3D1" data-smoke-reset-filter="all" data-smoke-reset-density="comfortable" data-smoke-selected-tick="1" data-smoke-visible-ticks="1"></div>
    """

    try:
        smoke._assert_dumped_dom(dom, payload)
    except AssertionError as exc:
        assert "frontend DOM does not match backend payload" in str(exc)
    else:
        raise AssertionError("payload mismatch was not rejected")


def test_dom_assertion_accepts_backend_payload_values():
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    payload = {
        "summary": {
            "ticks": 12,
            "degraded_ticks": 4,
            "event_visible_fraction": 0.75,
            "current_replicas": 9,
            "canary_share_pct": 12.34,
            "peak_forecast_rps": 1234.56,
        },
        "frontend_contract": {"version": "control-center.v1", "api_path": "/api/control-center"},
        "timeline": [
            {
                "tick": 0,
                "time_s": 0.0,
                "observed_rps": 111.2,
                "forecast_rps": 222.8,
                "replicas_next": 3,
                "pool_connections": 44,
                "degraded": True,
            }
        ],
        "events": {"total": 5, "distinct_kinds": 2},
    }
    dom = """
    <p id="hero-subtitle">loaded</p>
    <code id="frontend-contract-version">control-center.v1 · /api/control-center</code>
    <strong id="bar-ticks">12</strong>
    <strong id="bar-degraded">4</strong>
    <strong id="bar-events">75%</strong>
    <strong id="bar-canary">12.34%</strong>
    <strong id="bar-replicas">9</strong>
    <strong id="metric-peak">1234.56</strong>
    <div id="series-chart"><svg></svg></div>
    <div id="timeline-meta">1 / 1 拍</div>
    <article class="timeline-row"><strong>3 个副本 · 观测 111 RPS</strong><p>预测 223 RPS</p><div class="tick">44<br>连接</div></article>
    <div id="events-meta">2 类事件 · 5 条</div>
    <div id="tick-event-details"></div>
    <div id="tick-alloc-shares"></div>
    <div id="event-kind-lens-list"><button>all</button></div>
    <div id="safety-budget-list"><button class="budget-item" data-budget-focus="allocation">分配余量</button></div>
    <div id="capacity-budget-list"><button class="capacity-item" data-capacity-focus="slot">槽位压力</button></div>
    <div data-smoke-budget="allocation" data-smoke-kind-lens="kind" data-smoke-budget="allocation" data-smoke-lens="stage" data-smoke-filter="events" data-smoke-chart="pool" data-smoke-view="modules" data-smoke-density="compact" data-smoke-share-hash="#share=tick%3D1" data-smoke-reset-filter="all" data-smoke-reset-density="comfortable" data-smoke-density="compact" data-smoke-share-hash="#share=tick%3D1" data-smoke-reset-filter="all" data-smoke-reset-density="comfortable" data-smoke-density="compact" data-smoke-share-hash="#share=tick%3D1" data-smoke-reset-filter="all" data-smoke-reset-density="comfortable" data-smoke-selected-tick="1" data-smoke-visible-ticks="1"></div>
    """

    smoke._assert_dumped_dom(dom, payload)


def test_dom_assertion_requires_selected_tick_details_after_smoke_interaction():
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    payload = {
        "summary": {
            "ticks": 2,
            "degraded_ticks": 0,
            "event_visible_fraction": 1.0,
            "current_replicas": 5,
            "canary_share_pct": 8.0,
            "peak_forecast_rps": 800.0,
        },
        "frontend_contract": {"version": "control-center.v1", "api_path": "/api/control-center"},
        "timeline": [
            {
                "tick": 0,
                "time_s": 0.0,
                "observed_rps": 100.0,
                "forecast_rps": 120.0,
                "replicas_next": 3,
                "pool_connections": 10,
                "degraded": False,
                "event_details": [{"kind": "old-kind", "stage": "observe", "detail": "old detail", "safe_action": "old action"}],
                "alloc_shares": [10.0, 20.0],
            },
            {
                "tick": 1,
                "time_s": 5.0,
                "observed_rps": 130.0,
                "forecast_rps": 160.0,
                "replicas_next": 4,
                "pool_connections": 12,
                "degraded": False,
                "event_details": [{"kind": "selected-kind", "stage": "plan", "detail": "selected detail", "safe_action": "selected action"}],
                "alloc_shares": [31.25, 68.75],
            },
        ],
        "events": {"total": 2, "distinct_kinds": 2},
    }
    dom = """
    <p id="hero-subtitle">loaded</p>
    <code id="frontend-contract-version">control-center.v1 · /api/control-center</code>
    <strong id="bar-ticks">2</strong>
    <strong id="bar-degraded">0</strong>
    <strong id="bar-events">100%</strong>
    <strong id="bar-canary">8%</strong>
    <strong id="bar-replicas">5</strong>
    <strong id="metric-peak">800.0</strong>
    <div id="series-chart"><svg></svg></div>
    <div id="timeline-meta">2 / 2 拍</div>
    <article class="timeline-row"><strong>3 个副本 · 观测 100 RPS</strong><p>预测 120 RPS</p><div class="tick">10<br>连接</div></article>
    <div id="events-meta">2 类事件 · 2 条</div>
    <div id="tick-event-details"><strong>old-kind</strong><p>阶段：observe · old detail</p><p>安全动作：old action</p></div>
    <div id="tick-alloc-shares"><p>10.00 RPS</p><p>20.00 RPS</p></div>
    <div id="event-kind-lens-list"><button>all</button></div>
    <div id="safety-budget-list"><button class="budget-item" data-budget-focus="allocation">分配余量</button></div>
    <div id="capacity-budget-list"><button class="capacity-item" data-capacity-focus="slot">槽位压力</button></div>
    <div data-smoke-budget="allocation" data-smoke-kind-lens="kind" data-smoke-budget="allocation" data-smoke-lens="stage" data-smoke-filter="events" data-smoke-chart="pool" data-smoke-view="modules" data-smoke-density="compact" data-smoke-share-hash="#share=tick%3D1" data-smoke-reset-filter="all" data-smoke-reset-density="comfortable" data-smoke-density="compact" data-smoke-share-hash="#share=tick%3D1" data-smoke-reset-filter="all" data-smoke-reset-density="comfortable" data-smoke-density="compact" data-smoke-share-hash="#share=tick%3D1" data-smoke-reset-filter="all" data-smoke-reset-density="comfortable" data-smoke-selected-tick="1" data-smoke-visible-ticks="2"></div>
    """

    try:
        smoke._assert_dumped_dom(dom, payload)
    except AssertionError as exc:
        assert "selected tick" in str(exc)
    else:
        raise AssertionError("selected tick DOM mismatch was not rejected")


def test_dom_assertion_accepts_selected_tick_details_after_smoke_interaction():
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    payload = {
        "summary": {
            "ticks": 2,
            "degraded_ticks": 0,
            "event_visible_fraction": 1.0,
            "current_replicas": 5,
            "canary_share_pct": 8.0,
            "peak_forecast_rps": 800.0,
        },
        "frontend_contract": {"version": "control-center.v1", "api_path": "/api/control-center"},
        "timeline": [
            {
                "tick": 0,
                "time_s": 0.0,
                "observed_rps": 100.0,
                "forecast_rps": 120.0,
                "replicas_next": 3,
                "pool_connections": 10,
                "degraded": False,
                "event_details": [],
                "alloc_shares": [10.0, 20.0],
            },
            {
                "tick": 1,
                "time_s": 5.0,
                "observed_rps": 130.0,
                "forecast_rps": 160.0,
                "replicas_next": 4,
                "pool_connections": 12,
                "degraded": False,
                "event_details": [{"kind": "selected-kind", "stage": "plan", "detail": "selected detail", "safe_action": "selected action"}],
                "alloc_shares": [31.25, 68.75],
            },
        ],
        "events": {"total": 2, "distinct_kinds": 2},
    }
    dom = """
    <p id="hero-subtitle">loaded</p>
    <code id="frontend-contract-version">control-center.v1 · /api/control-center</code>
    <strong id="bar-ticks">2</strong>
    <strong id="bar-degraded">0</strong>
    <strong id="bar-events">100%</strong>
    <strong id="bar-canary">8%</strong>
    <strong id="bar-replicas">5</strong>
    <strong id="metric-peak">800.0</strong>
    <div id="series-chart"><svg></svg></div>
    <div id="timeline-meta">2 / 2 拍</div>
    <article class="timeline-row"><strong>3 个副本 · 观测 100 RPS</strong><p>预测 120 RPS</p><div class="tick">10<br>连接</div></article>
    <div id="events-meta">2 类事件 · 2 条</div>
    <div id="tick-event-details"><strong>selected-kind</strong><p>阶段：plan · selected detail</p><p>安全动作：selected action</p></div>
    <div id="tick-alloc-shares"><p>31.25 RPS</p><p>68.75 RPS</p></div>
    <div id="event-kind-lens-list"><button>all</button></div>
    <div id="safety-budget-list"><button class="budget-item" data-budget-focus="allocation">分配余量</button></div>
    <div id="capacity-budget-list"><button class="capacity-item" data-capacity-focus="slot">槽位压力</button></div>
    <div data-smoke-budget="allocation" data-smoke-kind-lens="kind" data-smoke-budget="allocation" data-smoke-lens="stage" data-smoke-filter="events" data-smoke-chart="pool" data-smoke-view="modules" data-smoke-density="compact" data-smoke-share-hash="#share=tick%3D1" data-smoke-reset-filter="all" data-smoke-reset-density="comfortable" data-smoke-density="compact" data-smoke-share-hash="#share=tick%3D1" data-smoke-reset-filter="all" data-smoke-reset-density="comfortable" data-smoke-density="compact" data-smoke-share-hash="#share=tick%3D1" data-smoke-reset-filter="all" data-smoke-reset-density="comfortable" data-smoke-selected-tick="1" data-smoke-visible-ticks="2"></div>
    """

    smoke._assert_dumped_dom(dom, payload)

def test_dom_assertion_requires_interaction_probe_state():
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    dom = """
    <p id="hero-subtitle">loaded</p>
    <code id="frontend-contract-version">control-center.v1</code>
    <div id="series-chart"><svg></svg></div>
    <article class="timeline-row"></article>
    <div id="tick-event-details"></div>
    <div id="tick-alloc-shares"></div>
    <div id="event-kind-lens-list"><button>all</button></div>
    <div id="safety-budget-list"><button class="budget-item" data-budget-focus="allocation">分配余量</button></div>
    <div id="capacity-budget-list"><button class="capacity-item" data-capacity-focus="slot">槽位压力</button></div>
    """

    try:
        smoke._assert_dumped_dom(dom)
    except AssertionError as exc:
        assert "browser interaction probe did not run" in str(exc)
    else:
        raise AssertionError("missing interaction probe state was not rejected")




def test_dom_assertion_requires_full_interaction_probe_state():
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    dom = """
    <p id="hero-subtitle">loaded</p>
    <code id="frontend-contract-version">control-center.v1</code>
    <div id="series-chart"><svg></svg></div>
    <article class="timeline-row"></article>
    <div id="tick-event-details"></div>
    <div id="tick-alloc-shares"></div>
    <div id="event-kind-lens-list"><button>all</button></div>
    <div id="safety-budget-list"><button class="budget-item" data-budget-focus="allocation">分配余量</button></div>
    <div id="capacity-budget-list"><button class="capacity-item" data-capacity-focus="slot">槽位压力</button></div>
    <div data-smoke-budget="allocation" data-smoke-kind-lens="kind" data-smoke-budget="allocation" data-smoke-lens="stage" data-smoke-filter="events" data-smoke-visible-ticks="12"></div>
    """

    try:
        smoke._assert_dumped_dom(dom)
    except AssertionError as exc:
        assert "browser interaction probe incomplete" in str(exc)
    else:
        raise AssertionError("partial interaction probe state was not rejected")


def test_system_browser_error_smoke_detects_rendered_backend_failure(monkeypatch, tmp_path):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    screenshot = tmp_path / "error.png"

    def fake_run(command, **kwargs):
        screenshot.write_bytes(b"png")
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=(
                '<p id="hero-subtitle">数据加载失败: HTTP 500 | control_center_contract_violation | timeline[0] missing required frontend field: observed_rps</p>'
                '<code id="frontend-contract-version">等待 API</code>'
            ).encode("utf-8"),
            stderr=b"",
        )

    monkeypatch.setattr(smoke.subprocess, "run", fake_run)

    smoke._run_system_browser_error_smoke(
        url="http://127.0.0.1:1/control-center",
        browser_path=Path("C:/Browser/browser.exe"),
        screenshot_path=screenshot,
        dom_dump_path=tmp_path / "error.html",
        viewport=smoke.SmokeViewport("desktop", 1440, 960),
    )

    assert "数据加载失败" in (tmp_path / "error.html").read_text(encoding="utf-8")


def test_system_browser_frontend_contract_smoke_detects_rendered_validator_failure(monkeypatch, tmp_path):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    screenshot = tmp_path / "frontend-error.png"

    def fake_run(command, **kwargs):
        screenshot.write_bytes(b"png")
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=(
                '<p id="hero-subtitle">数据加载失败: 前端契约校验失败：series.replicas length 11 does not match timeline length 12</p>'
                '<code id="frontend-contract-version">等待 API</code>'
            ).encode("utf-8"),
            stderr=b"",
        )

    monkeypatch.setattr(smoke.subprocess, "run", fake_run)

    smoke._run_system_browser_frontend_contract_smoke(
        url="http://127.0.0.1:1/control-center",
        browser_path=Path("C:/Browser/browser.exe"),
        screenshot_path=screenshot,
        dom_dump_path=tmp_path / "frontend-error.html",
        viewport=smoke.SmokeViewport("desktop", 1440, 960),
    )

    assert "前端契约校验失败" in (tmp_path / "frontend-error.html").read_text(encoding="utf-8")




def test_system_browser_error_smoke_uses_absolute_screenshot_path(monkeypatch, tmp_path):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    captured = {}
    monkeypatch.chdir(tmp_path)

    def fake_run(command, **kwargs):
        screenshot_arg = next(item for item in command if item.startswith("--screenshot="))
        screenshot_path = Path(screenshot_arg.split("=", 1)[1])
        captured["screenshot_path"] = screenshot_path
        screenshot_path.write_bytes(b"png")
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout='<p id="hero-subtitle">数据加载失败: HTTP 500 | control_center_contract_violation | timeline[0] missing required frontend field: observed_rps</p>'.encode("utf-8"),
            stderr=b"",
        )

    monkeypatch.setattr(smoke.subprocess, "run", fake_run)

    smoke._run_system_browser_error_smoke(
        url="http://127.0.0.1:1/control-center",
        browser_path=Path("C:/Browser/browser.exe"),
        screenshot_path=Path("error.png"),
        dom_dump_path=Path("error.html"),
        viewport=smoke.SmokeViewport("desktop", 1440, 960),
    )

    assert captured["screenshot_path"].is_absolute()

def test_error_smoke_handler_returns_contract_violation():
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    payload = smoke.build_broken_control_center_payload()
    errors = smoke.validate_control_center_payload(payload)

    assert errors
    assert any("missing required frontend field" in error for error in errors)


def test_browser_smoke_validator_rejects_missing_frontend_top_level_fields():
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    payload = smoke.build_control_center_payload()
    del payload["events"]

    errors = smoke.validate_control_center_payload(payload)

    assert "missing required frontend field: events" in errors


def test_browser_smoke_validator_rejects_missing_nested_frontend_fields():
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    payload = smoke.build_control_center_payload()
    del payload["hero"]["subtitle"]

    errors = smoke.validate_control_center_payload(payload)

    assert "hero missing required frontend field: subtitle" in errors


def test_browser_smoke_validator_rejects_missing_array_item_frontend_fields():
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    payload = smoke.build_control_center_payload()
    del payload["stage_rollup"][0]["count"]

    errors = smoke.validate_control_center_payload(payload)

    assert "stage_rollup[0] missing required frontend field: count" in errors


def test_browser_smoke_validator_rejects_inconsistent_frontend_lengths():
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    payload = smoke.build_control_center_payload()
    payload["series"]["replicas"] = payload["series"]["replicas"][:-1]
    payload["timeline"][0]["alloc_shares"] = []

    errors = smoke.validate_control_center_payload(payload)

    assert f"series.replicas length {len(payload['series']['replicas'])} does not match timeline length {len(payload['timeline'])}" in errors
    assert f"timeline[0].alloc_shares length 0 does not match load_split length {len(payload['load_split'])}" in errors


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
