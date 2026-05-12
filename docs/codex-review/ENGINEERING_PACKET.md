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
| 项目 wiki | 跨会话知识库、证据边界、review backlog | [`../../wiki/README.md`](../../wiki/README.md) |

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

## 5. 细粒度实现溯源

这张表把“数学支柱 → SRE adapter → event → tests → evidence → 弱点”压到 reviewer 可以逐行核对的粒度。

| Area | 主要实现 | Event / runtime path | 测试锚点 | Evidence | 当前可信边界 |
|---|---|---|---|---|---|
| §1 Lossless Convexification | `starship/lossless_convex.py`, `sre_control/pool_planner.py` | `pool_capacity_clipped` | `tests/test_sre_control.py`, `tests/test_event_schema.py` | `analysis/s01_lossless_convex.py` | SRE adapter 是容量 clipping/shortfall 映射，不是完整 PDG 凸化证明 |
| §2 SCP / trust region | `starship/scp.py`, `sre_control/canary_scheduler.py` | `rollout_rejected` | `tests/test_sre_control.py`, `tests/test_contracts.py` | `analysis/s02_scp.py` | 证明 scalar canary trust-region 语义，不证明多维 SCP 收敛 |
| §3 SO(3) / manifold state | `starship/quaternion.py`, `starship/rigid_body.py`, `sre_control/topology_state.py` | `topology_state_repaired` | `tests/test_quaternion.py`, `tests/test_rigid_body.py`, `tests/test_import_graph.py` | `analysis/s03_rigid_body.py` | topology wrapper 保证单位四元数/repair，不等价于真实服务拓扑物理模型 |
| §4 Cone projection | `starship/thrust_constraints.py`, `sre_control/slo_guardrail.py` | `unsafe_proposal_projected` | `tests/test_thrust_constraints.py`, `tests/test_contracts.py` | `analysis/s04_thrust_cone.py` | 投影保证动作可行，不保证业务意图或收益保持 |
| §5 EKF / SignalFusion | `starship/ekf.py`, `sre_control/signal_fusion.py` | `missing_sensor`, `outlier_rejected` | `tests/test_ekf.py`, `tests/test_sre_control.py`, `tests/test_event_schema.py` | `analysis/s05_ekf.py` | 当前 evidence 更像 radar EKF/filtering；per-sensor gate、Joseph covariance、真实多源场景仍弱 |
| §6 MPC / autoscaling | `starship/mpc.py`, `sre_control/predictive_autoscaler.py` | `replica_bound_active` | `tests/test_mpc.py`, `tests/test_sre_control.py`, `tests/test_failure_trace.py` | `analysis/s06_mpc.py`, `analysis/s09_sre_stack.py` | 证明 bounded replica planning，不证明容量规划最优 |
| §7 Bang-bang flip / traffic switch | `starship/flip_maneuver.py`, `sre_control/fast_switcher.py` | `deadline_exceeded` | `tests/test_sre_control.py`, `tests/test_event_schema.py` | `analysis/s07_flip_maneuver.py` | switcher event 主要是 local/schema 证据，尚未作为 hot path 接入 stack tick |
| §8 Bounded LS allocation | `starship/catch_controller.py`, `sre_control/weighted_balancer.py` | `bounded_ls_residual` | `tests/test_allocation.py`, `tests/test_contracts.py` | `analysis/s08_catch_allocation.py`, `analysis/s10_failure_trace.py` | residual 可观测但不会自动消失；在 §10 中还会形成背景噪声 |
| Lyapunov stability | `starship/stability_monitor.py`, `sre_control/stability_guard.py` | `stability_violation` | `tests/test_stability_monitor.py`, `tests/test_contracts.py` | 无独立 analysis study，主要靠单测和 stack trace | 默认是 generic scalar monitor；latch/manual reset 语义必须显式化 |
| SREControlStack lifecycle | `sre_control/stack.py`, `sre_control/events.py` | 聚合所有 adapter events；fallback 也用 `stability_violation` | `tests/test_contracts.py`, `tests/test_event_schema.py`, `tests/test_import_graph.py` | `analysis/s09_sre_stack.py`, `analysis/s10_failure_trace.py` | 研究型编排器可信；生产容错语义需 typed exception / stage policy 后才可信 |

## 6. 当前证据

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
| §5 EKF | `vel_rmse 481.1 -> 51.07` | 证明当前场景内 filtering 改善速度估计，但 `pos_p95` 变差，需要谨慎解释 |
| §8 Allocation | `saturation_violation_pct 33.75 -> 0` | 证明有界求解消除容量越界，不证明 residual 消失 |
| §9 SRE Stack | `slo_violation_pct 25 -> 10` | 证明控制栈用更高副本成本换更低 SLO 违例 |
| §10 Failure trace | `0 events / 0 kinds -> 83 events / 4 kinds` | 证明事件通道可观测，但 `degraded_tick_fraction=100` 的指标语义需要修 |

