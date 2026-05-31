from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from analysis.control_center_data import build_control_center_payload
from scripts.control_center_server import (
    API_PATH,
    ControlCenterHandler,
    is_loopback_bind_host,
    require_loopback_bind_host,
    validate_control_center_payload,
    is_allowed_host,
    resolve_control_center_route,
)


def test_build_control_center_payload_is_json_serializable_and_structured():
    payload = build_control_center_payload()

    assert {
        "generated_at",
        "design_system",
        "hero",
        "summary",
        "timeline",
        "adapters",
        "events",
        "series",
        "load_split",
        "stage_rollup",
    } <= payload.keys()
    assert payload["hero"]["title"] == "星舰回收 SRE 客户数据看板"
    assert payload["design_system"]["provider"] == "OpenDesign"
    assert "dashboard" in payload["design_system"]["style"]
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
    assert fusion["label"] == "多源信号融合"

    json.dumps(payload, ensure_ascii=False)


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


def test_build_control_center_payload_contains_algorithm_customer_benefits():
    payload = build_control_center_payload()

    assert len(payload["algorithm_benefits"]) == 8
    first = payload["algorithm_benefits"][0]
    assert {
        "pillar",
        "algorithm",
        "customer_value",
        "module",
        "before_label",
        "before_value",
        "after_label",
        "after_value",
        "improvement",
        "unit",
        "lower_is_better",
    } <= first.keys()
    assert first["pillar"] == "§1"
    assert first["algorithm"] == "无损凸化 PDG"
    assert all(item["module"].endswith(".py") for item in payload["algorithm_benefits"])
    assert any("MPC" in item["algorithm"] for item in payload["algorithm_benefits"])


def test_control_center_ekf_benefit_matches_current_section5_evidence():
    payload = build_control_center_payload()
    ekf = next(
        item
        for item in payload["algorithm_benefits"]
        if item["module"] == "starship/ekf.py"
    )

    assert ekf["before_value"] == pytest.approx(629.4)
    assert ekf["after_value"] == pytest.approx(9.374)
    assert ekf["after_value"] / ekf["before_value"] == pytest.approx(0.0149, rel=1e-2)
    assert "67" in ekf["improvement"]


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
    assert "row.event_details" in html or "r.event_details" in html
    assert "row.alloc_shares" in html or "r.alloc_shares" in html


def test_control_center_frontend_validates_payload_contract_before_rendering():
    html = (Path(__file__).resolve().parents[1] / "docs" / "control-center.html").read_text(
        encoding="utf-8"
    )

    assert "function validatePayloadContract" in html
    assert "payload.frontend_contract.top_level_required_fields" in html
    assert "payload.frontend_contract.object_required_fields" in html
    assert "payload.frontend_contract.array_item_required_fields" in html
    assert "payload.frontend_contract.timeline_required_fields" in html
    assert "topLevelFields.forEach" in html
    assert "Object.entries(objectFields).forEach" in html
    assert "Object.entries(arrayItemFields).forEach" in html
    assert "validateLengthConsistency(payload)" in html
    assert '"forecast_rps"' in html
    assert "series.${name} length" in html
    assert "alloc_shares length" in html
    load_start = html.index("async function load")
    validate_pos = html.index("validatePayloadContract(payload)", load_start)
    share_restore_pos = html.index("applyShareState", validate_pos)
    render_pos = html.index("renderHero()", validate_pos)
    assert validate_pos < share_restore_pos < render_pos
    assert "前端契约校验失败" in html


