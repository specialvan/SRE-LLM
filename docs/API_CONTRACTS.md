# API Contracts

这份文档把 `spacex/` 里真正会被调用的公开接口收拢成契约说明。  
目标很简单：让下一轮 Codex 或人类接手时，不需要先读完整个实现，就能知道每个对象该吃什么、吐什么、保什么不变量、坏了会怎么退化。

---

## 1. Cross-Cutting Rules

所有模块默认遵守这几条规矩：

1. 输入尽量是 `np.ndarray` 或原始 Python 标量，不要偷偷塞对象图。
2. 结构化输出尽量是 JSON-serializable 的 `dict` / `list` / `float` / `int`。
3. 物理量和 SRE 量必须在文档里写清单位。
4. 有状态对象必须说明状态会不会跨 tick 累积。
5. 任何“投影”“过滤”“分配”都必须写清楚它是硬约束还是软目标。
6. 数值边界上优先保守，不要靠乐观的浮点精度。
7. 本地 runtime event 必须遵守 `docs/EVENT_SCHEMA.md` 的四字段 schema。

---

## 2. Module Contracts

### 2.1 `PoolCapacityPlanner`

Public surface:

- `plan(demand_rps_forecast: list[float]) -> tuple[list[int], dict]`

Contract:

- Constructor inputs `min_keep_alive` and `max_capacity` must be integers satisfying `0 <= min_keep_alive <= max_capacity`, with `max_capacity > 0`.
- Constructor inputs `unit_cost` must be non-negative and finite; `horizon_seconds` and `rps_per_conn` must be positive finite values.
- Runtime `demand_rps_forecast` values must be finite and non-negative; invalid forecast data raises `AdapterInputError` before planning.

- 输入是每秒 RPS 预测。
- 输出是每秒池大小计划、成本信息和本地运行态 trace。
- `min_keep_alive <= pool <= max_capacity` 必须成立。
- 无流量时池不能直接掉到 0，除非显式允许 non-convex baseline。
- `info["events"]` 必须在预测需求超过硬上限时报告 `pool_capacity_clipped`。
- `info["capacity_shortfall_rps"]` 必须暴露被上限钳掉的需求量。

State:

- 无持久状态。

Failure modes:

- 预测过低时，计划会退化成最小保活。
- 预测过高时，计划会撞上 `max_capacity`，并通过 event 暴露容量缺口。
- 如果 baseline 设置成 on/off，会让“收益”看起来特别夸张，审查时要注意。

Counter-example:

- 如果 upstream 的连接池根本不需要保活，那么这个抽象就不合适。

### 2.2 `CanaryScheduler`

Public surface:

- `propose(current_share: float) -> float`
- `observe(current_share: float, proposed_share: float, observed_error_rate: float) -> CanaryStep`

Contract:

- Constructor inputs `slo_error_budget`, `eta_init`, `eta_min`, and `eta_max` must be positive finite values, with `eta_min <= eta_init <= eta_max`.
- Constructor inputs `rho_shrink` and `rho_grow` must be non-negative finite values, with `rho_shrink <= rho_grow`.
- Runtime share inputs must be finite values in `[0, 1]`; `observed_error_rate` must be finite and non-negative.

- 输入的 share 在 `[0, 1]` 里解释。
- `propose` 给出下一步灰度幅度。
- `observe` 返回 trust region、是否接受、预测误差与观测误差。
- trust region 必须保持在 `[eta_min, eta_max]` 内。
- `CanaryStep.events` 必须报告灰度拒绝等本地 failure trace。

State:

- 线性斜率估计 `b_est`
- 上一次 share / error
- 当前 trust region `eta`

Failure modes:

- 如果局部线性模型不准，trust region 会缩得过快或长得过猛。
- 如果误差观测本身不稳定，SCP 更新会抖。

Counter-example:

- 如果发布没有“比例”概念，而是一次性切版本，这个模块不适用。

### 2.3 `TopologyState`

Public surface:

- `step(velocity, angular_velocity, dt) -> dict`
- `ring_angle_rad -> float`
- `axis() -> np.ndarray`
- `distance_to(other) -> float`

Contract:

