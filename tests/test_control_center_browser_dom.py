from __future__ import annotations

import importlib
import subprocess
from pathlib import Path


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


