from __future__ import annotations

import importlib
import json
import struct
import zlib
from pathlib import Path

import pytest


def _png_bytes(width=8, height=6, color=(20, 40, 60, 255)):
    def chunk(kind, data):
        payload = kind + data
        return struct.pack(">I", len(data)) + payload + struct.pack(
            ">I", zlib.crc32(payload) & 0xFFFFFFFF
        )

    rows = []
    for y in range(height):
        row = bytearray(bytes(color) * width)
        if y == height - 1:
            row[-4:] = bytes(((color[0] + 90) % 256, color[1], color[2], color[3]))
        rows.append(b"\x00" + bytes(row))
    raw_rows = b"".join(rows)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw_rows))
        + chunk(b"IEND", b"")
    )


def _blank_png_bytes(width=8, height=6):
    def chunk(kind, data):
        payload = kind + data
        return struct.pack(">I", len(data)) + payload + struct.pack(
            ">I", zlib.crc32(payload) & 0xFFFFFFFF
        )

    raw_rows = b"".join(
        b"\x00" + bytes((255, 255, 255, 255)) * width for _ in range(height)
    )
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw_rows))
        + chunk(b"IEND", b"")
    )


def _valid_dom_for_payload(payload):
    def fmt(value):
        return f"{float(value):.2f}".rstrip("0").rstrip(".")

    summary = payload["summary"]
    events = payload["events"]
    first = payload["timeline"][0]
    selected = payload["timeline"][1]
    event = selected["event_details"][0]
    alloc_html = "".join(f"<p>{share:.2f} RPS</p>" for share in selected["alloc_shares"])
    dot = chr(183)
    tick_label = chr(25293)
    replica_label = "".join(map(chr, [20010, 21103, 26412]))
    observed_label = "".join(map(chr, [35266, 27979]))
    forecast_label = "".join(map(chr, [39044, 27979]))
    connection_label = "".join(map(chr, [36830, 25509]))
    event_kind_label = "".join(map(chr, [31867, 20107, 20214]))
    row_label = chr(26465)
    stage_label = "".join(map(chr, [38454, 27573, 65306]))
    safe_action_label = "".join(map(chr, [23433, 20840, 21160, 20316, 65306]))
    return f'''
    <p id="hero-subtitle">loaded</p>
    <code id="frontend-contract-version">{payload["frontend_contract"]["version"]} {dot} {payload["frontend_contract"]["api_path"]}</code>
    <strong id="bar-ticks">{summary["ticks"]}</strong>
    <strong id="bar-degraded">{summary["degraded_ticks"]}</strong>
    <strong id="bar-events">{fmt(summary["event_visible_fraction"] * 100)}%</strong>
    <strong id="bar-canary">{fmt(summary["canary_share_pct"])}%</strong>
    <strong id="bar-replicas">{summary["current_replicas"]}</strong>
    <strong id="metric-peak">{summary["peak_forecast_rps"]}</strong>
    <div id="series-chart"><svg></svg></div>
    <div id="timeline-meta">{len(payload["timeline"])} / {len(payload["timeline"])} {tick_label}</div>
    <article class="timeline-row"><strong>{first["replicas_next"]} {replica_label} {dot} {observed_label} {first["observed_rps"]:.0f} RPS</strong><p>{forecast_label} {first["forecast_rps"]:.0f} RPS</p><div class="tick">{first["pool_connections"]}<br>{connection_label}</div></article>
    <div id="events-meta">{events["distinct_kinds"]} {event_kind_label} {dot} {events["total"]} {row_label}</div>
    <div id="tick-event-details"><strong>{event["kind"]}</strong><p>{stage_label}{event["stage"]} {dot} {event["detail"]}</p><p>{safe_action_label}{event["safe_action"]}</p></div>
    <div id="tick-alloc-shares">{alloc_html}</div>
    <div id="event-kind-lens-list"><button data-event-kind="{event["kind"]}">kind</button></div>
    <div id="safety-budget-list"><button class="budget-item" data-budget-focus="allocation">allocation</button></div>
    <div id="capacity-budget-list"><button class="capacity-item" data-capacity-focus="slot">slot</button></div>
    <div data-smoke-budget="allocation" data-smoke-kind-lens="kind" data-smoke-lens="stage" data-smoke-filter="events" data-smoke-chart="pool" data-smoke-view="modules" data-smoke-density="compact" data-smoke-share-hash="#share=tick%3D1" data-smoke-reset-filter="all" data-smoke-reset-density="comfortable" data-smoke-selected-tick="1" data-smoke-visible-ticks="12"></div>
    '''


def test_write_dom_dump_normalizes_line_endings(tmp_path):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    path = tmp_path / "dom.html"

    smoke.write_dom_dump(path, "<p>a</p>\r\n<p>b</p>\r<p>c</p>\n")

    assert path.read_bytes() == b"<p>a</p>\n<p>b</p>\n<p>c</p>\n"


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
