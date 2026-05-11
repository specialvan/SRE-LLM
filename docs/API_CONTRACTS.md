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

---

## 2. Module Contracts

### 2.1 `PoolCapacityPlanner`

Public surface:

- `plan(demand_rps_forecast: list[float]) -> tuple[list[int], dict]`

Contract:

- 输入是每秒 RPS 预测。
- 输出是每秒池大小计划和成本信息。
- `min_keep_alive <= pool <= max_capacity` 必须成立。
- 无流量时池不能直接掉到 0，除非显式允许 non-convex baseline。

State:

- 无持久状态。

Failure modes:

- 预测过低时，计划会退化成最小保活。
- 预测过高时，计划会撞上 `max_capacity`。
- 如果 baseline 设置成 on/off，会让“收益”看起来特别夸张，审查时要注意。

Counter-example:

- 如果 upstream 的连接池根本不需要保活，那么这个抽象就不合适。

### 2.2 `CanaryScheduler`

Public surface:

- `propose(current_share: float) -> float`
- `observe(current_share: float, proposed_share: float, observed_error_rate: float) -> CanaryStep`

Contract:

- 输入的 share 在 `[0, 1]` 里解释。
- `propose` 给出下一步灰度幅度。
- `observe` 返回 trust region、是否接受、预测误差与观测误差。
- trust region 必须保持在 `[eta_min, eta_max]` 内。

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

- `step(velocity, angular_velocity, dt) -> None`
- `ring_angle_rad -> float`
- `axis() -> np.ndarray`
- `distance_to(other) -> float`

Contract:

- `q` 始终按 unit quaternion 理解。
- `step` 之后姿态应保持在单位球附近。
- `distance_to` 应返回“位置 + 流形角距离”的组合量。

State:

- `position`
- `q`
- `omega`

Failure modes:

- 如果把周期量当欧氏量处理，会出现环上跳变。
- 如果积分类方法不守单位模，会有漂移。

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

- 每个 sensor 都提供 `h / H / R`。
- `step` 要能跳过缺失传感器。
- 输出的 covariance 应该还能被用来做告警。
- `step()["events"]` 必须报告缺失传感器等本地观测降级。

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

- `plan(share_from, share_to, dt=0.1) -> (t_grid, share_schedule, info)`

Contract:

- 产出的轨迹应是两阶段 bang-bang 形态。
- 最终 share 应接近目标 share。
- 时间长度应反映 rate cap。

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

Public surface:

- `step(state, target_position, target_velocity, target_axis_body=...) -> (thrusts, info)`

Contract:

- 输出是每个 thruster 的 magnitudes。
- 先算 PD/wrench，再做有界分配。
- thrust 不能越过 `T_min / T_max`。

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
| `PoolCapacityPlanner` | `tests/test_sre_control.py` | keep-alive floor and capacity cap |
| `CanaryScheduler` | `tests/test_sre_control.py` | trust region grows/shrinks correctly |
| `TopologyState` | `tests/test_sre_control.py` | quaternion norm stays stable |
| `SLOGuardrail` | `tests/test_sre_control.py` | cone projection works and local projection events are visible |
| `SignalFusion` | `tests/test_sre_control.py` | fusion converges and missing sensors are marked locally |
| `PredictiveAutoscaler` | `tests/test_sre_control.py` | forecast growth triggers scaling |
| `FastTrafficSwitcher` | `tests/test_sre_control.py` | target share is reached under rate limits |
| `WeightedLoadBalancer` | `tests/test_sre_control.py` | demand is matched without false saturation events |
| `SREControlStack` | `tests/test_contracts.py` | trace stays JSON-serializable and runtime degradation states are visible |

---

## 4. Refinement Notes

The most useful next refinement is not more prose. It is:

1. one contract test per public method,
2. one failure trace per module,
3. one counter-example per SRE mapping,
4. one explicit downgrade rule per stack stage.

That is how the abstraction becomes operationally sticky rather than merely elegant.
