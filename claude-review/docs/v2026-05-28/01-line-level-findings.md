# 01 — 行级 Findings（F61–F72）

## F61 — pytest 当前失败，`437 passed` 声明失效【P1】

**位置**：

- `docs/codex-review/QUALITY_GATES.md:23-28`
- `scripts/control_center_browser_smoke.py:797-810`
- `tests/test_control_center_browser_smoke.py:1233`
- `tests/test_control_center_browser_smoke.py:1387`
- `tests/test_control_center_browser_smoke.py:1403-1405`

**最小复现**：

```bash
python -m pytest tests -q
```

**实际输出摘要**：

```text
FAILED tests/test_control_center_browser_smoke.py::test_system_browser_smoke_decodes_utf8_dom_dump
FAILED tests/test_control_center_browser_smoke.py::test_system_browser_smoke_gives_async_fetch_time
FAILED tests/test_control_center_browser_smoke.py::test_dom_assertion_ignores_error_literals_in_script_source
FAILED tests/test_control_center_browser_smoke.py::test_dom_assertion_rejects_rendered_error_message
AssertionError: browser DOM dump missing: ['safety-budget-list', 'data-budget-focus']
```

**根因**：

`_assert_dumped_dom()` 的 required_text 新增了 `safety-budget-list`、`data-budget-focus`：

```python
required_text = [
    "control-center.v1",
    "timeline-row",
    "series-chart",
    "tick-event-details",
    "tick-alloc-shares",
    "event-kind-lens-list",
    "safety-budget-list",
    "data-budget-focus",
]
```

但测试中 fake DOM fixture 没有同步这两个 token。更严重的是 saved browser manifest DOM dump 也缺少这两个 token，导致 F62。

**影响链路**：

- `QUALITY_GATES.md` 中的 `437 passed` 不是当前可复现事实。
- `scripts.quality_gate_counts` 依赖 package smoke replay browser evidence，也会失败。
- 这不是单个测试脆弱，而是前端 smoke 证据与断言契约漂移。

**修复验收**：

- 更新测试 fixture 或调整断言顺序，使 error-message 专项断言先于 required_text 缺失断言。
- 重新运行 browser smoke 生成 fresh DOM/manifest/report。
- `python -m pytest tests -q` 必须实测全绿后再更新质量门文档。

---

## F62 — `quality_gate_counts` replay browser evidence 失败【P1】

**位置**：

- `scripts/quality_gate_counts.py:294`
- `scripts/package_smoke.py:182`
- `scripts/control_center_browser_smoke.py:429`
- `scripts/control_center_browser_smoke.py:797-810`
- `analysis/artifacts/control-center-browser-smoke-manifest.json:52-67`

**最小复现**：

```bash
python -u -m scripts.quality_gate_counts
```

**实际输出摘要**：

```text
AssertionError: browser DOM dump missing: ['safety-budget-list', 'data-budget-focus']
```

调用链：

```text
quality_gate_counts.collect_pytest_count
  -> package_smoke.verify_control_center_evidence_report
  -> control_center_browser_smoke.verify_evidence_manifest
  -> _assert_dumped_dom
```

**根因**：

当前 saved manifest 指向的 normal DOM dump 是旧证据：

```json
"dom_dump": {
  "path": "D:\\workspace\\SRE-LLM\\spacex\\analysis\\artifacts\\control-center-browser-smoke-desktop.html",
  "bytes": 138375,
  "sha256": "873b64e9..."
}
```

但 `_assert_dumped_dom()` 的契约已经要求新版 safety budget UI token。质量门没有先实时重跑 browser smoke，而是 replay 旧 manifest，导致 stale artifact 被当作 current evidence。

**影响链路**：

- `quality_gate_counts` 作为“自愈合 gate”不可用。
- docs 中 `G1 已通过 quality_gate_counts 自愈合修复` 的说法需要收敛：它只覆盖 manifest→report 顺序，不能保证 browser evidence 当前性。

