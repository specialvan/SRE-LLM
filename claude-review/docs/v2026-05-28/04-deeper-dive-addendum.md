# 04 — 继续深挖追加报告（F73–F81）

> 本文件是在用户再次反馈“颗粒度不够，继续深挖”后追加的逐函数/逐断言审计。相比 `00-blocker-summary.md` 的第一轮结论，本轮复跑发现状态更细：`tests/test_control_center_browser_smoke.py` 单独已经通过，但 `scripts.quality_gate_counts` 仍因 saved browser manifest DOM 缺 token 失败。也就是说，问题从“测试 fixture 与断言漂移”进一步收敛为“测试替身已同步，但真实证据制品未刷新，质量门同步器无法自愈”。

## 最新复跑差异

| 命令 | 最新实测 | 解释 |
|---|---|---|
| `python -m pytest tests/test_control_center_browser_smoke.py -q` | `62 passed` | 单测 fixture 已包含新增 smoke token |
| `python -u -m scripts.quality_gate_counts` | fail | replay saved manifest 时 DOM 缺 `capacity-budget-list` / `data-capacity-focus` |

失败栈：

```text
quality_gate_counts.collect_pytest_count
  -> package_smoke.verify_control_center_evidence_report
  -> control_center_browser_smoke.verify_evidence_manifest
  -> _assert_dumped_dom
AssertionError: browser DOM dump missing: ['capacity-budget-list', 'data-capacity-focus']
```

---

## F73 — 单测 fixture 已同步，但真实 browser manifest 未刷新，造成“测试绿 / 证据红”分裂【P1】

**位置**：

- `tests/test_control_center_browser_smoke.py:1226-1229`
- `tests/test_control_center_browser_smoke.py:1257-1259`
- `tests/test_control_center_browser_smoke.py:1385-1388`
- `scripts/control_center_browser_smoke.py:798-819`
- `analysis/artifacts/control-center-browser-smoke-desktop.html`

**逐断言证据**：

单测 fake DOM 已包含：

```text
safety-budget-list data-budget-focus capacity-budget-list data-capacity-focus
```

`_assert_dumped_dom()` 现在要求：

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
    "capacity-budget-list",
    "data-capacity-focus",
]
```

但 saved manifest 指向的真实 DOM dump 缺 `capacity-budget-list` / `data-capacity-focus`，导致 `quality_gate_counts` 失败。

**为什么现有测试没抓住**：

- 单测覆盖的是 mock stdout / inline DOM。
- `tests/test_control_center_browser_smoke.py` 不 replay 当前仓库已保存的 `analysis/artifacts/control-center-browser-smoke-manifest.json`。
- `quality_gate_counts` 才会走 saved manifest replay，但它是脚本运行时失败，不是 pytest suite 中强制 gate。

**最小修复点**：

1. 重新运行：
   ```bash
   python -m scripts.control_center_browser_smoke --report-manifests --report-json analysis/artifacts/control-center-browser-evidence-report.json
   ```
2. 确认 `analysis/artifacts/control-center-browser-smoke-desktop.html` 和 mobile/error DOM 均含新增 capacity budget token。
3. 再运行：
   ```bash
   python -m scripts.package_smoke
   python -u -m scripts.quality_gate_counts
   ```

**验收测试建议**：

新增 pytest：

```python
def test_saved_browser_manifests_replay_against_current_dom_contract():
    smoke.verify_evidence_manifest(ROOT / "analysis/artifacts/control-center-browser-smoke-manifest.json")
```

如果担心 artifacts 不应作为单测输入，则至少在 `tests/test_quality_gate_counts.py` 中 mock 出 stale DOM，要求错误消息给出刷新命令。

---

## F74 — `_assert_dumped_dom()` 断言顺序已修一半，但错误分类仍过粗【P2】

**位置**：

- `scripts/control_center_browser_smoke.py:798-835`
- `tests/test_control_center_browser_smoke.py:1376-1413`

**现状**：

第一轮发现 error DOM 可能先报 missing tokens，掩盖“rendered frontend load failure”。当前代码已把 hero error 检查提前到 required_text 之前：

```python
hero_subtitle = re.search(...)
if hero_subtitle and ("数据加载失败" ...):
    raise AssertionError("browser DOM dump contains rendered frontend load failure")