def test_control_center_frontend_is_opendesign_chinese_interactive_dashboard():
    html = (Path(__file__).resolve().parents[1] / "docs" / "control-center.html").read_text(
        encoding="utf-8"
    )

    required_text = [
        '<html lang="zh-CN">',
        "\u004f\u0070\u0065\u006e\u0044\u0065\u0073\u0069\u0067\u006e \u63a5\u5165",
        "\u5ba2\u6237\u6570\u636e\u770b\u677f",
        "\u7b97\u6cd5\u843d\u5730",
        "\u524d\u540e\u6536\u76ca",
        "\u62a4\u680f\u8ddd\u79bb",
        "\u8fde\u63a5\u538b\u529b",
        "\u51b3\u7b56\u8d26\u672c",
        "\u5b9e\u4f8b\u5256\u9762",
        "\u7a97\u53e3\u6d1e\u5bdf",
        "\u4e8b\u4ef6\u7c7b\u578b\u900f\u955c",
        "\u7126\u70b9\u8f68\u8ff9",
        "\u9009\u62cd\u5bf9\u7167",
        "\u5904\u7f6e\u5efa\u8bae",
        "\u98ce\u9669\u89e3\u91ca",
        "\u56fe\u8868\u72b6\u6001",
        "\u5feb\u6377\u72b6\u6001",
        "\u72b6\u6001\u900f\u955c",
        "\u7ec4\u4ef6\u900f\u955c",
        "\u544a\u8b66\u9608\u503c",
    ]
    for needle in required_text:
        assert needle in html

    required_anchors = [
        "tick-filter",
        "show-pool",
        "context-summary",
        "context-filter",
        "context-selection",
        "context-benefit",
        "context-lens",
        "clear-lens",
        "playback-control",
        "play-toggle",
        "play-speed",
        "tick-scrubber",
        "stage-chain",
        "risk-radar",
        "risk-radar-grid",
        "risk-radar-copy",
        "decision-ledger",
        "decision-ledger-list",
        "alloc-profile",
        "window-insights",
        "window-insights-grid",
        "event-kind-lens",
        "focus-trail",
        "tick-compare",
        "tick-compare-grid",
        "runbook-panel",
        "runbook-list",
        "benefit-risk-bridge",
        "chart-status",
        "shortcut-hints",
        "state-lens-summary",
        "adapter-lens",
        "alert-thresholds",
        "window-range",
        "window-hotspots",
        "compare-baseline",
        "share-state",
        "algorithm-benefits-grid",
        "benefit-focus-panel",
    ]
    for anchor in required_anchors:
        assert f'id="{anchor}"' in html

    required_behaviors = [
        'data-filter-shortcut="degraded"',
        'data-filter-shortcut="events"',
        "data-risk-focus",
        "data-event-jump",
        "data-ledger-focus",
        "data-alloc-slot",
        "data-event-kind",
        "data-trail-action",
        'data-chart="rps"',
        'data-view="benefits"',
        "function applyRiskFocus",
        "renderBenefits",
        "renderInteractive",
        "renderRiskRadar",
        "renderDecisionLedger",
        "renderAllocProfile",
        "renderWindowInsights",
        "renderEventKindLens",
        "renderFocusTrail",
        "renderTickCompare",
        "data-compare-focus",
        "renderRunbook",
        "data-runbook-action",
        "renderBenefitRiskBridge",
        "data-risk-bridge",
        "renderChartStatus",
        "renderShortcutHints",
        "data-shortcut-action",
        "renderStateLensSummary",
        "data-state-summary",
        "renderAdapterLens",
        "data-adapter-lens",
        "renderAlertThresholds",
        "data-threshold-focus",
        "renderWindowRange",
        "data-window-range",
        "renderWindowHotspots",
        "data-hotspot-jump",
        "renderCompareBaseline",
        "data-baseline-action",
        "renderShareState",
        "data-share-action",
        "applyShareState",
        "URLSearchParams",
    ]
    for needle in required_behaviors:
        assert needle in html

    assert "????" not in html
    assert "???? ?" not in html
    assert "鏄" not in html
    assert "锛?{" not in html


