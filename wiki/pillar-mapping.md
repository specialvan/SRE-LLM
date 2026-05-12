# Pillar Mapping

## 8 个数学支柱到 SRE adapter

| # | 数学支柱 | SRE adapter | Event kind | 当前证据边界 |
|---|---|---|---|---|
| 1 | Lossless Convexification | `PoolCapacityPlanner` | `pool_capacity_clipped` | SRE 侧是容量 clipping/shortfall 映射，不是完整 PDG 凸化证明 |
| 2 | SCP / trust region | `CanaryScheduler` | `rollout_rejected` | 证明 scalar canary trust-region 语义，不证明多维 SCP 收敛 |
| 3 | SO(3) / topology state | `TopologyState` | `topology_state_repaired` | 保证单位四元数/repair，不等价于真实服务拓扑物理模型 |
| 4 | Thrust cone projection | `SLOGuardrail` | `unsafe_proposal_projected` | 投影保证动作可行，不保证业务意图或收益保持 |
| 5 | EKF fusion | `SignalFusion` | `missing_sensor`, `outlier_rejected` | 当前更像 radar/filtering 场景证据；per-sensor gate 仍需加强 |
| 6 | Receding-horizon MPC | `PredictiveAutoscaler` | `replica_bound_active` | 证明 bounded replica planning，不证明容量规划最优 |
| 7 | Bang-bang flip | `FastTrafficSwitcher` | `deadline_exceeded` | local/schema 证据较强，hot path 接入仍有限 |
| 8 | Bounded LS allocation | `WeightedLoadBalancer` | `bounded_ls_residual` | residual 可观测但不会自动消失，需要业务告警语义 |
| + | Lyapunov stability | `StabilityGuard` | `stability_violation` | 当前是 generic scalar monitor，manual-reset latch 需合同化 |

## 分层边界

- `starship/` 不应 import `sre_control/`。
- `sre_control/` 可以使用 `starship/` 控制原语并生成 SRE runtime events。
- `analysis/` 和 `examples/` 是消费方，不应成为底层依赖。
- `CatchController` 属于物理层；若要产生 SRE event，应新增 SRE wrapper，而不是让 `starship/` 反向依赖 `sre_control/events.py`。

## 审查重点

1. 不要把数学原语迁移误写成 SpaceX 官方实现。
2. 不要把场景内 evidence 泛化成生产 guarantee。
3. 每个 adapter 的 safe action 需要同时说明“保证了什么”和“没有保证什么”。
4. event kind 必须由真实 adapter 生成，并配 counter-example。