- `step` rejects non-positive/non-finite `dt` and non-finite `velocity` or `angular_velocity` with `AdapterInputError` before mutating `position`, `q`, or `omega`.
- `q` 始终按 unit quaternion 理解。
- `step` 之后姿态应保持在单位球附近。
- `step()["events"]` 必须在输入 quaternion 被 reset / renormalize 时报告 `topology_state_repaired`。
- `distance_to` 应返回“位置 + 流形角距离”的组合量。

State:

- `position`
- `q`
- `omega`

Failure modes:

- 如果把周期量当欧氏量处理，会出现环上跳变。
- 如果积分类方法不守单位模，会有漂移。
- 如果输入 quaternion 已经是零模、非有限或明显非单位模，必须先修复再积分。

Counter-example:

- 如果状态没有拓扑意义，只是普通 scalar metric，没必要上这个抽象。

### 2.4 `SLOGuardrail`

Public surface:

- `approve(proposal) -> np.ndarray`
- `audit(proposal) -> dict`

Contract:

- `approve` 必须把 proposal 投影到可行集。
- 可行集由 cone + magnitude floor/ceiling 组成。
- `audit` 必须返回可审查的违例信息。
- `audit["events"]` 必须在发生投影时报告本地 failure trace。

State:

- 只保存过滤器参数。

Failure modes:

- 若 proposal 已经在锥外很远，投影会更像“钳制”而不是平滑修正。
- 若 cone 定义错了，后续所有控制都会错在安全层。

Counter-example:

- 如果动作没有硬边界，只有概率风险，这种硬投影就会过度保守。

### 2.5 `SignalFusion`

Public surface:

- `step(dt, readings) -> dict`
- `state -> np.ndarray`
- `covariance -> np.ndarray`

Contract:

- 每个 sensor 都提供 `h / H / R`，并可选提供 per-sensor `gate_threshold` 覆盖 fusion 默认值。
- `step` 要能跳过缺失传感器，并允许同一 tick 内一部分 sensor 被 gate 拒绝、另一部分继续更新。
- 输出的 covariance 应该还能被用来做告警。
- `step()["signals"]` 要记录实际使用的 `threshold_used` 与 `innovation_mahalanobis`，便于追溯 gate 决策。
- `step()["events"]` 必须报告缺失传感器或 outlier rejection 等本地观测降级。

State:

- EKF posterior `x`
- covariance `P`

Failure modes:

- 噪声模型错了，后验会被污染。
- 观测不可辨识时，位置和速度会互相“偷解释权”。

Counter-example:

- 如果系统没有任何可用观测，fusion 只会把模型偏差越滚越大。

### 2.6 `PredictiveAutoscaler`

Public surface:

- `step(current_replicas, observed_rps, forecast_rps) -> int`

Contract:

- 输出必须是整数副本数。
- 输出必须在 `[replicas_min, replicas_max]` 内。
- `forecast_rps` 是决定性输入，不应被隐藏成副作用。
- `last_trace["events"]` 必须报告副本数打到硬边界的情况。

State:

- MPC warm-start

Failure modes:

- horizon 太短，容易跟不上 surge。
- cost 权重太大，容易过保守。
- cost 权重太小，容易过度扩容。

Counter-example:

- 如果扩缩容动作不是整数、也不是离散步长，MPC 仍可用，但这个适配层要重写。

### 2.7 `FastTrafficSwitcher`

Public surface:

- `plan(share_from, share_to, dt=0.1, deadline_s=None) -> (t_grid, share_schedule, info)`

Contract:

- Constructor inputs `rate_max` and `safety_margin` must be positive finite values.
- Runtime inputs `share_from` and `share_to` must be finite; `dt` and optional `deadline_s` must be positive finite values.

- 产出的轨迹应是两阶段 bang-bang 形态。
- 最终 share 应接近目标 share。
- 时间长度应反映 rate cap。
- `info["events"]` 必须在最短切换时间超过 deadline 时报告。

State:

- 无持久状态。

Failure modes:

- rate cap 太小，会导致切流太慢。
- 若中点健康检查没接上，bang-bang 的实际价值会下降。

Counter-example:

- 如果切换过程必须连续平滑、不能有明显拐点，这个抽象太硬。

