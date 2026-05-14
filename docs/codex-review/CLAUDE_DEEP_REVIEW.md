# Claude Deep Review

> 本文是 Codex 在本地对 `spacex` 当前工程包做的 Claude Reviewer 风格深度梳理与评审。它不是外部 Claude 的真实输出，但按“先问题、后总结”的审查口径组织。

## 1. 结论

未发现 P0 阻断。工程当前能跑通，质量门绿色，依赖方向和 event schema 有测试守护。

和上一版相比，PR-A 与 PR-B 的核心问题已经在当前工作区收敛：§10 使用单一连续 stack history，recoverable control-domain failure 也已从 `stability_violation` 中拆到 `adapter_exception`。当前更值得追的，是剩余 P1/P2 风险是否会削弱 reviewer 对证据边界的信任。

## 2. Findings

| Priority | File / Area | Finding | Why it matters | Suggested fix |
|---|---|---|---|---|
| P1 | `sre_control/signal_fusion.py:55-124` | `SignalFusion.gate_threshold` 仍是全局阈值；trace 里也没有记录 sensor-specific threshold。 | 不同维度、噪声和容错需求的 signal 被同一阈值约束，Reviewer 很难相信这个 gate 可以直接迁移到真实多源 SRE 场景。 | 实现 per-sensor gate policy，并把 `threshold_used` 写入 trace。 |
| P1 | `sre_control/stack.py:248-259` | allocator recoverable fallback 仍返回全零 shares。 | `adapter_exception` 已把错误分类理顺，但 “recoverable → 全量停流” 在 SRE 语义上仍过于激进，可能把局部退化放大成全局 outage。 | 改成 hold-last-known-good shares，或显式返回 `traffic_halt=True` 让上游 fail closed。 |
| P2 | `analysis/s10_failure_trace.py:226-244` | §10 的 `replica_bound_active` 只覆盖了 60% 的注入窗口。 | 单 stack 和背景事件控制已经成立，但如果 reviewer 期望“每个窗口都强触发预期 event”，这部分证据还不算满。 | 视评审要求决定是否收紧 `replicas_max`、延长窗口或将 0.6 覆盖写入验收阈值。 |
| P2 | `starship/ekf.py:91-94` | EKF covariance update 使用 `(I-KH)P`，没有 Joseph form 和对称化。 | 当前小测试能过，但在 gating、病态 `R` 或多传感器串行更新下更容易产生非对称或非 PSD covariance。 | 改成 `P=(I-KH)P(I-KH)^T + K R K^T`，再做 `(P+P.T)/2`；补 PSD 回归测试。 |
| P2 | `docs/knowledge-base.html`, `docs/V2_Knowledge/knowledge-base.html` | 主知识库与 V2 知识库并存，且 V2 语义更新更完整。 | 两个入口长期并存会制造评审漂移：Reviewer 可能读到旧模板却以为是 canonical。 | 选定 canonical 入口，另一个标注为 generated snapshot / archive；在构建脚本中加入口一致性检查。 |

## 3. 质量门复核

本轮实际复跑：

```bash
python -m pytest tests -q
# 64 passed

python -m analysis.run_all
# All 10 studies finished
```

观察：

- 测试覆盖已经能守住 import graph、event schema、runtime degraded/state/event 合同。
- §10 输出现在是 `event_count_total=14`、`distinct_kinds=4`、`event_visible_fraction=0.846`、`background_event_fraction=0.0`、`true_degraded_fraction=0.2167`。
- `analysis/artifacts/SUMMARY.txt` 里的计时字段会随机器轻微抖动，不应作为能力证据。

## 4. 架构判断

通过项：

- `starship/` 与 `sre_control/` 的依赖方向设计正确，并已有 AST 级 import graph 测试。
- Runtime event 统一到 `sre_control/events.py`，比散落字符串更可审。
- `adapter_exception` 已把 recoverable adapter failure 从 `stability_violation` 中拆开，并有 machine-readable cause 字段。
- `analysis/s10_failure_trace.py` 现在维持单一连续 stack history，并导出 full/sample JSONL。
- `docs/claude-review/` 和 `docs/codex-review/` 已经形成双向移交闭环。
- `SREControlStack.step()` 的 trace 结构足够让 Reviewer 复盘单 tick。

保留意见：

- `SREControlStack` 现在更像研究型编排器，不宜被文档写成生产控制面。
- `SignalFusion` 的 gating 还没进入 per-sensor 粒度，现阶段更像单策略 demo。
- allocator recoverable fallback 仍可能把局部退化放大成全局停流。
- before/after 的“收益”要持续写成场景内证据，尤其是 §5 `pos_p95` 变差、§8 residual 没降这类反例需要保留。

## 5. 建议下一批 PR

| Priority | PR | Scope |
|---|---|---|
| P1 | `per-sensor-gate-policy` | 为不同 signal 提供不同 gate threshold，并把实际阈值写入 trace |
| P1 | `allocator-fallback-semantics` | 把 recoverable allocator failure 从“全零 shares”收敛成更明确的安全合同 |
| P2 | `ekf-joseph-update` | Joseph covariance update、PSD 断言、病态传感器回归 |
| P2 | `knowledge-canonical-entry` | 主知识库与 V2 入口收敛，构建脚本增加漂移检查 |

## 6. 给下一位 Reviewer 的短评

这轮 Codex 的方向还是对的，而且 PR-A / PR-B 已经从评审意见变成了真实代码和测试。下一轮最该接的是 `SignalFusion` 的 per-sensor gate policy；如果只修一个行为缺口，就修 allocator recoverable fallback 的语义。
