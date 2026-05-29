# SRE Runtime Event Schema

这份文档定义 `sre_control/` 里本地 runtime event 的最小共享格式。

它解决的问题是：每个 adapter 都能报告自己的 failure trace，但不要让每个模块各自发明字段名，最后让 `SREControlStack.step()` 很难汇总。

## 1. Event Shape

每个 event 必须是 JSON-serializable 的 `dict`，并至少包含四个字段：

| Field | Meaning |
|---|---|
| `stage` | 产生事件的 adapter 或阶段 |
| `kind` | 稳定事件类型，用于测试和文档索引 |
| `detail` | 当前 tick 发生了什么 |
| `safe_action` | 控制栈采取的保守动作 |

代码入口：

- `sre_control/events.py::make_event`
- `sre_control/events.py::validate_event`
- `sre_control/events.py::EVENT_COUNTEREXAMPLES`

## 2. Current Event Kinds

| Kind | Producer | Trigger | Safe action | Counter-example |
|---|---|---|---|---|
| `missing_sensor` | `SignalFusion.step()` | 某路观测为 `None` | 跳过 update，保留 posterior prediction | 不要把一路低价值观测缺失直接当成全局事故；只有当该观测影响当前控制动作时才降级信心 |
| `rollout_rejected` | `CanaryScheduler.observe()` | 灰度观测错误率烧穿预算 | 缩小 trust region 并冻结推进 | 一次性迁移没有流量比例 ramp，不适合用灰度拒绝事件表达 |
| `unsafe_proposal_projected` | `SLOGuardrail.audit()` | proposal 违反 cone 或 magnitude | 只执行投影后的 action | 小投影距离可能只是数值 clipping，不一定说明上游策略坏了 |
| `replica_bound_active` | `PredictiveAutoscaler.step()` | 下一个副本数打到 min/max | 返回有界整数副本数 | 打到 `replicas_max` 可能是 quota 或依赖容量问题，不一定是 autoscaler 失效 |
| `deadline_exceeded` | `FastTrafficSwitcher.plan()` | 最短切换时间超过 deadline | 冻结变更或走更简单 rollback | 没有健康检查卡位时，不要为了赶 deadline 强行 bang-bang 切流 |
| `bounded_ls_residual` | `WeightedLoadBalancer.allocate()` / `CatchLoadAdapter.allocate()` | box 饱和或 residual 无法清零 | 报告 residual，不伪装 exact match | 不要 solve 后强行归一化 shares；那会悄悄破坏 per-instance capacity box |
| `pool_capacity_clipped` | `PoolCapacityPlanner.plan()` | 预测需求超过 `max_capacity * rps_per_conn` | 池大小钳到 `max_capacity`，同时暴露 `capacity_shortfall_rps` | 撞上连接池上限可能是 quota、依赖容量或上游削峰问题，不一定是 planner 算错 |
| `topology_state_repaired` | `TopologyState.step()` | 输入 quaternion 非有限、接近零或明显非单位模 | 先 reset / renormalize，再做 exp-map 积分 | 不要把普通 scalar metric 当成流形状态硬归一化；只有明确拓扑姿态态才适合修复 |
| `outlier_rejected` | `SignalFusion.step()` (当 `gate_threshold` 启用时) | 观测的 Mahalanobis 距离 `√(yᵀS⁻¹y)` 超过 gate 阈值 | 跳过 update 保护 posterior，保留 predict 结果 | 不要通过调高 gate 来让事件消失；持续 outlier 通常意味着 `h(x)` 或 `R` 设置错了 |
| `stability_violation` | `StabilityGuard.step()` | `dV/dt > tolerance` 连续 k 次 | 记录 Lyapunov 红线并要求 operator review | 不要把 Lyapunov 红线当成普通告警噪声；持续稳定性违例意味着控制目标正在向错误方向移动 |
| `adapter_exception` | `SREControlStack.step()` | adapter 抛出 `RecoverableControlError` | 记录异常原因，替换为该阶段 validated fallback，并继续 tick | 不要吞 `AttributeError` / `TypeError` 等 programmer error；只有控制域可恢复失败才能走该事件 |

`adapter_exception` 额外要求 machine-readable 字段：