**修复验收**：

- `python -m scripts.control_center_browser_smoke --report-manifests --report-json analysis/artifacts/control-center-browser-evidence-report.json` 必须先成功。
- 然后 `python -m scripts.package_smoke` 成功。
- 最后 `python -u -m scripts.quality_gate_counts` 成功。
- 三者顺序写入 `QUALITY_GATES.md` 与 `OPUS_REVIEW_PACKET.md`。

---

## F63 — `SignalFusion.step()` 接受 NaN sensor reading 并污染 EKF state【P1】

**位置**：

- `sre_control/signal_fusion.py:151-156`
- `sre_control/signal_fusion.py:157-198`

**最小复现**：

```python
import json, math
import numpy as np
from sre_control import SignalFusion, Signal

fusion = SignalFusion(
    x0=np.array([1.0]),
    P0=np.eye(1),
    Q=np.zeros((1, 1)),
    x_ref=np.array([1.0]),
    theta=0.0,
)
sig = Signal(name="metrics", h=lambda x: x, H=lambda x: np.eye(1), R=np.eye(1))
trace = fusion.step(1.0, [(sig, np.array([float("nan")]))])
print("state=", fusion.state.tolist())
print("trace_signals=", trace["signals"])
print("trace_events=", trace["events"])
print("json_allows_nan=", json.dumps(trace)[:200])
```

**实测输出**：

```text
state= [nan]
trace_signals= [{'signal': 'metrics', 'used': True, 'residual': nan, 'innovation_mahalanobis': 0.0, 'threshold_used': None, 'consecutive_rejections': 0}]
trace_events= []
json_allows_nan= {"x": [NaN], "P_trace": 0.5, "signals": [{"signal": "metrics", "used": true, "residual": NaN, ...
```

**根因**：

`z = np.asarray(z, dtype=float)` 后没有 `np.isfinite(z).all()`。NaN 进入 EKF update 后被标记为 used，而不是 missing/outlier/rejected。

**影响链路**：

- OBSERVE 边界输入污染 posterior state。
- trace 可写出非标准 JSON `NaN`。
- 后续 guardrail/autoscaler/stability 可能被 NaN 级联污染。
- 当前 F54 只修了 guardrail proposal，未覆盖 sensor reading。

**建议修复**：

- 在 `z = np.asarray(...)` 后立即拒绝非有限值。
- 推荐抛 `AdapterInputError("non-finite sensor reading")`，由 stack 进入 `DEGRADED_OBSERVE` fallback。
- 加测试：非有限 reading 不改变 state/covariance，不写 JSON NaN，runtime state 含 `DEGRADED_OBSERVE` 或产生合法事件。

---

## F64 — `SLOGuardrail.audit()` 修 NaN，但 public `approve()` 仍返回 NaN safe action【P1】

**位置**：

- `sre_control/slo_guardrail.py:62-67`
- `sre_control/slo_guardrail.py:70-74`

**最小复现**：

```python
import numpy as np
from sre_control import SLOGuardrail

guard = SLOGuardrail(
    nominal_direction=np.array([0.0, 0.0, 1.0]),
    magnitude_cap=100.0,
)
print(guard.approve([float("nan"), 0.0, 0.0]))
print(guard.approve([float("inf"), 0.0, 0.0]))
```

**实测输出**：

```text
approve_input= [nan, 0.0, 0.0]
approve_output= [nan, nan, nan]
output_finite= False
audit_raised= AdapterInputError non-finite proposal
approve_input= [inf, 0.0, 0.0]
approve_output= [nan, nan, nan]
output_finite= False
audit_raised= AdapterInputError non-finite proposal
```

**根因**：

`audit()` 在 `slo_guardrail.py:72-74` 有 finite check，但 `approve()` 在 `slo_guardrail.py:62-67` 直接调用 `self._filter.filter(proposal)`。

**影响链路**：