required_text = [...]
```

**剩余问题**：

`_assert_dumped_dom()` 仍把三类不同失败混在一个函数：

1. 页面加载失败（hero-subtitle error）
2. 静态 DOM 关键区块缺失（required_text）
3. smoke interaction probe 未执行（data-smoke-*）
4. backend payload 与 DOM 内容不一致（payload rendered mismatch）

这些错误都抛 `AssertionError` 字符串，`quality_gate_counts` 只透传最后字符串，没有 artifact path、viewport、manifest mode。

**为什么会误导 reviewer**：

当前失败只显示缺 token，不显示：

- 哪个 manifest：normal/backend/frontend？
- 哪个 viewport：desktop/mobile？
- 哪个 DOM dump path？
- 缺 token 是 stale artifact 还是当前 frontend 没渲染？

**最小修复点**：

- `_assert_dumped_dom(dom, payload, context=...)` 增加 context。
- `verify_evidence_manifest()` 在调用处传：`manifest path + viewport name + dom_dump path`。
- 错误消息改为：
  ```text
  normal manifest desktop DOM analysis/artifacts/... missing current DOM tokens: [...]. Regenerate with python -m scripts.control_center_browser_smoke --report-manifests ...
  ```

---

## F75 — `quality_gate_counts` 先消费 saved browser report，未生产 fresh report，自愈合语义不足【P1】

**位置**：

- `scripts/quality_gate_counts.py:271-299`
- `scripts/quality_gate_counts.py:400-407`
- `scripts/control_center_browser_smoke.py:1015-1025`

**数据流**：

`update_quality_gate_docs(count=None)` 执行：

1. `collect_pytest_count()`
   - 跑 pytest
   - build wheel
   - `package_smoke.verify_control_center_evidence_report(existing_report)`
2. `run_analysis_suite_gate()`
3. `run_evidence_artifact_gates()`
4. `run_demo_smoke_gate()`
5. 写文档

关键问题在 1：它只验证已有 report，不调用 browser smoke 生成新 report。

**为什么这是 P1**：

文档已把 `quality_gate_counts` 描述为 G1 自愈合 gate；但它只对 `analysis.evidence_manifest -> analysis.evidence_report` 顺序自愈，对 browser evidence 没有自愈能力。DOM 改了以后，它不能刷新 browser evidence，只能失败。

**最小修复点**：

二选一：

- 方案 A：`quality_gate_counts` 在 verify report 前运行 browser smoke report 生成命令。
- 方案 B：保持只读，但失败时输出明确 remediation，并把文档改成“quality_gate_counts 消费已生成 browser report，不负责生成”。

**验收测试**：

- mock `package_smoke.verify_control_center_evidence_report` 抛 DOM missing。
- 断言 `quality_gate_counts` 的异常包含 browser smoke 生成命令，而不是裸 `AssertionError`。

---

## F76 — `CURRENT_QUALITY_GATE_COMMANDS` 小于文档 Required Commands，命令漂移检查是子集检查【P1】

**位置**：

- `scripts/quality_gate_counts.py:49-54`
- `scripts/quality_gate_counts.py:207-220`
- `docs/codex-review/QUALITY_GATES.md:10-21`
- `tests/test_quality_gate_counts.py:1247-1279`

**具体矛盾**：

`QUALITY_GATES.md` Required Commands 包含：

```text
python -m scripts.control_center_browser_smoke --report-manifests --report-json analysis/artifacts/control-center-browser-evidence-report.json
python -m scripts.package_smoke
```

但 `CURRENT_QUALITY_GATE_COMMANDS` 不含这两条。`require_quality_gate_commands()` 只检查 `CURRENT_QUALITY_GATE_COMMANDS`，因此不会保护 browser/package smoke 是否从多个入口文档掉出。

**为什么现有测试没抓住**：

`tests/test_quality_gate_counts.py:1247-1279` 只检查 `QUALITY_GATES.md` 这一个文档包含 browser/package/audit 顺序；没有要求 `CURRENT_QUALITY_GATE_COMMANDS` 与 Required Commands block 完全一致。

**修复验收**：

新增 parser：

```python
commands = parse_required_commands(QUALITY_GATES.md)
assert commands == list(CURRENT_QUALITY_GATE_COMMANDS)
```

若要区分 direct/indirect gate，则显式定义 `INDIRECT_QUALITY_GATE_COMMANDS` 并让文档分组对应。

---

## F77 — current-facing 文档数字被替换，但未保证所有 current 数字都被捕获【P2】

**位置**：

- `scripts/quality_gate_counts.py:75-160`
- `wiki/README.md:42-45`
- `tests/test_quality_gate_counts.py:868-1043`

**现象**：

`wiki/README.md` 同一 current baseline 段同时写：

```text
passes with 437 tests
...
当前 297 为 F50–F60/G1 修复后本工作区实测
```

`QUALITY_GATE_TARGETS` 能替换 `437`，但没有扫描漏网 current count。`297` 就留在同一 current 段里。

**为什么现有测试没抓住**：

测试验证“表中 target 可替换”，不验证“所有 current count 都在表中”。

**修复验收**：

新增仓库级 drift test：

- 扫描 current-facing docs 中 `\d+ passed`、`passes with \d+ tests`、`当前 \d+`。
- 如果上下文含 `Current` / `当前` / `verified` / `baseline` 且没有 `历史` / `historical` / `snapshot` 限定，则必须被 `QUALITY_GATE_TARGETS` 覆盖。
- 同一 current baseline 段只允许一个未历史限定的测试数。

---

## F78 — `OPUS_REVIEW_PACKET.md` 同时声称 historical snapshot 与 current verified output【P2】

**位置**：

- `docs/opus-review/OPUS_REVIEW_PACKET.md:11-16`
- `docs/opus-review/OPUS_REVIEW_PACKET.md:58-79`
- `docs/opus-review/OPUS_REVIEW_PACKET.md:115-116`

**矛盾**：

文件前部说 packet 是已被 Opus review 的工程 snapshot，不是 live open-risk ledger；但后文标题/措辞使用：

- `Current Verification Snapshot`
- `Latest verified commands`
- `Observed current outputs`
- `quality gate pytest count: 437`

**影响**：

Reviewer 会把历史包误读为当前可复现质量门记录；尤其当前 `quality_gate_counts` 已失败时，这种 current wording 是错误锚点。

**修复落点**：

改成：

- `Verification Snapshot Submitted To Opus v2.0`
- `Commands used in that packet`
- `Observed outputs at packet submission time`

并链接 live docs / latest rerun log。

---

## F79 — `PR-REQUIREMENTS.md` 仍列 `scripts.build_kb`/HTML 质量门，但同步机制不执行不检查【P2】

**位置**：

- `PR-REQUIREMENTS.md:19-30`
- `PR-REQUIREMENTS.md:75-87`
- `scripts/quality_gate_counts.py:49-54`

**问题**：

PR front matter 和 NFR 表列：

```text
python -m scripts.build_kb
HTML well-formed (html.parser)
```

但 `CURRENT_QUALITY_GATE_COMMANDS` 和 `update_quality_gate_docs()` 不执行它们。

**为什么会误导**：

Reviewer 看到 PR requirements 会以为 build_kb 是每 PR 必跑 gate；脚本同步又给人“当前 gates 已同步”的印象。但该 gate 不在同步机制里。

**修复方式**：

- 如果 build_kb 是 required gate，加入 command set 和执行流程。
- 如果是条件 gate，文档移到 “when docs/assets changed”。

---

## F80 — `quality_gate_counts` 没有只读 check 模式，审计工具与写入工具耦合【P2】

**位置**：

- `scripts/quality_gate_counts.py:400-425`
- `scripts/quality_gate_counts.py:428-435`

**问题**：

脚本成功后直接写多个文档；没有 `--check` / `--dry-run`。reviewer 想只检查 drift 时，要么运行失败卡在外部证据，要么成功后污染工作区 diff。

**影响**：

- CI 难以只读验证 docs drift。
- reviewer 无法安全地区分“当前门禁失败”与“文档待更新”。

**建议**：

- 增加 `--check`：计算 expected replacements，不写文件；有 drift 返回非零。
- 增加 `--update` 或保持默认 update。
- 增加 `--skip-expensive`：只做文档解析/命令一致性。

---

## F81 — WeightedLoadBalancer 对非有限 demand/zone_target/instance bounds 缺少边界校验【P2】

**位置**：

- `sre_control/weighted_balancer.py:51-62`
- `sre_control/weighted_balancer.py:72-82`
- `sre_control/stack.py:333-334`

**问题**：

`WeightedLoadBalancer.__post_init__()` 只校验 instances 非空和 zone_vector 维度，不校验：

- `zone_vector` 是否 finite；
- `rps_min/rps_max` 是否 finite；
- `rps_min <= rps_max`；
- `rps_demand` 是否 finite；
- `zone_target` 是否 finite 且维度匹配。

`allocate()` 中：

```python
A = self._matrix()
b = np.concatenate([[rps_demand], np.asarray(zone_target, dtype=float)])
lb = np.array([i.rps_min for i in self.instances])
ub = np.array([i.rps_max for i in self.instances])
try:
    res = lsq_linear(A, b, bounds=(lb, ub))
