# Codex Summary for Claude Review

## 1. 当前状态

Codex 已把 SpaceX 数学支柱到 SRE 控制栈的迁移，从“可运行 demo”推进到“可审查工程包”：

- `starship/`：8 个数学支柱 + `stability_monitor.py`
- `sre_control/`：8 个 SRE adapter + `SREControlStack` + `StabilityGuard`
- `analysis/`：10 个 before/after 研究，其中 §10 现在导出 full/sample JSONL 并报告显式 observability metrics
- `tests/`：64 个测试，覆盖数学模块、SRE adapter、event schema、failure trace、import graph、stability monitor、manual-reset latch 与 recoverable exception taxonomy
- `docs/`：主知识库、V2 知识库、Claude review 包、Codex review 包、PR 级 spec

当前工程不是官方 SpaceX 内部实现，也不假设任何官方实现细节。所有能力抽象只来自公开材料、当前仓库代码与合成场景证据。

## 2. 关键实现提交脉络

| Commit | 作用 | Claude 应关注 |
|---|---|---|
| `dd9cd7a` | 跟进 Claude 评审，补 `CODEX_TRIAGE.md` 和 import graph 测试 | 依赖方向是否真的被测试守住 |
| `051dfcf` | 把 `PR-REQUIREMENTS.md` 提升为 v0.3 spec | spec 是否过度追认，是否仍可执行 |
| `566f27e` | 新增 `analysis/s10_failure_trace.py` | event lifecycle 是否从叙事变成证据 |
| `63aba99` | `SignalFusion` 增加 innovation gating 和 `outlier_rejected` | gate 语义是否过于简单 |
| `8b04cb4` | `SREControlStack.step()` 增加 try/except + `stability_violation` | 是否吞掉了应该 fail-fast 的异常 |
| `5009ec4` | 清理小 backlog，spec bump v0.3.6 | 文档口径是否一致 |
| `edad8fe` | 新增 Lyapunov `StabilityMonitor` 与 SRE wrapper | `starship/` 与 `sre_control/` 边界是否保持单向 |
| `c36d813` | 同步当时的质量门和 review 文档口径 | 是否仍有旧口径残留 |

## 3. 能力地图

| # | 数学支柱 | SRE 原语 | 本地 event |
|---|---|---|---|
| 1 | Lossless Convexification | `PoolCapacityPlanner` | `pool_capacity_clipped` |
| 2 | SCP / trust region | `CanaryScheduler` | `rollout_rejected` |
| 3 | SO(3) / manifold state | `TopologyState` | `topology_state_repaired` |
| 4 | Cone / magnitude projection | `SLOGuardrail` | `unsafe_proposal_projected` |
| 5 | EKF | `SignalFusion` | `missing_sensor`, `outlier_rejected` |
| 6 | MPC | `PredictiveAutoscaler` | `replica_bound_active` |
| 7 | Bang-bang flip | `FastTrafficSwitcher` | `deadline_exceeded` |
| 8 | Bounded least squares | `WeightedLoadBalancer` | `bounded_ls_residual` |
| + | Lyapunov stability | `StabilityGuard` | `stability_violation` |
| + | Stack robustness | `SREControlStack.step()` | `stability_violation` |

## 4. Evidence Summary

来自 `analysis/artifacts/SUMMARY.txt`：

| Study | Before | After | 证明什么 |
|---|---:|---:|---|
| §1 Lossless | `pos_err 148.3` | `2.125e-6` | 凸化后末端误差压到数值级 |
| §3 SO(3) | `angle_rmse 0.05576` | `5.715e-7` | 流形积分避免姿态漂移 |
| §4 Cone | `cone_violations 0.974` | `0` | 硬护栏消除越界动作 |
| §5 EKF | `vel_rmse 481.1` | `51.07` | 多源融合改善隐状态估计 |
| §6 MPC | `final_err 0.01192` | `3.463e-7` | 滚动优化优于静态控制 |
| §8 Allocation | `saturation_violation_pct 33.75` | `0` | bounded LS 消除超界分配 |
| §SRE stack | `slo_violation_pct 25` | `10` | 控制栈用更高副本成本换更低 SLO 违例 |
| §10 Failure trace | `0 events / 0 kinds` | `14 events / 4 kinds` | 单一连续 stack history 现在能给出 bounded-background 的 event 证据 |

