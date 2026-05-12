# Runtime Lifecycle

## Stack state machine

`SREControlStack.step()` 可按一个小型状态机理解：

```text
INIT -> OBSERVING -> PLANNING -> GUARDING -> ALLOCATING -> EXECUTING
```

降级态包括：

| State | Meaning | Safe action |
|---|---|---|
| `DEGRADED_OBSERVE` | 观测缺失、异常或可信度下降 | 保留 posterior prediction，降低信心 |
| `DEGRADED_PLAN` | 预测、稳定性或计划阶段不可信 | 缩短 horizon、冻结 rollout 或保守回退 |
| `DEGRADED_ALLOCATE` | residual 无法清零或分配受限 | 保留 bounded LS trace，不伪装 exact match |
| `EMERGENCY_CUTOVER` | incident / rollback / deadline 触发 | 使用 bang-bang switcher 或冻结变更 |

## Event schema

runtime event 最小字段：

| Field | Meaning |
|---|---|
| `stage` | 产生事件的 adapter 或阶段 |
| `kind` | 稳定事件类型 |
| `detail` | 当前 tick 发生了什么 |
| `safe_action` | 控制栈采取的保守动作 |

当前 registry 共 10 种 kind：

| Kind | Producer | 语义 |
|---|---|---|
| `missing_sensor` | `SignalFusion.step()` | 某路观测缺失 |
| `outlier_rejected` | `SignalFusion.step()` | innovation gate 拒绝异常观测 |
| `rollout_rejected` | `CanaryScheduler.observe()` | 灰度观测烧穿预算 |
| `unsafe_proposal_projected` | `SLOGuardrail.audit()` | proposal 被投影回可行集 |
| `replica_bound_active` | `PredictiveAutoscaler.step()` | 副本数触达 min/max |
| `deadline_exceeded` | `FastTrafficSwitcher.plan()` | 最短切换时间超过 deadline |
| `bounded_ls_residual` | `WeightedLoadBalancer.allocate()` | bounded LS residual 无法清零 |
| `pool_capacity_clipped` | `PoolCapacityPlanner.plan()` | pool 被容量上限钳制 |
| `topology_state_repaired` | `TopologyState.step()` | quaternion 被 reset / renormalize |
| `stability_violation` | `StabilityGuard.step()` / stack fallback | Lyapunov 红线或当前过宽异常兜底 |

## 当前语义风险

- `stability_violation` 同时承载 Lyapunov 红线和 adapter 异常兜底，语义压力过大。
- `SREControlStack.step()` 当前 fallback 口径仍需区分 recoverable control-domain error 与 programmer error。
- `docs/RUNTIME_STATES.md` 的 local emitter 表曾按 8 个 core adapter 写法表达；阅读时应结合 `docs/EVENT_SCHEMA.md` 的 10 kinds。

## 下一步合同

PR-B 应引入 stage-specific fallback taxonomy，事件 payload 至少应能区分：

- `stage`
- `exception_type`
- `cause_type`
- `recoverable`

PR-C 固化 StabilityGuard manual-reset latch 语义：触发后保持 triggered，直到显式 `reset()`。