except (RuntimeError, ValueError) as exc:
    raise RecoverableControlError(...)
```

虽然 scipy 部分错误会被包装成 `RecoverableControlError`，但 fault localization 太晚：非有限输入会被归因成 bounded LS solver 失败，而不是 adapter boundary input invalid。

**影响链路**：

- 与 F63/F64 同类：非有限值进入更深层 solver 后才暴露。
- `stack.py:333` 从 `safe_action` norm 得到 `rps_demand`，若上游漏 NaN，allocator 只看到 solver failure。
- 事件归因可能落到 `WeightedLoadBalancer`，掩盖原始 fault。

**最小测试断言**：

```python
with pytest.raises(AdapterInputError, match="non-finite rps_demand"):
    balancer.allocate(float("nan"), [0.0])

with pytest.raises(ValueError, match="rps_min <= rps_max"):
    WeightedLoadBalancer([Instance("a", np.array([0.0]), 10.0, 1.0)])
```

**修复落点**：

- 构造期用 `ValueError` 拒绝非法静态配置。
- `allocate()` 入口用 `AdapterInputError` 或 `RecoverableControlError` 明确拒绝非有限 runtime input。
- 事件 safe_action 应保留 fault family：`invalid_allocator_input`，不要笼统 `bounded LS solver failed`。

---

## 追加结论

上一轮 F61“pytest 当前失败”的表述需要细化：当前 `tests/test_control_center_browser_smoke.py` 已能单独通过，但完整质量门仍因 saved manifest replay 失败而 Block。真正阻断点不是 mock fixture，而是：

1. browser evidence artifacts 没有随 DOM contract 刷新；
2. `quality_gate_counts` 不生产 fresh browser report，只消费 saved report；
3. 文档把 `437 passed` 和“当前质量门全绿”写得过强；
4. drift tests 只覆盖已知 replacement target，不覆盖漏网 current claims。

因此当前合并门禁仍应维持 **Block**，直到 `python -u -m scripts.quality_gate_counts` 通过并且 current-facing docs 的门禁语义被收敛。