def test_control_center_black_gold_style_is_locked_for_handoff():
    root = Path(__file__).resolve().parents[1]
    html = (root / "docs" / "control-center.html").read_text(encoding="utf-8")
    handoff = (root / "docs" / "CONTROL_CENTER_HANDOFF.md").read_text(encoding="utf-8")

    assert "black-gold premium" in handoff
    assert "效果ok，锁定该版本样式" in handoff
    assert "#f3c96b" in html
    assert "#c89b3c" in html
    assert "rgba(255,216,135" in html
    assert "OpenDesign" in html
    for handoff_anchor in [
        "#global-actions",
        "#reset-dashboard",
        "#density-toggle",
        "#operator-receipt",
        "#view-health",
        "#action-queue",
        "#safety-budget",
        "#capacity-budget",
    ]:
        assert handoff_anchor in handoff

    locked_items = [
        "tick-filter",
        "show-pool",
        "context-summary",
        "context-lens",
        "clear-lens",
        "playback-control",
        "tick-scrubber",
        "stage-chain",
        "risk-radar",
        "decision-ledger",
        "alloc-profile",
        "window-insights",
        "event-kind-lens",
        "focus-trail",
        "tick-compare",
        "runbook-panel",
        "benefit-risk-bridge",
        "chart-status",
        "shortcut-hints",
        "state-lens-summary",
        "adapter-lens",
        "alert-thresholds",
        "window-range",
        "window-hotspots",
        "compare-baseline",
        "share-state",
        "global-actions",
        "operator-receipt",
        "view-health",
        "action-queue",
        "safety-budget",
        "capacity-budget",
    ]
    for anchor in locked_items:
        assert f'id="{anchor}"' in html

    for renderer in [
        "renderContextSummary",
        "renderRiskRadar",
        "renderDecisionLedger",
        "renderAllocProfile",
        "renderWindowInsights",
        "renderEventKindLens",
        "renderFocusTrail",
        "renderTickCompare",
        "renderRunbook",
        "renderBenefitRiskBridge",
        "renderChartStatus",
        "renderShortcutHints",
        "renderStateLensSummary",
        "renderAdapterLens",
        "renderAlertThresholds",
        "renderWindowRange",
        "renderWindowHotspots",
        "renderCompareBaseline",
        "renderShareState",
        "renderSafetyBudget",
        "renderCapacityBudget",
    ]:
        assert renderer in html

def test_control_center_frontend_supports_persistent_operator_view_state():
    html = (Path(__file__).resolve().parents[1] / "docs" / "control-center.html").read_text(
        encoding="utf-8"
    )

    required_text = [
        "\u5168\u5c40\u64cd\u4f5c",
        "\u6062\u590d\u9ed8\u8ba4\u89c6\u56fe",
        "\u5bc6\u5ea6",
        "\u8212\u9002",
        "\u7d27\u51d1",
        "\u9009\u62cd\u5907\u6ce8",
    ]
    for needle in required_text:
        assert needle in html

    required_anchors = [
        "global-actions",
        "reset-dashboard",
        "density-toggle",
        "tick-note",
        "tick-note-list",
    ]
    for anchor in required_anchors:
        assert f'id="{anchor}"' in html

    required_behaviors = [
        'data-dashboard-action="reset"',
        'data-density-mode="compact"',
        "function resetDashboardView",
        "function applyDensityMode",
        "function updateShareHash",
        "function renderTickNote",
        "`density=${densityMode}`",
        'params.get("density")',
        "history.replaceState",
        "renderTickNote();",
    ]
    for needle in required_behaviors:
        assert needle in html


def test_control_center_frontend_surfaces_operator_feedback_state():
    html = (Path(__file__).resolve().parents[1] / "docs" / "control-center.html").read_text(
        encoding="utf-8"
    )

    required_text = [
        "操作回执",
        "视图健康",
        "可复现",
        "当前操作",
    ]
    for needle in required_text:
        assert needle in html

    required_anchors = [
        "operator-receipt",
        "operator-receipt-copy",
        "operator-receipt-code",
        "view-health",
        "view-health-list",
    ]
    for anchor in required_anchors:
        assert f'id="{anchor}"' in html

    required_behaviors = [
        "function setOperatorReceipt",
        "function renderOperatorReceipt",
        "function renderViewHealth",
        "operatorReceipt",
        "renderOperatorReceipt();",
        "renderViewHealth();",
    ]
    for needle in required_behaviors:
        assert needle in html



