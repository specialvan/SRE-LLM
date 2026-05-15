# Codex Triage of Claude Review

> 本文是 Codex 对 `docs/claude-review/` 评审包的二次梳理。
> 目标不是复述 Claude 的结论，而是把“打回点 / 已修事实 / 仍需行动”拆成可执行队列。

## 1. 结论先行

Claude 这次不是 P0 打回。它的明确结论是 **P0 通过，建议合并**，但指出了一条中等一致性问题和若干非阻塞改进。

当前仓库事实：

- 当前分支：`spacex-session`
- triage 基线：`e2658f6 docs: refresh CODEX_HANDOFF and ship V2_Knowledge snapshot` 及其后的本地 follow-up
- 本地分支是否领先 `origin/spacex-session` 以 `git status -sb` 为准，不再在文档里固定写死
- `python -m pytest tests -q`：51 passed
- Claude 主问题 `DEGRADED_GUARD` 已由 `41cdea8` 修复，并已有 contract 测试覆盖

因此，下一轮不应再把 `DEGRADED_GUARD` 当成未修 blocker；真正要接的是“把评审包中的剩余建议工程化”。

## 2. Claude 评审包结构

| 文件 | 实际价值 | 接手时怎么用 |
|---|---|---|
| `README.md` | 评审包导航 | 确认读文件顺序和 reviewer 的两个核心关注点 |
| `REVIEW_OF_CODEX_SESSION.md` | 逐 commit 评审和缺陷清单 | 以第 6 节为 issue source of truth，但要对照当前代码 |
| `DETAILED_ARCHITECTURE.md` | C4 五视图架构 | 维护依赖方向、运行时链路和下一轮演化蓝图 |
| `EVENT_LIFECYCLE.md` | event 生命周期叙事 | 理解事件从 adapter 到 stack trace 的路径 |
| `FAILURE_MODES.md` | 模块级失效模式 | 做 sentinel 测试和生产化保护时的输入 |
| `HANDOFF_CHECKLIST.md` | 接手核查清单 | 有几处 commit 口径已过期，需要按当前 HEAD 修正理解 |

## 3. 打回点逐项 triage

| Claude 发现 | 严重度 | 当前状态 | 证据 | 下一步 |
|---|---|---|---|---|
| guardrail 触发 event 时 stack 没有加 `DEGRADED_GUARD` | 中 | 已修 | `sre_control/stack.py` 在 guardrail 分支 append `DEGRADED_GUARD`；`tests/test_contracts.py` 覆盖 guardrail event upward | 无需重复修；继续守住“event + DEGRADED_* 同步” |
| `run_all.py` 写死 `All 8 studies` | 小 | 已修 | `analysis/run_all.py` 使用 `len(STUDIES)` | 无需动作 |
| `test_event_schema.py` 用 `"Do not"` 文案签名 | 小 | 已修 | `tests/test_event_schema.py` 已改为 `startswith(("Do not", "Avoid"))` | 继续保持 counter-example 语义明确即可 |
| `API_CONTRACTS.md §2.9 CatchController` 容易误导为 SRE adapter | 小 | 代码/主文档已解释，评审包仍把它列为 open | `API_CONTRACTS.md` 已写明它属于 `starship/` 物理层，不直接依赖 `sre_control/events.py` | 清理 handoff/open-list 口径，别让已解决事项继续漂着 |
| `ARCHITECTURE.md` 与 handoff 都提 CatchController wrapper | 小 | 部分成立 | 两处都仍有“未来 wrapper”提醒 | 保留一处即可；建议收敛到 handoff，架构文档只写依赖边界 |
| 缺少 import graph 测试保护 `starship/` 不 import `sre_control/` | 中 | 已修 | 新增 `tests/test_import_graph.py`，同时守住 `sre_control/events.py` 不 import `starship` | 以后改依赖边界时同步更新该测试 |
| 缺少 failure-state before/after 图 | 中 | 已修 | `analysis/s10_failure_trace.py` 输出 event density、co-occurrence 和 JSONL sample；`analysis.run_all` 已扩到 10 studies | 后续可导出全量 JSONL 和 dashboard 查询样例 |
| `SignalFusion` 没有 innovation gating | 中 | 已修 | `SignalFusion.gate_threshold` + `outlier_rejected` event + 单测覆盖 | 后续可做 per-sensor gate 和恢复窗口 |
| `SREControlStack.step()` 没有 adapter 异常转 event 的 try/except | 大 | 已修 | `SREControlStack.step()` 每阶段处理 `RecoverableControlError`，异常转 `adapter_exception` 并继续 tick；contract tests 覆盖 | 后续细化 stage-specific rollback 策略 |

## 4. 评审包自身的漂移

Claude 包是一个快照，不是实时真源。当前读它时要注意三处漂移：