- 同一个 public class 的两个 public API 安全语义不一致。
- 调用方看到方法名 `approve()` 会误以为返回已经过滤的 safe action。
- F54 的 resolved 只能覆盖 stack 使用的 `audit()` 路径，不能覆盖导出 API。

**建议修复**：

- 抽 `_validate_proposal()`，`approve()` 与 `audit()` 共用。
- `approve([nan])` / `approve([inf])` 必须抛 `AdapterInputError` 或 `ValueError`，不得返回 NaN。

---

## F65 — Canary rejected warm-start 声称 shrink，实际 eta 连续 expand【P1】

**位置**：

- `sre_control/canary_scheduler.py:72-99`
- `sre_control/canary_scheduler.py:101-124`

**最小复现**：

```python
from sre_control import CanaryScheduler

s = CanaryScheduler(slo_error_budget=0.01, eta_init=0.1, eta_min=0.005, eta_max=0.3)
for idx in range(1, 4):
    step = s.observe(current_share=0.5, proposed_share=0.6, observed_error_rate=0.03)
    print(idx, s._eta, step.trust_region, step.accepted, step.local_states)
    for event in step.events:
        print(event["safe_action"], event.get("trust_region"))
```

**实测输出**：

```text
step 1 eta= 0.1 trust_region= 0.1 accepted= False states= ['observe', 'initialise', 'freeze']
  event.safe_action= shrink trust region and freeze rollout progress event.trust_region= 0.1
step 2 eta= 0.15000000000000002 trust_region= 0.15000000000000002 accepted= False states= ['observe', 'expand', 'freeze', 'refit_rejected']
  event.safe_action= shrink trust region and freeze rollout progress event.trust_region= 0.15000000000000002
step 3 eta= 0.22500000000000003 trust_region= 0.22500000000000003 accepted= False states= ['observe', 'expand', 'freeze', 'refit_rejected']
  event.safe_action= shrink trust region and freeze rollout progress event.trust_region= 0.22500000000000003
```

**根因**：

- warm-start 初始化分支 `sre_control/canary_scheduler.py:72-99` 在 `accepted=False` 时只 append `freeze`，没有 shrink `_eta`。
- 下一轮 `predicted_gain` 与 `actual_gain` 同号同值时 `rho=1.0`，进入 `rho > rho_grow` 的 expand 路径，再 append `freeze`。
- event 的 `safe_action="shrink trust region and freeze rollout progress"` 与实际状态矛盾。

**影响链路**：

- 操作员看到 rollout_rejected，以为 trust region 缩小。
- 实际 `_eta` 从 0.1 到 0.15 到 0.225，拒绝越多试探步越大。
- F52 主问题虽修，但 rejected warm-start 产生新的安全语义错误。

**建议修复**：

- `accepted=False` 优先 shrink，不允许同轮 expand。
- warm-start 分支内也复用 rejected shrink 逻辑。
- 事件里的 `trust_region` 必须记录 shrink 后值。
- 测试连续 rejected observation 不得 expand。

---

## F66 — evidence JSON/JSONL writer 未 `allow_nan=False`【P1】

**位置**：

- `analysis/evidence_manifest.py:35-45`
- `scripts/control_center_browser_smoke.py:291`
- `scripts/control_center_browser_smoke.py:314`
- `scripts/control_center_browser_smoke.py:338`
- `scripts/control_center_browser_smoke.py:1018`
- `scripts/control_center_integration_audit.py:193`

**问题**：

Python `json.dumps()` 默认 `allow_nan=True`，会把 NaN/Infinity 写成非标准 JSON。当前 evidence writer 没有关闭该默认行为。

`analysis/evidence_manifest.py:35-45`：

```python
def _write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )

def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True, default=_json_default) + "\n")
```

**复现关联**：

F63 已实测 `json.dumps(trace)` 写出：

```text
{"x": [NaN], ... "residual": NaN, ...}
```

**影响链路**：