### 2.8 `WeightedLoadBalancer`

Public surface:

- `allocate(rps_demand, zone_target) -> (shares, info)`

Contract:

- 输出必须满足每实例 box 约束。
- residual 要可报告。
- 如果 exact matching 不可能，优先给出最小残差解。
- `info["events"]` 必须报告 box 饱和或残差无法清零的情况。

State:

- 无持久状态。

Failure modes:

- 若 geometry matrix rank 不足，残差会长期存在。
- 若用了伪逆，box 约束很容易被破坏。

Counter-example:

- 如果实例之间没有任何可区分的 zone 权重，这个分配器会退化得很难看。

### 2.9 `CatchController`

> **注意 · 属 `starship/` 物理层**：本小节列出 `CatchController` 的契约是为了让 future
> wrapper 开发者参考；它本身**不是** SRE adapter，不依赖 `sre_control/events.py`。残差
> 通过 `info["alloc_residual"]` 暴露，如果未来需要把它映射成 SRE event，要新增一层
> wrapper 而不是让 `starship/` 反向依赖 `sre_control/`（见 I-1 依赖方向不变量）。

Public surface:

- `step(state, target_position, target_velocity, target_axis_body=...) -> (thrusts, info)`

Contract:

- 输出是每个 thruster 的 magnitudes。
- 先算 PD/wrench，再做有界分配。
- thrust 不能越过 `T_min / T_max`。
- 该模块属于 `starship/` 物理层，不直接依赖 `sre_control/events.py`；SRE 侧残差事件应由 `WeightedLoadBalancer` 或 future wrapper 产生。

State:

- 内部 allocator

Failure modes:

- 几何矩阵退化时，分配残差会升高。
- 目标姿态和力需求不一致时，力和矩会互相打架。

Counter-example:

- 如果没有多个执行器，只存在单个 actuator，这个最小二乘分配器就没有意义。

### 2.10 `SREControlStack`

Public surface:

- `step(...) -> dict`

Contract:

- 一次 tick 必须产出完整 trace。
- 必须能串起 observation、planning、guardrail、allocation。
- 任意子模块可以 optional 化，但 trace 不能丢。
- `runtime.states` 必须记录本 tick 经过的栈级状态。
- `runtime.events` 必须暴露缺失观测、硬边界命中、投影和分配残差等降级信号。

State:

- `trace` 历史列表

Failure modes:

- 如果上游观测缺失，系统要在低置信度下继续运行，而不是直接崩。
- 如果某子模块输出异常，应该在 trace 中可见，而不是默默吞掉。

Counter-example:

- 如果系统只是单模块控制，没有闭环编排需求，这个 stack 过重。

---

## 3. Contract-to-Test Map

| Contract | Test file | What it proves |
|---|---|---|
| `PoolCapacityPlanner` | `tests/test_sre_control.py` | keep-alive floor, capacity cap and cap events |
| `CanaryScheduler` | `tests/test_sre_control.py` | trust region adapts and rollout rejection is visible |
| `TopologyState` | `tests/test_sre_control.py` | quaternion norm stays stable and invalid quaternions are repaired visibly |
| `SLOGuardrail` | `tests/test_sre_control.py` | cone projection works and local projection events are visible |
| `SignalFusion` | `tests/test_sre_control.py` | fusion converges and missing sensors are marked locally |
| `PredictiveAutoscaler` | `tests/test_sre_control.py` | forecast growth triggers scaling and bound events are visible |
| `FastTrafficSwitcher` | `tests/test_sre_control.py` | target share is reached and deadline misses are visible |
| `WeightedLoadBalancer` | `tests/test_sre_control.py` | demand is matched without false saturation events |
| `SREControlStack` | `tests/test_contracts.py` | trace stays JSON-serializable and runtime degradation states are visible |
| Runtime events | `tests/test_event_schema.py` | every event follows schema and has a counter-example |

---

## 4. Refinement Notes

The most useful next refinement is not more prose. It is:

1. one contract test per public method,
2. one failure trace per module,
3. one counter-example per SRE mapping,
4. one explicit downgrade rule per stack stage.

That is how the abstraction becomes operationally sticky rather than merely elegant.