def test_control_center_frontend_surfaces_window_action_queue():
    html = (Path(__file__).resolve().parents[1] / "docs" / "control-center.html").read_text(
        encoding="utf-8"
    )

    required_text = [
        "处置队列",
        "窗口动作",
        "优先级",
    ]
    for needle in required_text:
        assert needle in html

    required_anchors = [
        "action-queue",
        "action-queue-list",
        "action-queue-meta",
    ]
    for anchor in required_anchors:
        assert f'id="{anchor}"' in html

    required_behaviors = [
        "function renderActionQueue",
        "function applyActionQueueFocus",
        "data-queue-action",
        "renderActionQueue();",
        "setOperatorReceipt(`执行处置队列",
    ]
    for needle in required_behaviors:
        assert needle in html




def test_control_center_frontend_surfaces_safety_budget_panel():
    html = (Path(__file__).resolve().parents[1] / "docs" / "control-center.html").read_text(
        encoding="utf-8"
    )

    required_text = [
        "安全预算",
        "当前窗口余量",
        "延迟余量",
        "容量余量",
        "护栏余量",
        "分配余量",
    ]
    for needle in required_text:
        assert needle in html

    required_anchors = [
        "safety-budget",
        "safety-budget-list",
        "safety-budget-meta",
    ]
    for anchor in required_anchors:
        assert f'id="{anchor}"' in html

    required_behaviors = [
        "function renderSafetyBudget",
        "function applySafetyBudgetFocus",
        "data-budget-focus",
        "renderSafetyBudget();",
        "setOperatorReceipt(`安全预算聚焦",
    ]
    for needle in required_behaviors:
        assert needle in html



def test_control_center_frontend_surfaces_capacity_budget_panel():
    html = (Path(__file__).resolve().parents[1] / "docs" / "control-center.html").read_text(
        encoding="utf-8"
    )

    required_text = [
        "容量预算",
        "资源余量",
        "预测 RPS",
        "副本承载",
        "连接池",
        "灰度流量",
        "槽位压力",
    ]
    for needle in required_text:
        assert needle in html

    required_anchors = [
        "capacity-budget",
        "capacity-budget-list",
        "capacity-budget-meta",
    ]
    for anchor in required_anchors:
        assert f'id="{anchor}"' in html

    required_behaviors = [
        "function renderCapacityBudget",
        "function applyCapacityBudgetFocus",
        "data-capacity-focus",
        "renderCapacityBudget();",
        "setOperatorReceipt(`容量预算聚焦",
    ]
    for needle in required_behaviors:
        assert needle in html


def test_control_center_frontend_whitelists_share_state_values_before_rendering():
    html = (Path(__file__).resolve().parents[1] / "docs" / "control-center.html").read_text(
        encoding="utf-8"
    )

    required_guards = [
        "const SHARE_FILTER_MODES",
        "const SHARE_WINDOW_MODES",
        "const SHARE_LENS_MODES",
        "const SHARE_CHARTS",
        "const SHARE_DENSITY_MODES",
        "SHARE_FILTER_MODES.has(filter)",
        "SHARE_WINDOW_MODES.has(windowValue)",
        "SHARE_LENS_MODES.has(mode)",
        "SHARE_CHARTS.has(chart)",
        "SHARE_DENSITY_MODES.has(density)",
        "isAllowedLensValue(mode,lensCandidate)",
    ]
    for needle in required_guards:
        assert needle in html
    assert 'filterMode=params.get("filter")||filterMode' not in html
    assert 'currentChart=params.get("chart")||currentChart' not in html


def test_control_center_frontend_escapes_dynamic_inner_html_labels():
    html = (Path(__file__).resolve().parents[1] / "docs" / "control-center.html").read_text(
        encoding="utf-8"
    )

    assert "chips.map(c=>" in html
    assert "chart-pill" in html
    assert "esc(c)" in html
    assert 'const items=[{action:"all"' in html
    assert "esc(item.label)" in html
    assert "esc(item.action)" in html
    assert 'items.join("")' not in html