## 7. 守护不变量

| Invariant | 为什么重要 | 守护方式 |
|---|---|---|
| `starship/` 不 import `sre_control/` | 防止物理/数学层被 SRE 语义污染 | `tests/test_import_graph.py` |
| Event schema 封闭 | 防止文档列出但运行时不能生成的 kind | `sre_control/events.py`, `tests/test_event_schema.py` |
| 降级路径对齐 | `runtime.degraded=True` 必须有 `DEGRADED_*` 状态和事件证据 | `tests/test_contracts.py` |
| 文档不钉死 HEAD | 避免交接文档一提交就过期 | 本目录用“近期日志包含”而不是“最新 commit = SHA” |
| adapter 异常不崩 tick | 单阶段失败不能让整条 trace 丢失 | `SREControlStack.step()` + contract tests |

## 8. Reviewer 应优先看的问题

第一优先级不是“能不能跑”，而是“证据是否被过度解释”。当前质量门绿色，但仍有四类需要深审：

- `analysis/s10_failure_trace.py` 是否真的模拟同一条连续控制环。
- `degraded_tick_fraction` 是否应该拆成 `event_visible_fraction` 与 `runtime_degraded_fraction`。
- `SREControlStack.step()` 的异常兜底是否把 programmer error 也当成可恢复控制异常。
- `StabilityMonitor` 的触发是否应该永久 latch，还是需要恢复条件和清除事件。

详见 [`CLAUDE_DEEP_REVIEW.md`](./CLAUDE_DEEP_REVIEW.md)。

## 9. Codex 打回评审汇总

本次打回不是 P0 否决，而是要求把“能跑通”的结论降级为“可继续审查”，并把证据口径、异常策略和恢复语义补成下一批工程 PR。工程包按下面口径收束：

| Priority | 打回项 | 当前证据 | 工程处理 | 下一步 |
|---|---|---|---|---|
| P1 | §10 failure trace 不是严格连续控制环 | `analysis/s10_failure_trace.py` 为触发 bound event 切换两个 stack，且 `degraded_tick_fraction` 按 event 数计算 | 只认可“event channel 可观测”，不再写成“runtime 全程降级证据” | 单 stack 注入、拆 `event_visible_fraction` / `runtime_degraded_fraction`、导出全量 JSONL |
| P1 | `SREControlStack` fallback 过宽 | 每个 stage 都 `except Exception`，异常统一转 `stability_violation` | 当前作为研究 trace 可接受；不能当生产容错策略 | 分离 recoverable control exception 与 programmer error；补 stage-specific fallback |
| P1 | `StabilityMonitor` 触发后恢复语义不清 | `triggered` 当前永久 latch，stack 持续追加 `DEGRADED_PLAN` | 需要明确是人工确认红线还是自动恢复信号 | 增加 latch/manual reset 或 recovery window 合同与测试 |
| P2 | EKF / SignalFusion 证据和数值稳定性不足 | §5 文档说 multi-sensor，但当前主要喂 radar；covariance update 不是 Joseph form | 不再把 §5 写成强多源融合证明，只保留场景内 filtering 证据 | 接入真实 fiducial update 或改名；补 Joseph form、PSD 回归、per-sensor gate |
| P2 | fallback 安全动作需要 SRE 语义复审 | allocator 异常 fallback 为全零 shares | “route nothing” 不应默认等同安全 | hold last known good shares，或显式 `traffic_halt=True` 让上游 fail closed |
| P2 | 文档入口仍可能漂移 | 主知识库与 V2 知识库并存 | 本目录作为当前评审入口；知识库入口另开收敛 PR | 选 canonical 入口，并在构建脚本做 drift check |

打回后的 reviewer 读法：先看上表决定是否接受当前证据边界，再看 [`CLAUDE_DEEP_REVIEW.md`](./CLAUDE_DEEP_REVIEW.md) 的逐条 finding，最后把 [`OPEN_RISKS.md`](./OPEN_RISKS.md) 作为后续 PR backlog。

## 10. 下一步拆包

建议下一轮按 PR 粒度推进：

| PR | 范围 | 验收 |
|---|---|---|
| PR-A | 修 `s10`：单 stack 注入、指标拆名、全量 JSONL | `tests/test_failure_trace.py` 增加连续性和指标语义断言 |
| PR-B | 异常兜底策略：typed control exception、programmer error fail-fast、stage-specific fallback | `tests/test_contracts.py` 覆盖可恢复与不可恢复异常 |
| PR-C | Stability recovery：明确 latch/manual reset 或自动 clear 策略 | `tests/test_stability_monitor.py` 覆盖恢复窗口 |
| PR-D | EKF covariance：Joseph form + 对称化 + PSD 断言 | `tests/test_ekf.py` 增加数值稳定性回归 |