| Field | Meaning |
|---|---|
| `exception_type` | 异常类名，例如 `RecoverableControlError` |
| `cause_type` | 失败原因分类；`AdapterInputError` 使用 `adapter_input`，其他可恢复控制域 fallback 使用 `control_domain` |
| `adapter_family` | 阶段族：`observe` / `plan` / `rollout` / `guard` / `allocate` |
| `fault_family` | remediation 使用的故障族；当前与 `cause_type` 同步 |
| `fallback_action` | 具体 fallback，例如 `keep_current_replicas` 或 `reuse_last_good_shares` |
| `fallback_mode` | 粗粒度替代策略，例如 `keep_current_value`、`zero_action`、`reuse_last_good_cache`，供 dashboard/report 分桶 |
| `recoverable` | 是否可用 validated fallback 安全完成本 tick |

`CatchController` 属于 `starship/` 物理层，仍通过 `info["alloc_residual"]` 暴露分配残差，但不反向 import `sre_control/events.py`。SRE 侧捕获/负载 wrapper 由 `CatchLoadAdapter` 生成 runtime event，避免 `starship/` 对迁移层产生倒置依赖。

## 3. Kind-Specific Fields

`validate_event()` now enforces an exact field set for every known event kind:
the four base fields plus the kind-specific fields below. Unknown extra fields
are rejected so typoed payload keys cannot silently enter review artifacts.

| Kind | Required kind-specific fields |
|---|---|
| `missing_sensor` | `signal` |
| `rollout_rejected` | `observed_error_rate`, `slo_error_budget`, `trust_region` |
| `unsafe_proposal_projected` | `cone_violated_before`, `magnitude_violated_before`, `projection_distance` |
| `replica_bound_active` | `next_replicas`, `replicas_min`, `replicas_max` |
| `deadline_exceeded` | `minimum_time_seconds`, `deadline_seconds` |
| `bounded_ls_residual` | `rps_residual`, `rps_residual_fraction`, `zone_residual`, `demand_satisfied` |
| `pool_capacity_clipped` | `clipped_slots`, `capacity_shortfall_rps`, `max_capacity` |
| `topology_state_repaired` | `input_norm_valid`, `quaternion_norm`, `repair_action` |
| `outlier_rejected` | `signal`, `innovation_mahalanobis`, `threshold_used`, `consecutive_rejections` |
| `stability_violation` | `label`, `V`, `dV_dt`, `consecutive_violations`, `tolerance` |
| `adapter_exception` | `exception_type`, `cause_type`, `adapter_family`, `fault_family`, `fallback_action`, `fallback_mode`, `recoverable` |

`bounded_ls_residual` makes the distinction between safe bounded projection and
fully satisfied demand machine-checkable in evidence artifacts.

`adapter_exception` lets reviewers distinguish recoverable control-domain
fallback from programmer errors and route remediation by stage family. Its
`adapter_family` value is derived from `stack_data_contract().event_stage_routes`
so trace payloads and the exported stack contract cannot drift independently.
`fallback_mode` is intentionally coarser than `fallback_action`: the action keeps
the exact code path, while the mode lets reviewers group events by replacement
strategy without minting new event kinds. `SREControlStack._adapter_exception_event()`
rejects fallback actions that are not declared in `stack_data_contract()`, so a
typo or new fallback path must update the exported contract before it can enter
runtime evidence.

## 4. Stack Aggregation

Adapter 先产生本地 `events`，然后 `SREControlStack.step()` 做两件事：

1. 汇总 adapter 本地事件到 `entry["runtime"]["events"]`
2. 根据事件类别补上栈级 `DEGRADED_*` 状态

这让 trace 同时保留两层信息：

- 本地：哪个 adapter 具体失败、采取了什么保守动作
- 全局：这个 tick 是否进入 degraded runtime state

## 5. Test Coverage

事件 schema 由 `tests/test_event_schema.py` 固化：

- 每个 event 必须满足 `validate_event`
- 每个已知 `kind` 必须有 counter-example
- 十一种当前 event kind 都必须能由本地 adapter 或 stack 聚合路径生成

如果新增 event kind，先补 `EVENT_COUNTEREXAMPLES`，再补测试。
