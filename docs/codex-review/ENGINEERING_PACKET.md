# Codex Engineering Packet

> 目标：把 `spacex` 工程从“散落的实现、分析、评审文档”收束成一份可以离线交给 Reviewer 的工程包。本文不替代源码，以“读什么、信什么、哪里有风险”为主。

## 1. 工程定位

本仓库是一个学习/工程复现包：用公开文章中可抽象出的 8 个数学支柱，构造一套可运行的 Starship 回收控制原型，再把这些控制原语迁移成 SRE 控制栈。

明确边界：

- 不代表 SpaceX 官方实现。
- before/after 只证明当前合成场景内的机制收益。
- `starship/` 是数学/物理层，`sre_control/` 是 SRE 迁移层。
- `analysis/` 是证据生成，不是生产 benchmark。
- `docs/claude-review/` 是上一轮 Reviewer 移交包；本目录是 Codex 侧汇总与二次审查包。

## 2. 入口清单

| 入口 | 读者问题 | 位置 |
|---|---|---|
| 主叙事 | 这个工程在做什么 | [`README.md`](../../README.md) |
| PR 级规格 | 每个功能如何被拆成可交付 PR | [`PR-REQUIREMENTS.md`](../../PR-REQUIREMENTS.md) |
| 架构 | 分层、依赖方向、运行时链路 | [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) |
| API 契约 | 每个 adapter 输入/输出/状态 | [`docs/API_CONTRACTS.md`](../API_CONTRACTS.md) |
| 事件 schema | runtime event 的封闭命名空间 | [`docs/EVENT_SCHEMA.md`](../EVENT_SCHEMA.md) |
| 运行态 | `runtime.states` 与降级传播 | [`docs/RUNTIME_STATES.md`](../RUNTIME_STATES.md) |
| Claude 移交 | 上一轮 Reviewer 的详细包 | [`docs/claude-review/README.md`](../claude-review/README.md) |
| Codex 汇总 | 本轮交给 Reviewer 的摘要 | [`CODEX_SUMMARY.md`](./CODEX_SUMMARY.md) |
| 深度评审 | 本轮发现、分级、下一步 | [`CLAUDE_DEEP_REVIEW.md`](./CLAUDE_DEEP_REVIEW.md) |

## 3. 架构主线

运行链路可以按两层读：

| 层 | 责任 | 关键目录 |
|---|---|---|
| 数学层 | 复现凸化、SCP、刚体动力学、EKF、MPC、分配等控制原语 | `starship/` |
| SRE 层 | 把控制原语映射到容量规划、金丝雀、信号融合、护栏、负载分配等生产控制问题 | `sre_control/` |

端到端 tick：

```text
OBSERVE -> STABILITY -> PLAN -> GUARD -> ALLOCATE -> EXECUTE
```

对应实现：

- `SignalFusion.step()` 融合观测，产生 `missing_sensor` / `outlier_rejected`。
- `StabilityGuard.step()` 监控 Lyapunov 候选函数，产生 `stability_violation`。
- `PredictiveAutoscaler.step()` 与 `CanaryScheduler` 负责计划，产生 `replica_bound_active` / `rollout_rejected`。
- `SLOGuardrail.audit()` 投影不安全动作，产生 `unsafe_proposal_projected`。
- `WeightedLoadBalancer.allocate()` 做有界最小二乘，产生 `bounded_ls_residual`。
- `SREControlStack.step()` 汇总 `runtime.states`、`runtime.events` 和每阶段 trace。

## 4. 8 支柱到 SRE 的审查矩阵

