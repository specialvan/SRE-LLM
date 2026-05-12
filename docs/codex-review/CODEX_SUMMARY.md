# Codex Summary for Claude Review

## 1. 当前状态

Codex 已把 SpaceX 数学支柱到 SRE 控制栈的迁移，从“可运行 demo”推进到“可审查工程包”：

- `starship/`：8 个数学支柱 + `stability_monitor.py`
- `sre_control/`：8 个 SRE adapter + `SREControlStack` + `StabilityGuard`
- `analysis/`：10 个 before/after 研究，其中 §10 专门验证 runtime events
- `tests/`：51 个测试，覆盖数学模块、SRE adapter、event schema、failure trace、import graph、stability monitor
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
| `c36d813` | 同步质量门和 review 文档到 51 passed / 10 studies / 10 events | 是否仍有旧口径残留 |

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
| §10 Failure trace | `0 events / 0 kinds` | `83 events / 4 kinds` | event lifecycle 已变成可观测证据 |

Claude 需要特别审 §10：`degraded_tick_fraction` after 为 `100%`，这是因为该研究故意把 observability 视作“打开事件通道后所有降级 tick 都可见”。这能证明事件可见性，但也可能让“降级比例”这个指标不够细，应考虑拆成 `event_visible_fraction` 与 `true_degraded_fraction`。

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

- `pytest`: 51 passed
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
- event schema 从 8 个核心 adapter 扩展到 10 个 event kind，覆盖 outlier gating 与 stability red-line。
- `analysis/s10_failure_trace.py` 把 Claude 文档中的事件生命周期变成了图和 JSONL 样例。
- `starship/stability_monitor.py` 没有 import `sre_control`，SRE 映射放在 wrapper，依赖方向仍干净。

### 仍然薄弱

- `SREControlStack` 的异常 fallback 目前偏通用，stage-specific rollback 策略还比较粗。
- `SignalFusion.gate_threshold` 是全局阈值，缺 per-sensor policy 和恢复窗口。
- `analysis/s10_failure_trace.py` 只写 sample JSONL，没有全量 trace 与 dashboard 查询脚本。
- `StabilityMonitor` 的默认例子偏抽象，还缺更像物理能量函数的验证样例。
- `docs/knowledge-base.html` 仍是旧模板，V2 知识库更完整但还未完全替换主入口。

## 8. 给 Claude 的建议审查顺序

1. 先看 `CLAUDE_REVIEW_REQUEST.md`，确认 P0/P1/P2。
2. 运行 `python -m pytest tests -q` 和 `python -m analysis.s10_failure_trace`。
3. 审 `sre_control/stack.py` 的 try/except fallback 是否过度吞错。
4. 审 `analysis/s10_failure_trace.py` 的指标命名是否误导。
5. 审 `starship/stability_monitor.py` 与 `sre_control/stability_guard.py` 的层次边界。

## 9. 下一步候选

| 优先级 | 任务 | 理由 |
|---|---|---|
| P1 | s10 全量 JSONL + dashboard query 示例 | 让事件证据可被外部工具消费 |
| P1 | stage-specific fallback policy | 避免所有异常都变成同质 `stability_violation` |
| P2 | per-sensor innovation gate | 真实 SRE 信号源噪声差异很大 |
| P2 | StabilityMonitor 物理能量函数样例 | 让 Lyapunov 抽象不止是 generic scalar |
| P2 | 主 `knowledge-base.html` 迁移到 V2 模板 | 减少两个知识入口的漂移 |