def test_control_center_server_allows_only_local_hosts():
    assert is_allowed_host("127.0.0.1:8765", 8765) is True
    assert is_allowed_host("localhost:8765", 8765) is True
    assert is_allowed_host("[::1]:8765", 8765) is True
    assert is_allowed_host("evil.example:8765", 8765) is False
    assert is_allowed_host(None, 8765) is False


def test_control_center_server_rejects_non_loopback_bind_hosts_by_default():
    assert is_loopback_bind_host("127.0.0.1") is True
    assert is_loopback_bind_host("localhost") is True
    assert is_loopback_bind_host("::1") is True
    assert is_loopback_bind_host("0.0.0.0") is False
    assert is_loopback_bind_host("") is False

    require_loopback_bind_host("127.0.0.1")
    require_loopback_bind_host("0.0.0.0", allow_non_loopback=True)
    with pytest.raises(ValueError, match="Refusing to bind"):
        require_loopback_bind_host("0.0.0.0")


def test_control_center_server_exposes_only_fixed_routes():
    assert resolve_control_center_route("/") == "html"
    assert resolve_control_center_route("/control-center") == "html"
    assert resolve_control_center_route("/control-center.html") == "html"
    assert resolve_control_center_route("/api/control-center") == "api"
    assert resolve_control_center_route("/api/control-center/health") == "health"

    assert resolve_control_center_route("/api/control-center?debug=1") is None
    assert resolve_control_center_route("/assets/s01_lossless_convex.png") is None
    assert resolve_control_center_route("/../pyproject.toml") is None


def test_control_center_payload_validator_rejects_missing_frontend_fields():
    payload = build_control_center_payload()
    del payload["timeline"][0]["alloc_shares"]

    errors = validate_control_center_payload(payload)

    assert errors == ["timeline[0] missing required frontend field: alloc_shares"]


def test_control_center_payload_validator_rejects_missing_frontend_top_level_fields():
    payload = build_control_center_payload()
    del payload["summary"]
    del payload["algorithm_benefits"]

    errors = validate_control_center_payload(payload)

    assert "missing required frontend field: summary" in errors
    assert "missing required frontend field: algorithm_benefits" in errors


def test_control_center_payload_validator_rejects_missing_nested_frontend_fields():
    payload = build_control_center_payload()
    del payload["summary"]["current_replicas"]
    del payload["series"]["forecast_rps"]

    errors = validate_control_center_payload(payload)

    assert "summary missing required frontend field: current_replicas" in errors
    assert "series missing required frontend field: forecast_rps" in errors


def test_control_center_payload_validator_rejects_missing_array_item_frontend_fields():
    payload = build_control_center_payload()
    del payload["algorithm_benefits"][0]["module"]
    del payload["adapters"][0]["status"]
    del payload["events"]["kinds"][0]["count"]

    errors = validate_control_center_payload(payload)

    assert "algorithm_benefits[0] missing required frontend field: module" in errors
    assert "adapters[0] missing required frontend field: status" in errors
    assert "events.kinds[0] missing required frontend field: count" in errors


def test_control_center_payload_validator_rejects_inconsistent_frontend_lengths():
    payload = build_control_center_payload()
    payload["summary"]["ticks"] = len(payload["timeline"]) + 1
    payload["series"]["forecast_rps"] = payload["series"]["forecast_rps"][:-1]
    payload["series"]["degraded_mask"] = payload["series"]["degraded_mask"][:-2]
    payload["timeline"][0]["alloc_shares"] = payload["timeline"][0]["alloc_shares"][:-1]

    errors = validate_control_center_payload(payload)

    assert f"summary.ticks {payload['summary']['ticks']} does not match timeline length {len(payload['timeline'])}" in errors
    assert f"series.forecast_rps length {len(payload['series']['forecast_rps'])} does not match timeline length {len(payload['timeline'])}" in errors
    assert f"series.degraded_mask length {len(payload['series']['degraded_mask'])} does not match timeline length {len(payload['timeline'])}" in errors
    assert f"timeline[0].alloc_shares length {len(payload['timeline'][0]['alloc_shares'])} does not match load_split length {len(payload['load_split'])}" in errors


