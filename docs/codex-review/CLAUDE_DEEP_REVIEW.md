# Claude Deep Review

> 本文是 Codex 在本地对 `spacex` 当前工程包做的 Claude Reviewer 风格深度梳理与评审。它不是外部 Claude 的真实输出，但按“先问题、后总结”的审查口径组织。

## 1. 结论

未发现 P0 阻断。工程当前能跑通，质量门绿色，依赖方向和 event schema 有测试守护。

主要风险集中在四处：§10 failure trace 证据口径、`SREControlStack` 异常兜底边界、`StabilityMonitor` 恢复语义、EKF 数值稳定性。这些不会阻止当前 demo 运行，但会影响 Reviewer 是否相信“事件生命周期已经从叙事变成工程证据”。

## 2. Findings

| Priority | File / Area | Finding | Why it matters | Suggested fix |
|---|---|---|---|---|
| P1 | `analysis/s10_failure_trace.py:126-158` | §10 为触发 `replica_bound_active` 在同一场景里切换了两个独立 `SREControlStack` 实例。两个 stack 各自持有 EKF、autoscaler 和 trace 状态，导致 bound window 前后的控制历史不连续。 | §10 声称“same scenario will be run once”，但双 stack 会让 Reviewer 质疑事件证据是不是来自同一条控制环。 | 使用单一 stack，在 bound window 内临时收紧 `stack.autoscaler.replicas_max`，tick 后恢复；或显式证明两条 stack 的状态同步。 |
| P1 | `analysis/s10_failure_trace.py:171-188` | `degraded_tick_fraction` 是用 `len(events)>0` 计算的，不是用 `entry["runtime"]["degraded"]`。 | 该指标名会被理解成 runtime 降级比例，但实际是 event-visible tick 比例；遇到 sustained stability 这类“有降级状态但无新事件”的 tick 会低估，当前场景又显示 100% 容易误导。 | `_run_scenario()` 同时返回 `runtime_degraded_flags`；把指标拆成 `event_visible_fraction` 和 `runtime_degraded_fraction`。 |
| P1 | `starship/stability_monitor.py:119-134`, `sre_control/stack.py:142-145` | `StabilityMonitor.triggered` 一旦触发就永久 latch，`SREControlStack` 之后每 tick 都追加 `DEGRADED_PLAN`，即使 `dV/dt` 已恢复非正。 | 如果这是人工确认式红线，需要明确文档和 reset 流程；如果是自动控制信号，缺恢复会让系统长期保守、污染 degraded 指标。 | 增加显式 `latch=True/False` 策略、恢复阈值和 `stability_recovered` 或 clear trace；测试触发后恢复的行为。 |
| P1 | `sre_control/stack.py:119-170`, `sre_control/stack.py:199-238` | `except Exception` 把控制域异常、输入异常、编程错误都转成 `stability_violation` 并继续 tick。 | 这满足“不崩 tick”，但可能吞掉应 fail-fast 的 bug；事件 payload 只有字符串 detail，不足以让上游自动分流 recoverable / non-recoverable。 | 引入 typed exceptions 或 `fault_policy`；对 shape/type/programmer error 默认 fail-fast；event 增加结构化 `error_type` / `recoverable` 字段或放入 trace 子对象。 |
| P2 | `starship/ekf.py:91-94` | EKF covariance update 使用 `(I-KH)P`，没有 Joseph form 和对称化。 | 当前小测试能过，但在 gating、病态 `R` 或多传感器串行更新下更容易产生非对称或非 PSD covariance。 | 改成 `P=(I-KH)P(I-KH)^T + K R K^T`，再做 `(P+P.T)/2`；补 PSD 回归测试。 |
| P2 | `sre_control/stack.py:226-238` | allocator 异常 fallback 返回全零 shares，并注释为“upstream LB will route nothing”。 | 在 SRE 语境中“route nothing”通常不是安全动作，可能等价于全量中断。 | fallback 应优先 hold last known good shares，或显式返回 `traffic_halt=True` 并要求调用方 fail closed。 |
| P2 | `docs/knowledge-base.html`, `docs/V2_Knowledge/knowledge-base.html` | 主知识库与 V2 知识库并存，且 V2 语义更新更完整。 | 两个入口长期并存会制造评审漂移：Reviewer 可能读到旧模板却以为是 canonical。 | 选定 canonical 入口，另一个标注为 generated snapshot / archive；在构建脚本中加入口一致性检查。 |

## 3. 质量门复核

本轮实际复跑：

```bash
python -m pytest tests -q
# 51 passed

python -m analysis.run_all
# All 10 studies finished
```

观察：

- 测试覆盖已经能守住 import graph、event schema、runtime degraded/state/event 合同。
- §10 输出仍为 `event_count_total=83`、`distinct_kinds=4`、`degraded_tick_fraction=100`。
- `analysis/artifacts/SUMMARY.txt` 里的计时字段会随机器轻微抖动，不应作为能力证据。

## 4. 架构判断

通过项：

- `starship/` 与 `sre_control/` 的依赖方向设计正确，并已有 AST 级 import graph 测试。
- Runtime event 统一到 `sre_control/events.py`，比散落字符串更可审。
- `docs/claude-review/` 和 `docs/codex-review/` 已经形成双向移交闭环。
- `SREControlStack.step()` 的 trace 结构足够让 Reviewer 复盘单 tick。

保留意见：

- `SREControlStack` 现在更像研究型编排器，不宜被文档写成生产控制面。
- `stability_violation` 同时承载 adapter crash 和 Lyapunov red-line，语义压力偏大。
- before/after 的“收益”要持续写成场景内证据，尤其是 §5 `pos_p95` 变差、§8 residual 没降这类反例需要保留。

## 5. 建议下一批 PR

| Priority | PR | Scope |
|---|---|---|
| P1 | `s10-continuous-trace` | 单 stack 注入故障、拆分 event visibility / runtime degraded、导出全量 JSONL |
| P1 | `stack-fault-policy` | 分离 recoverable control exception 与 programmer error，补 stage-specific fallback |
| P1 | `stability-recovery-contract` | 明确 latch/manual reset 或自动恢复策略，并补恢复测试 |
| P2 | `ekf-joseph-update` | Joseph covariance update、PSD 断言、病态传感器回归 |
| P2 | `knowledge-canonical-entry` | 主知识库与 V2 入口收敛，构建脚本增加漂移检查 |

## 6. 给下一位 Reviewer 的短评

这轮 Codex 的方向是对的：它没有只写漂亮文档，而是把事件、schema、trace、tests 和 analysis 连了起来。真正要继续追的是“证据口径是否严谨”。如果下一轮只能修一个点，先修 `analysis/s10_failure_trace.py`：让它成为一条连续控制环，并把指标名字改到不会误导。