- “machine-readable evidence / JSON parseability” 不等于 strict JSON。
- Python `json.loads()` 默认也接受 NaN，shape/range 检查如果只做 `<` / `>` 会被 NaN 绕过。
- reviewer 使用 jq、Go、Rust、browser JSON parser 时会失败。

**建议修复**：

- 所有 evidence writer 使用 `allow_nan=False`。
- reader/validator 递归检查 `math.isfinite()`。
- 测试注入 NaN/Infinity，要求明确失败而不是写出 artifact。

---

## F67 — control-center share hash 未白名单 + innerHTML 未统一 escape【P1】

**位置**：

- `docs/control-center.html:104`
- `docs/control-center.html:119`
- `docs/control-center.html:126`

**问题**：

`applyShareState(raw)` 从 URL hash 恢复 `filterMode`、`windowMode`、`lensMode`、`lensValue`、`currentChart`，但没有白名单校验：

```javascript
filterMode=params.get("filter")||filterMode;
windowMode=params.get("window")||windowMode;
...
lensMode=mode||"none";
lensValue=rest.join(":")==="none"?"":rest.join(":");
currentChart=params.get("chart")||currentChart;
```

随后 `renderChartStatus()`、`renderFocusTrail()` 把这些值拼进 `innerHTML`，其中 `renderFocusTrail()` 未 escape：

```javascript
const lensLabel=lensMode==="none"?"无透镜":`${lensMode}: ${lensValue}`;
const items=[`<button ...>透镜：${lensLabel}</button>`, ...];
document.getElementById("focus-trail-list").innerHTML=items.join("");
```

**影响链路**：

- 攻击者可构造 `#share=` URL，把恶意 lens/filter/chart 注入 DOM。
- 虽是本地 HTML / reviewer dashboard，但工程包可能被打开、分享或作为 docs 静态页发布。

**建议修复**：

- `filterMode` only `all|degraded|events`。
- `currentChart` only `rps|replicas|pool`。
- `density` only `comfortable|compact`。
- `lensMode` only `none|stage|state|kind`。
- `windowMode` only `all|6|12|24` 或正整数范围。
- 所有动态 HTML 文本 `esc()`，或改用 DOM API + `textContent`。
- 增加恶意 hash regression：DOM 不出现 `<img`、`onerror`、`script` 注入。

---

## F68 — browser smoke source manifest 写绝对路径，不可移植【P2】

**位置**：

- `scripts/control_center_browser_smoke.py:140-147`
- `analysis/artifacts/control-center-browser-smoke-manifest.json:9-12`
- `analysis/artifacts/control-center-browser-smoke-manifest.json:52-67`

**证据**：

`_artifact_record()`：

```python
path = path.resolve()
return {"path": str(path), ...}
```

当前 manifest：

```json
"api_snapshot": {
  "path": "D:\\workspace\\SRE-LLM\\spacex\\analysis\\artifacts\\control-center-browser-smoke-api.json"
},
"dom_dump": {
  "path": "D:\\workspace\\SRE-LLM\\spacex\\analysis\\artifacts\\control-center-browser-smoke-desktop.html"
}
```

**影响链路**：

- 换 checkout 路径、CI artifact 解包路径、其他 reviewer 机器后 replay 读取旧绝对路径。
- 与 `analysis.evidence_manifest` 的 repo-relative 设计不一致。

**建议修复**：

- browser manifest path 改 repo-relative。
- verifier 接收 `repo_root` 并做 containment 校验。
- 旧绝对路径 manifest 在质量门中应 fail 或标记 nonportable。

---

## F69 — `run_all(artifacts_dir=...)` 只写 SUMMARY，不转发 artifacts_dir 给 studies【P2】

**位置**：

- `analysis/run_all.py:31-44`
- `analysis/run_all.py:71-74`

**最小复现**：