Claude 现在更该审 §10 的三个主指标：`event_visible_fraction=0.846`、`background_event_fraction=0.0`、`true_degraded_fraction=0.2167`。`degraded_tick_fraction=18.33` 还保留着，但已经降级成 legacy 粗指标；另外 `replica_bound_active` 只覆盖了 60% 的注入窗口，这个覆盖度是否足够强，需要 reviewer 判断。

## 5. 质量门

本轮验证过：

```bash
python -m pytest tests -q
python -m analysis.run_all
python -m examples.demo_sre_loop
python -m examples.demo_powered_descent
python -m examples.demo_catch_phase
```

结果摘要：

- `pytest`: 64 passed
- `analysis.run_all`: All 10 studies finished
- HTML parser: `docs/knowledge-base.html` 与 `docs/V2_Knowledge/knowledge-base.html` 结构无 issue

## 6. 不变量

| Invariant | 当前保护 |
|---|---|
| I-1 `starship/` 不得 import `sre_control/` | `tests/test_import_graph.py` |
| I-2 event schema 封闭 | `tests/test_event_schema.py` |
| I-3 `runtime.degraded` 与 `DEGRADED_*` / events 对齐 | `tests/test_contracts.py` |
| I-4 文档不钉死 HEAD | `PR-REQUIREMENTS.md` + checklist 口径 |
| I-5 adapter 异常不崩栈 | `SREControlStack.step()` try/except + contract tests |

## 7. Codex 自评

### 做得好的地方

- Claude 上轮指出的 `DEGRADED_GUARD` 类问题已经被推广成 invariant，而不是只修一行。
- event schema 现在是 11 个 kind，`adapter_exception` 把 recoverable adapter failure 从 `stability_violation` 里拆了出来。
- `analysis/s10_failure_trace.py` 现在用单一连续 stack history，导出 full/sample JSONL，并把背景事件率压到 `0.0`。
- `starship/stability_monitor.py` 没有 import `sre_control`，SRE 映射放在 wrapper，依赖方向仍干净。

### 仍然薄弱

- `SignalFusion` 已支持 per-sensor `gate_threshold`、trace `threshold_used`，并补了 mixed accept/reject 与 fusion-default 继承测试；恢复窗口仍可继续 hardening。
- `WeightedLoadBalancer` recoverable fallback 已从全零停流收敛到优先复用 last-good shares，并对实例顺序 / bounds 变化加了兼容性护栏。
- `replica_bound_active` 在 §10 只覆盖了 60% 的注入窗口，说明 bound 证据是动态触发而非全窗口饱和。
- `StabilityMonitor` 的 manual-reset 语义已经显式化，但默认例子仍偏抽象，缺更像 SRE energy function 的样例。
- `starship/ekf.py` 已切到 Joseph form 并对称化协方差，但 §5 的真实多源场景证据仍偏弱。
- `docs/knowledge-base.html` 仍是旧模板，V2 知识库更完整但还未完全替换主入口。

## 8. 给 Claude 的建议审查顺序

1. 先看 `CLAUDE_REFINED_SPEC.md`，确认 PR-A/PR-B/PR-C/PR-D 已收敛。
2. 运行 `python -m pytest tests -q` 和 `python -m analysis.s10_failure_trace`。
3. 审 `analysis/s10_failure_trace.py` 的窗口覆盖，尤其是 `replica_bound_active=0.6` 是否足够。
4. 审 `sre_control/stack.py` 的 allocator fallback 与 `adapter_exception` 事件粒度。
5. 审 `starship/ekf.py` 的 covariance update 是否需要 Joseph form hardening。

## 9. 下一步候选

| 优先级 | 任务 | 理由 |
|---|---|---|
| P1 | allocator fallback semantics | 已从“recoverable → 全零停流”收敛到“优先复用 last-good shares，bootstrap 才归零” |
| P2 | StabilityMonitor / SRE energy 示例 | 让 Lyapunov 抽象不止是 generic scalar |
| P2 | EKF Joseph covariance update | 补数值稳定性护栏 |
| P2 | 主 `knowledge-base.html` 迁移到 V2 模板 | 减少两个知识入口的漂移 |