def test_control_center_http_reports_contract_errors_as_json(monkeypatch):
    def broken_payload():
        payload = build_control_center_payload()
        del payload["timeline"][0]["event_details"]
        return payload

    monkeypatch.setattr("scripts.control_center_server.build_control_center_payload", broken_payload)
    server = ThreadingHTTPServer(("127.0.0.1", 0), ControlCenterHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_port

    try:
        connection = HTTPConnection("127.0.0.1", port, timeout=5)
        connection.request("GET", API_PATH, headers={"Host": f"127.0.0.1:{port}"})
        response = connection.getresponse()
        body = json.loads(response.read().decode("utf-8"))
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert response.status == 500
    assert body["error"] == "control_center_contract_violation"
    assert body["details"] == ["timeline[0] missing required frontend field: event_details"]


def test_control_center_http_serves_frontend_and_api_contract_together():
    server = ThreadingHTTPServer(("127.0.0.1", 0), ControlCenterHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_port

    try:
        connection = HTTPConnection("127.0.0.1", port, timeout=5)
        connection.request("GET", "/control-center", headers={"Host": f"127.0.0.1:{port}"})
        html_response = connection.getresponse()
        html_body = html_response.read().decode("utf-8")
        connection.close()

        connection = HTTPConnection("127.0.0.1", port, timeout=5)
        connection.request("GET", API_PATH, headers={"Host": f"127.0.0.1:{port}"})
        api_response = connection.getresponse()
        api_body = api_response.read().decode("utf-8")
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert html_response.status == 200
    assert html_response.getheader("Cache-Control") == "no-store"
    assert html_response.getheader("X-Control-Center-Contract") == "control-center.v1"
    assert html_response.getheader("X-Control-Center-API") == API_PATH
    assert api_response.status == 200
    assert api_response.getheader("X-Control-Center-Contract") == "control-center.v1"
    assert api_response.getheader("X-Control-Center-API") == API_PATH
    assert api_response.getheader("Cache-Control") == "no-store"
    assert 'const API_URL = "/api/control-center";' in html_body

    payload = json.loads(api_body)
    contract = payload["frontend_contract"]
    assert contract["api_path"] == API_PATH
    assert contract["version"] == "control-center.v1"
    assert "summary" in contract["top_level_required_fields"]
    assert "algorithm_benefits" in contract["top_level_required_fields"]
    assert "tick" in contract["timeline_required_fields"]
    assert "event_details" in contract["timeline_required_fields"]
    assert "alloc_shares" in contract["timeline_required_fields"]

    first_tick = payload["timeline"][0]
    assert set(contract["timeline_required_fields"]) <= set(first_tick)
    assert len(first_tick["alloc_shares"]) == len(payload["load_split"])
    assert payload["summary"]["ticks"] == len(payload["timeline"])


def test_control_center_http_health_reports_live_contract_metadata():
    server = ThreadingHTTPServer(("127.0.0.1", 0), ControlCenterHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_port

    try:
        connection = HTTPConnection("127.0.0.1", port, timeout=5)
        connection.request("GET", "/api/control-center/health", headers={"Host": f"127.0.0.1:{port}"})
        response = connection.getresponse()
        body = json.loads(response.read().decode("utf-8"))
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert response.status == 200
    assert response.getheader("Content-Type") == "application/json; charset=utf-8"
    assert response.getheader("Cache-Control") == "no-store"
    assert response.getheader("X-Control-Center-Contract") == "control-center.v1"
    assert response.getheader("X-Control-Center-API") == API_PATH
    assert body == {
        "status": "ok",
        "contract": {"version": "control-center.v1", "api_path": API_PATH},
        "routes": {"frontend": "/control-center", "api": API_PATH},
    }