```python
import tempfile
from pathlib import Path
from analysis import run_all

out = Path(tempfile.mkdtemp())
run_all.main(studies=["analysis.s10_failure_trace"], artifacts_dir=out)
print((out / "SUMMARY.txt").exists())
print((out / "s10_trace_full.jsonl").exists())
print(Path("analysis/artifacts/s10_trace_full.jsonl").exists())
```

**实测输出**：

```text
custom_summary_exists= True
custom_trace_exists= False
default_trace_exists= True
custom_dir_files= ['SUMMARY.txt']
```

**根因**：

`run_all.main()` 接收 `artifacts_dir`，但调用 study 时固定 `mod.main()`，没有检测/传入 `artifacts_dir`。

**影响链路**：

- 调用者以为隔离目录中 SUMMARY 与 artifacts 是同一轮 run。
- 实际 artifacts 仍在默认 `analysis/artifacts`，可能新旧混合。

**建议修复**：

- 统一 study main 签名或 inspect 支持 `artifacts_dir` 后传入。
- SUMMARY 记录每个 study 实际 artifact 目录。
- 测试隔离目录下产物完整性。

---

## F70 — 质量门命令集合未纳入 browser report / package smoke【P2】

**位置**：

- `scripts/quality_gate_counts.py:49-54`
- `docs/codex-review/QUALITY_GATES.md:15-16`

**问题**：

`QUALITY_GATES.md` Required Commands 包含：

```text
python -m scripts.control_center_browser_smoke --report-manifests --report-json analysis/artifacts/control-center-browser-evidence-report.json
python -m scripts.package_smoke
```

但 `CURRENT_QUALITY_GATE_COMMANDS` 只展开 analysis suite、evidence artifact modules、demo modules，不含这两条一等命令。

**影响链路**：

- 文档 drift 校验不会发现 OPUS packet 缺少 browser/package smoke。
- `quality_gate_counts` 的“当前命令集合”小于 docs 的 Required Commands。

**建议修复**：

- 把 browser report 生成和 package smoke 加入 `CURRENT_QUALITY_GATE_COMMANDS`。
- 明确执行顺序：browser smoke -> package smoke -> integration audit -> quality_gate_counts。

---

## F71 — control-center server 允许调用方绑定非 loopback【P2】

**位置**：

- `scripts/control_center_server.py:231-232`
- `scripts/control_center_browser_smoke.py:76`
- `scripts/control_center_browser_smoke.py:627-628`
- `docs/codex-review/OPEN_RISKS.md:27`

**问题**：

默认 host 是 `127.0.0.1`，但 server 与 smoke CLI 仍允许传入其他 host。Host header 校验不是网络绑定边界；若绑定到 `0.0.0.0`，外部客户端可手动构造 Host 头访问。

**建议修复**：

- 默认强制 loopback：`127.0.0.1`、`localhost`、`::1`。
- 非 loopback 必须显式危险开关，如 `--allow-non-loopback`。
- OPEN_RISKS 不应笼统声明 localhost exposure policy fully resolved。

---

## F72 — package/integration audit 对 saved replay 与 current proof 表述过强【P2】

**位置**：

- `scripts/control_center_integration_audit.py:98-121`
- `scripts/control_center_integration_audit.py:147-156`
- `scripts/package_smoke.py:147-190`
- `docs/codex-review/QUALITY_GATES.md:41-48`

**问题**：

当前 integration audit 只证明 normal API snapshot 与当前 backend payload hash 一致；backend error / frontend error evidence 主要是 saved manifest replay。package smoke 验证的是 report 固定摘要与 manifest/hash 自洽，不等同于实时 browser 重跑。

**影响链路**：

- 文档说 “frontend/backend integration proof” 容易过度解读为三类 browser paths 都由当前代码实时生成。
- saved replay 适合证明 artifact integrity，不适合单独证明 current behavior。

**建议修复**：

- audit artifact 增加 freshness 字段，区分 `current_api_snapshot` 与 `saved_manifest_replay_only`。
- 文档明确 normal/current、error/replay 的边界。
- 正式 gate 要实时重跑三类 browser smoke。
