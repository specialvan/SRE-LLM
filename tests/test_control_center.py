from __future__ import annotations

import json
from pathlib import Path

from analysis.control_center_data import build_control_center_payload
from scripts.control_center_server import is_allowed_host


def test_build_control_center_payload_is_json_serializable_and_structured():
    payload = build_control_center_payload()

    assert {
        "generated_at",
        "hero",
        "summary",
        "timeline",
        "adapters",
        "events",
        "series",
        "load_split",
        "stage_rollup",
    } <= payload.keys()
    assert payload["hero"]["title"] == "Starship SRE Control Center"
    assert payload["summary"]["ticks"] > 0
    assert payload["summary"]["degraded_ticks"] >= 0
    assert len(payload["timeline"]) == payload["summary"]["ticks"]
    assert len(payload["adapters"]) == 8
    assert isinstance(payload["events"]["kinds"], list)
    assert isinstance(payload["events"]["recent"], list)
    assert isinstance(payload["series"]["replicas"], list)
    assert isinstance(payload["load_split"], list)
    assert isinstance(payload["stage_rollup"], list)

    first_tick = payload["timeline"][0]
    assert {
        "tick",
        "time_s",
        "forecast_rps",
        "observed_rps",
        "replicas_next",
        "degraded",
        "states",
        "events",
        "event_details",
        "alloc_shares",
        "pool_connections",
        "guardrail_projection_distance",
    } <= first_tick.keys()

    fusion = next(card for card in payload["adapters"] if card["id"] == "signal-fusion")
    assert {"id", "label", "metric", "detail", "status"} <= fusion.keys()

    json.dumps(payload)


def test_build_control_center_payload_contains_runtime_event_rollups():
    payload = build_control_center_payload()

    assert payload["events"]["total"] >= 0
    assert payload["events"]["distinct_kinds"] >= 0
    assert payload["events"]["distinct_kinds"] == len(payload["events"]["kinds"])
    assert all("kind" in item and "count" in item for item in payload["events"]["kinds"])
    assert all("state" in item and "count" in item for item in payload["stage_rollup"])


def test_build_control_center_payload_contains_visualization_feeds():
    payload = build_control_center_payload()

    assert len(payload["series"]["replicas"]) == payload["summary"]["ticks"]
    assert len(payload["series"]["observed_rps"]) == payload["summary"]["ticks"]
    assert len(payload["series"]["forecast_rps"]) == payload["summary"]["ticks"]
    assert len(payload["series"]["pool_connections"]) == payload["summary"]["ticks"]
    assert len(payload["load_split"]) == 4


def test_control_center_payload_supports_tick_level_frontend_drilldown():
    payload = build_control_center_payload()
    tick = payload["timeline"][0]

    assert all(isinstance(value, float) for value in tick["alloc_shares"])
    assert len(tick["alloc_shares"]) == len(payload["load_split"])
    assert tick["event_details"]
    assert {
        "tick",
        "time_s",
        "stage",
        "kind",
        "detail",
        "safe_action",
    } <= tick["event_details"][0].keys()


def test_control_center_frontend_renders_real_tick_drilldown_contract():
    html = (Path(__file__).resolve().parents[1] / "docs" / "control-center.html").read_text(
        encoding="utf-8"
    )

    assert "id=\"tick-event-details\"" in html
    assert "id=\"tick-alloc-shares\"" in html
    assert "row.event_details" in html
    assert "row.alloc_shares" in html


def test_control_center_server_allows_only_local_hosts():
    assert is_allowed_host("127.0.0.1:8765", 8765) is True
    assert is_allowed_host("localhost:8765", 8765) is True
    assert is_allowed_host("evil.example:8765", 8765) is False
    assert is_allowed_host(None, 8765) is False