1. `HANDOFF_CHECKLIST.md` 原先要求 `git log --oneline -5` 顶部固定等于 `41cdea8`，但当前代码已经继续前进；本次 triage 已改成检查关键 commit 是否出现在近期日志里。
2. `V2_Knowledge/knowledge-base.html` 原先把 `59389ee` 写成固定最新点，但它本身由 `e2658f6` 引入；本次 triage 已改成“最近日志应包含关键 commit”。
3. `CODEX_HANDOFF.md` 的小项仍把 `API_CONTRACTS.md §2.9 CatchController` 说明列为待做，但当前 `API_CONTRACTS.md` 已经有物理层边界说明。

这些不是代码 bug，但会误导下一轮 agent。建议把“精确 HEAD 必须等于某 commit”的说法改成“最近日志应包含哪些关键 review commit”，避免每次新增文档 commit 后清单过期。

## 5. 架构要点再抽象

### 5.1 依赖方向

稳定边界是：

```text
starship/     -> 只包含物理与数学原语
sre_control/  -> 单向 import starship，并持有 SRE event schema
analysis/     -> 读 starship/sre_control 生成证据
docs/         -> 读代码和证据，不参与 runtime
```

最不能破坏的是：`starship/` 不得 import `sre_control/`。`CatchController` 的残差保留在 `info["alloc_residual"]` 是正确做法，SRE 事件应该由 `WeightedLoadBalancer` 或未来 wrapper 产生。

### 5.2 事件生命周期

一条 event 的路径是：

```text
adapter 检测 degradation
  -> make_event(stage, kind, detail, safe_action)
  -> adapter 返回 events
  -> SREControlStack 汇总到 runtime.events
  -> SREControlStack 同步追加 DEGRADED_* 状态
  -> trace 留给 analysis / dashboard / incident review
```

关键判断规则：只加 event 不加 `DEGRADED_*` 是漏洞；只加 `DEGRADED_*` 不带 event 也是漏洞。

### 5.3 运行链路

闭环顺序仍然是：

```text
observe -> fuse -> predict/plan -> guard -> allocate -> execute
```

其中 `guard` 不能跳过，`allocate` 即使 residual 不为 0 也要返回 bounded best effort。这个设计比“失败就中断”更适合 SRE，因为它保留了故障现场。

## 6. 证据链缺口

当前 before/after 证据仍主要证明“控制效果变好”：

- §1 pos_err 降到近数值精度
- §4 cone violations 从 97.4% 到 0
- §5 velocity RMSE 显著下降
- §8 saturation violation 到 0
- §SRE SLO violation 从 25% 到 10%

但 Claude 新包引入的 event lifecycle 还没有被同等强度证明。`EVENT_LIFECYCLE.md` 描述 brown-out / surge 下的事件密度模式，但 `analysis/s09_sre_stack.py` 当前并没有注入 missing sensor，也没有输出 event density / co-occurrence 图。

所以 `analysis/s10_failure_trace.py` 是下一轮最高性价比：它把“可观测性抽象”也变成 before/after 证据，而不只是文字说明。

## 7. 推荐执行顺序

### A. 低风险文档清理

1. 修正 `HANDOFF_CHECKLIST.md` 的 HEAD 口径，避免固定死 `41cdea8`。
2. 修正 `V2_Knowledge/knowledge-base.html` 的最新 commit 口径。
3. 把 CatchController wrapper 建议收敛到 handoff，架构文档只保留边界。

### B. 小代码护栏

1. `tests/test_import_graph.py` 已新增，固化 `starship/` 不得 import `sre_control/`。
2. `test_event_schema.py` 已放宽 counter-example 文案断言。

### C. 证据增强

1. 新增 `analysis/s10_failure_trace.py`。
2. 输出事件密度图、共现矩阵、JSONL trace 样例。
3. 把 s10 产物接入 `scripts.build_kb` 和知识库。

### D. 生产化候选

1. 给 `SignalFusion` 加 innovation gating。
2. 设计 `stability_violation`，再给 `SREControlStack.step()` 加异常转事件。
3. 如果做 `starship/stability_monitor.py`，必须保持它不依赖 SRE schema；SRE 侧另做 wrapper。

## 8. 接手验收标准

下一轮如果要声称“处理完 Claude 打回”，至少应该满足：

- `python -m pytest tests -q` 继续 51+ passed
- import graph 测试通过
- `DEGRADED_*` 与 `runtime.events` 的同步规则有测试守护
- Claude 包里的过期 commit 口径被消除或明确标注为快照
- event-level 证据产物已落地；后续关注全量导出和 dashboard 查询

## 9. 当前建议

下一步不要再重复做 s10 / gating / stability fallback。最稳的是：

1. 给 `analysis/s10_failure_trace.py` 增加全量 JSONL trace 导出；
2. 在 V2 知识库补一段 dashboard 查询示例；
3. 细化 `SREControlStack.step()` 的 stage-specific rollback 策略；
4. 如果继续动 events，仍然先改 `EVENT_COUNTEREXAMPLES`，再改真实触发路径和测试。