| # | 数学支柱 | SRE adapter | Event kind | 主要测试 |
|---|---|---|---|---|
| 1 | Lossless Convexification | `PoolCapacityPlanner` | `pool_capacity_clipped` | `tests/test_sre_control.py` |
| 2 | SCP / trust region | `CanaryScheduler` | `rollout_rejected` | `tests/test_sre_control.py`, `tests/test_contracts.py` |
| 3 | SO(3) / topology state | `TopologyState` | `topology_state_repaired` | `tests/test_import_graph.py`, `tests/test_sre_control.py` |
| 4 | Thrust cone projection | `SLOGuardrail` | `unsafe_proposal_projected` | `tests/test_thrust_constraints.py`, `tests/test_contracts.py` |
| 5 | EKF fusion | `SignalFusion` | `missing_sensor`, `outlier_rejected` | `tests/test_ekf.py`, `tests/test_event_schema.py` |
| 6 | Receding-horizon MPC | `PredictiveAutoscaler` | `replica_bound_active` | `tests/test_mpc.py`, `tests/test_sre_control.py` |
| 7 | Bang-bang flip | `FastTrafficSwitcher` | `deadline_exceeded` | `tests/test_sre_control.py` |
| 8 | Bounded LS allocation | `WeightedLoadBalancer` | `bounded_ls_residual` | `tests/test_allocation.py`, `tests/test_contracts.py` |
| + | Lyapunov stability | `StabilityGuard` | `stability_violation` | `tests/test_stability_monitor.py`, `tests/test_contracts.py` |

## 5. 当前证据

本轮复跑结果：

```bash
python -m pytest tests -q      # 51 passed
python -m analysis.run_all     # All 10 studies finished
```

关键证据解读：

| Study | 观察 | 审查口径 |
|---|---|---|
| §1 Lossless | `pos_err 148.3 -> 2.125e-6` | 证明合成 PDG 场景中凸化路径有效 |
| §4 Cone | `cone_violations 0.974 -> 0` | 证明硬护栏能消除越界动作 |
| §5 EKF | `vel_rmse 481.1 -> 51.07` | 证明多源融合改善速度估计，但 `pos_p95` 变差，需要谨慎解释 |
| §8 Allocation | `saturation_violation_pct 33.75 -> 0` | 证明有界求解消除容量越界，不证明 residual 消失 |
| §9 SRE Stack | `slo_violation_pct 25 -> 10` | 证明控制栈用更高副本成本换更低 SLO 违例 |
| §10 Failure trace | `0 events / 0 kinds -> 83 events / 4 kinds` | 证明事件通道可观测，但 `degraded_tick_fraction=100` 的指标语义需要修 |

## 6. 守护不变量

| Invariant | 为什么重要 | 守护方式 |
|---|---|---|
| `starship/` 不 import `sre_control/` | 防止物理/数学层被 SRE 语义污染 | `tests/test_import_graph.py` |
| Event schema 封闭 | 防止文档列出但运行时不能生成的 kind | `sre_control/events.py`, `tests/test_event_schema.py` |
| 降级路径对齐 | `runtime.degraded=True` 必须有 `DEGRADED_*` 状态和事件证据 | `tests/test_contracts.py` |
| 文档不钉死 HEAD | 避免交接文档一提交就过期 | 本目录用“近期日志包含”而不是“最新 commit = SHA” |
| adapter 异常不崩 tick | 单阶段失败不能让整条 trace 丢失 | `SREControlStack.step()` + contract tests |

## 7. Reviewer 应优先看的问题

第一优先级不是“能不能跑”，而是“证据是否被过度解释”。当前质量门绿色，但仍有四类需要深审：

- `analysis/s10_failure_trace.py` 是否真的模拟同一条连续控制环。
- `degraded_tick_fraction` 是否应该拆成 `event_visible_fraction` 与 `runtime_degraded_fraction`。
- `SREControlStack.step()` 的异常兜底是否把 programmer error 也当成可恢复控制异常。
- `StabilityMonitor` 的触发是否应该永久 latch，还是需要恢复条件和清除事件。

详见 [`CLAUDE_DEEP_REVIEW.md`](./CLAUDE_DEEP_REVIEW.md)。

## 8. 下一步拆包

建议下一轮按 PR 粒度推进：

| PR | 范围 | 验收 |
|---|---|---|
| PR-A | 修 `s10`：单 stack 注入、指标拆名、全量 JSONL | `tests/test_failure_trace.py` 增加连续性和指标语义断言 |
| PR-B | 异常兜底策略：typed control exception、programmer error fail-fast、stage-specific fallback | `tests/test_contracts.py` 覆盖可恢复与不可恢复异常 |
| PR-C | Stability recovery：明确 latch/manual reset 或自动 clear 策略 | `tests/test_stability_monitor.py` 覆盖恢复窗口 |
| PR-D | EKF covariance：Joseph form + 对称化 + PSD 断言 | `tests/test_ekf.py` 增加数值稳定性回归 |

