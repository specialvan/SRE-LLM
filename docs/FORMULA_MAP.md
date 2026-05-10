# 公式 ↔ 代码逐行对照

本文把原文出现的每一条数学式定位到代码里的具体符号 / 函数。
“行号”指首次落地的位置；许多公式在多个模块里被复用，只列代表性出口。

---

## §1.1 交互意图图

| 公式 | 符号含义 | 代码出口 |
| --- | --- | --- |
| `G_I = (V_I, E_I)` | 时变加权有向图 | `auto_decide.graph.InteractionIntentGraph` |
| `V_I` 参与者节点 | car / ped / bike / static | `auto_decide.graph.Node` |
| `E_I` 边权 | 距离 × 方向 × 意图冲突 | `InteractionIntentGraph._edge_weight` |
| 意图冲突概率 `C(p_i, p_j)` | 文章里的"博弈权重" | `auto_decide.graph.intent_conflict` |

核心行：`graph.py` 中 `_edge_weight` 实现
`w_ij = exp(-d/D0) · heading_penalty · intent_conflict(p_i, p_j)`。

---

## §1.2 连续层

| 公式 | 代码出口 |
| --- | --- |
| `x = (x, v, a, μ)` 状态向量 | `auto_decide.types.State` |
| `ẋ = f(x, u)` 车辆动力学 | `auto_decide.dynamics.BicycleModel.f` |
| 轮胎附着约束 `|a| ≤ μ·g` | `BicycleModel.f` 中 jerk clamp + `step` 末端 clamp |
| 状态流形可行性 | `auto_decide.dynamics.Manifold.is_feasible` |
| "空洞" (void) | `Obstacle.signed_distance`（`CircleObstacle` / `RectObstacle`） |

---

## §1.3 非合作博弈中的动力学投影

| 公式 | 代码出口 |
| --- | --- |
| `ẋ = -∇Φ(x)` 受限梯度流 | `auto_decide.potential.PotentialField.flow_direction` |
| `Φ(x)` 势能函数 | `PotentialField.value` |
| `∇Φ(x)` 梯度 | `PotentialField.grad_xy`（数值差分） |
| 目标 / 障碍 / 规则三项分解 | `goal_potential` / `obstacle_potential` / `interaction_potential` |

---

## §2.1 李雅普诺夫稳定性

| 公式 | 代码出口 |
| --- | --- |
| `V(x)` 李雅普诺夫候选函数 | `auto_decide.lyapunov.QuadraticLyapunov.V` — 纯稳定性项 `½q_v(v-v*)² + ½q_a a²` |
| `dV(x)/dt ≤ 0` | `QuadraticLyapunov.dV_dt` + `StabilityMonitor.check` |
| 衰减率 / 告警指标 | `StabilityMonitor.metrics` |

> 代码里把"物理安全"（距离）与"控制稳定"（速度误差）解耦：
> - V 只管 **稳定性**；
> - 距离 / 车道等 **安全硬约束** 由 §3.2 的 CBF 承担。
> 这对应原文里把"李雅普诺夫 = 物理红线"与"CBF = 拓扑栅栏"分开的说法。

> 数值实现上，`dV_dt` 使用前向一步有限差：
> `dV/dt ≈ (V(step(x,u,dt)) - V(x)) / dt`。

---

## §2.2 可达集

| 公式 | 代码出口 |
| --- | --- |
| `R(x₀, T)` 前向可达集 | `auto_decide.reachable.ReachableSet.sample` |
| `hull(R)` 凸包近似 | `ReachableSet.hull`（`scipy.spatial.ConvexHull`） |
| "逻辑死区" 判定 | `auto_decide.reachable.DeadZoneDetector.check` |

---

## §2.3 非完全信息博弈

| 公式 | 代码出口 |
| --- | --- |
| 意图置信度 `p(intent)` | `auto_decide.game.BeliefState` |
| 信息熵 | `BeliefState.entropy` / `uncertainty` |
| 安全缓冲 `buffer_min` | `auto_decide.game.WorstCaseGame.safe_buffer` |
| 多车最坏情况聚合 | `WorstCaseGame.aggregate_buffer` |

---

## §3.1 控制不变集生成算子

| 公式 | 代码出口 |
| --- | --- |
| `u_safe = T_inv(u_nn)` | `auto_decide.invariant.ControlInvariantOperator.apply` |
| `dV/dt ≤ -γV` 指数衰减版 | `apply` 内迭代松弛 |
| 不可行时回退刹停 | `apply` 末端 `Control(0, -jerk_max)` |

---

## §3.2 控制屏障函数

| 公式 | 代码出口 |
| --- | --- |
| `h(x) ≥ 0` 安全集 | `auto_decide.cbf.BarrierFunction` 协议 |
| `ḣ(x, u) + α h(x) ≥ 0` | `CBFQPFilter._objective` 约束 |
| 纯几何距离屏障（相对度 2） | `DistanceBarrier` |
| 含制动距离的屏障（相对度 1，μ-自适应） | `BrakingDistanceBarrier` |
| 速度屏障 | `SpeedBarrier` |
| 搜索空间折叠 | `CBFQPFilter.filter` — 网格粗筛 + 精化 |

> 实现备注：几何 `DistanceBarrier` 对 jerk 是相对度 2，仅靠它在 jerk 驱动系统里反应
> 不够快，因此 `make_obstacle_barriers` 同时挂一个 `BrakingDistanceBarrier`。后者把
> 停车距离 `v²/(2·a_brake(μ))` 与反应时间 `v·τ` 都算进 `h`，对 jerk 相对度 1，能
> 被 QP 即时矫正。

---

## §3.3 定量对比

| 文章论点 | 代码对应 |
| --- | --- |
| OOD 场景下 NN 输出违反物理常识 | `examples.compare_e2e_vs_structural._pure_e2e_step` |
| 结构化链路保持安全 | `StructuralPlanner.run` + CBF + `T_inv` |
| 碰撞率降低 2~3 个数量级 | `summarise(...)` 报告碰撞率 |

---

## §4 结语装配

| 文章主张 | 代码对应 |
| --- | --- |
| 给 AI 戴上物理的枷锁 | `StructuralPlanner.step` 的三段流水：`nominal → T_inv → step` |
| 每一次动作都是动力学演化步 | 任何 NN 输出必须先过 `T_inv.apply` |
| 运行在物理定律所划定的安全河床 | `Manifold.is_feasible` 在测试里被断言 |
