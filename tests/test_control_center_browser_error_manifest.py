from __future__ import annotations

import importlib
import json
import struct
import zlib


LOAD_FAILED = "".join(map(chr, [25968, 25454, 21152, 36733, 22833, 36133]))
FRONTEND_VALIDATION_FAILED = "".join(
    map(chr, [21069, 31471, 22865, 32422, 26657, 39564, 22833, 36133])
)


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


def test_write_error_evidence_manifest_records_error_artifacts(tmp_path):
    smoke = importlib.import_module("scripts.control_center_browser_smoke")
    shot = tmp_path / "error.png"
    dom = tmp_path / "error.html"
    manifest_path = tmp_path / "error-manifest.json"
    shot.write_bytes(_png_bytes(width=1440, height=960))
    dom.write_text(
        f'<p id="hero-subtitle">{LOAD_FAILED}: HTTP 500 | control_center_contract_violation | timeline[0] missing required frontend field: observed_rps</p>',
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
    dom.write_text(f'<p id="hero-subtitle">{LOAD_FAILED}: HTTP 500</p>', encoding="utf-8")
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
    dom.write_text(f'<p id="hero-subtitle">{LOAD_FAILED}: API shape rejected</p>', encoding="utf-8")
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
        f'<p id="hero-subtitle">{LOAD_FAILED}: {FRONTEND_VALIDATION_FAILED}: series.replicas length 11 does not match timeline length 12</p>',
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
