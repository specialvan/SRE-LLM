# PR 级功能需求清单

把文章中的叙述性内容逐项翻译成可独立交付的 PR。
每个 PR 都有：背景、验收标准（DoD）、涉及文件、对应论文原文定位。
颗粒度按"1 个 PR 1~2 天、不超过 400 行代码"来切分。

> 命名规约：`PR-<section>-<seq>: <短标题>`
> 例：`PR-1.1-01: 交互意图图数据结构`

---

## Epic 1 · 核心结构：时变非线性流形上的受限梯度流

### PR-1.1-01 · 交互意图图数据结构 `G_I = (V_I, E_I)`
- **背景**：论文 1.1 节，把交通抽象为带意图的加权有向图，节点是交通参与者，边权描述意图冲突强度。
- **范围**：
  - `Node` 数据类：id、类型（car/ped/bike/static）、位姿、速度、意图分布。
  - `Edge` 数据类：方向、权重 w∈[0,1]、意图冲突类型。
  - `InteractionIntentGraph` 容器：`add_node / add_edge / neighbors / to_adjacency`。
  - 时变更新：`update(dt)` 根据几何距离 + 速度矢量夹角刷新边权。
- **DoD**：
  - `tests/test_graph.py` 覆盖"距离近→权重大、距离远→权重趋零、方向无关→权重趋零"。
  - 能在一帧 <1 ms 内处理 100 个 agent。
- **文件**：`auto_decide/graph.py`、`tests/test_graph.py`。

### PR-1.1-02 · 意图分布与博弈权重耦合
- **背景**：论文强调图里每条边不仅有方向还有"意图指向"，是博弈性质的。
- **范围**：边权 `w = g(distance) · cos_penalty · intent_conflict(p_i, p_j)`；提供 `IntentPrior` 接口，默认均匀分布，可由上游感知注入概率。
- **DoD**：同一对车，意图冲突概率从 0→1 时边权单调上升；API 文档齐全。
- **文件**：`auto_decide/graph.py` 新增 `IntentPrior`、`intent_conflict()`。

### PR-1.2-01 · 车辆动力学连续层 `ẋ = f(x, u)`
- **背景**：论文 1.2 节，定义状态 `x=(x, v, a, μ)` 与动力学流形。
- **范围**：
  - `State` 数据类：`[px, py, psi, v, a, mu]`。
  - 自行车模型 `BicycleModel.f(state, u)`，`u = [steer, jerk]`。
  - 轮胎附着约束 `|a| ≤ μ·g`。
  - `step(state, u, dt)` 使用 RK4 积分。
- **DoD**：
  - 纯直线恒速输入下 `dt` 归零误差 ≤1e-6。
  - 超过 μ·g 时 `f` 会把加速度 clamp 并打日志。
- **文件**：`auto_decide/dynamics.py`、`tests/test_dynamics.py`。

### PR-1.2-02 · 非欧状态流形与不可行"空洞"
- **背景**：行人/障碍物在状态空间中形成 void。
- **范围**：`Obstacle` 基类（圆形、矩形、车道线）；`Manifold.is_feasible(state)` 返回可行性。
- **DoD**：障碍物内部点不可行；车道外侧不可行。
- **文件**：`auto_decide/dynamics.py`（`Obstacle`, `Manifold`）。

### PR-1.3-01 · 势能场 Φ 与受限梯度流 `ẋ = -∇Φ(x)`
- **背景**：论文 1.3 节将车辆行为视为势能梯度下降，并强调是"受限"梯度流。
- **范围**：
  - `PotentialField` 组件：目标项 + 安全项（与障碍、与他车）+ 规则项（车道、限速）。
  - `grad(state, graph)` 用数值梯度或解析梯度返回 `∇Φ`。
  - `constrained_flow(state, graph, manifold)` 把梯度方向投影到流形切空间。
- **DoD**：
  - 给定目标点，空旷场景梯度指向目标；靠近障碍时梯度被推开。
  - 切空间投影后 `f·n ≈ 0`（n 为约束法向）。
- **文件**：`auto_decide/potential.py`。

---

## Epic 2 · 数学约束边界：Lyapunov + 可达集 + 博弈

### PR-2.1-01 · 李雅普诺夫函数与稳定性监视 `dV/dt ≤ 0`
- **背景**：论文 2.1 节，Lyapunov 构成系统"物理红线"。
- **范围**：
  - `LyapunovFn` 协议：`V(state)`、`dV_dt(state, u, dynamics)`。
  - 默认实现：`V = ½·e_vᵀ·Q·e_v + k·(1/d_min)²`，e_v 为跟随速度误差，d_min 为与最近障碍距离。
  - `StabilityMonitor.check(state, u)` 返回 `(is_stable, margin)`。
- **DoD**：
  - 车辆靠近障碍时 V 单调上升；远离时下降。
  - 当 `dV/dt>0` 时 monitor 返回 `is_stable=False`。
- **文件**：`auto_decide/lyapunov.py`、`tests/test_lyapunov.py`。

### PR-2.1-02 · Lyapunov 衰减率告警
- **背景**：工业级要求有阈值告警。
- **范围**：新增 `decay_rate(state, u)`；暴露 Prometheus 风格指标接口 `metrics()`。
- **DoD**：在 ci 里 dump 一份 JSON metrics；阈值可配置。

### PR-2.2-01 · 前向可达集 `R(x₀, T)`
- **背景**：论文 2.2 节定义可达集，是"逻辑死区"判定的基础。
- **范围**：
  - `ReachableSet.sample(state0, T, n)` 采样控制序列并前向积分。
  - `ReachableSet.hull()` 返回凸包近似（`scipy.spatial.ConvexHull`）。
  - `in_reachable(state0, target, T)` 判断 target 是否落在可达集里。
- **DoD**：
  - 给定 `a_max / steer_max`，随 T 增大可达集面积单调增大。
  - 单次调用 ≤ 5 ms（n=200, T=2 s, dt=0.1 s）。
- **文件**：`auto_decide/reachable.py`。

### PR-2.2-02 · 逻辑死区检测
- **背景**：外部不确定性超出可达集即"死区"。
- **范围**：`DeadZoneDetector.check(state, threats)` 返回布尔 + 最小可规避裕度。
- **DoD**：前车急刹的场景能正确识别死区。

### PR-2.3-01 · 非完全信息博弈与纳什均衡近似
- **背景**：论文 2.3 节强调信息不完全，需要安全冗余。
- **范围**：
  - `BeliefState`：对每个他车意图维护概率分布。
  - `WorstCaseGame.safe_action(ego, others, beliefs)`：按最坏意图折算预期代价。
  - 输出"推荐最小缓冲距离" `buffer_min`。
- **DoD**：置信度均匀时缓冲距离最大；置信度集中在"对方让行"时距离减小。
- **文件**：`auto_decide/game.py`。

---

## Epic 3 · 优化空间的结构重构

### PR-3.1-01 · 控制不变集生成算子 `T_inv`
- **背景**：论文 3.1 节最核心算子——`u_safe = T_inv(u_nn)`。
- **范围**：
  - `ControlInvariantOperator`：包装 Lyapunov 判据 + 一个回退控制器（LQR / 保守制动）。
  - `apply(state, u_nn) -> u_safe`：若 `dV/dt(u_nn) > 0` 则求解
    `min‖u - u_nn‖²  s.t.  dV/dt ≤ -γV`。
  - 用二次规划求解，若 QP 不可行则降级到刹停。
- **DoD**：
  - 在"NN 输出违反稳定性"的合成场景里能够被矫正。
  - 相较原 NN 输出的能量差 ≤ 预算阈值。
- **文件**：`auto_decide/invariant.py`。

### PR-3.2-01 · 控制屏障函数 h(x) 与 CBF-QP
- **背景**：论文 3.2 节：`h(x)≥0` + `ḣ+αh≥0`。
- **范围**：
  - `BarrierFunction` 协议：`h(x)`、`grad_h(x)`。
  - 常用实现：
    - `DistanceBarrier`（与障碍距离 - 安全距离） — 纯几何，适合静态边界；
    - `BrakingDistanceBarrier`（距离 - 速度·τ - v²/(2·a_brake(μ))） — 考虑制动距离与 μ，
      对 jerk 是**相对度 1**，能及时刹停；
    - `LaneBarrier`（距车道线距离）。
  - `CBFQPFilter.filter(state, u_nom)` 求解
    `min‖u - u_nom‖²  s.t.  (∂h/∂x)·f(x,u) + αh ≥ 0  (对每个屏障)`。
  - ``h_dot`` 使用物理有意义的前瞻 `h_dot_horizon=0.1s`（jerk 驱动系统的必要前瞻）。
- **DoD**：
  - 加速度方向的 u_nom 若会撞上障碍，被矫正为减速。
  - QP 规模与屏障数 O(n)，200 帧耗时 <50 ms。
- **文件**：`auto_decide/cbf.py`、`tests/test_cbf.py`。

### PR-3.2-02 · 搜索空间折叠
- **背景**：多屏障组合裁剪状态空间。
- **范围**：`FoldedSearchSpace`：接受屏障列表，返回"是否在安全流形内"的快速判定；提供采样器 `sample_feasible(n)`。
- **DoD**：采样效率至少比拒绝采样快 3 倍。

### PR-3.3-01 · 端到端 vs 结构化基准对比
- **背景**：论文 3.3 节声称碰撞规避率可提升 2~3 个数量级。
- **范围**：`examples/compare_e2e_vs_structural.py`：
  - 构造 N 次随机长尾场景（雨天摩擦降低、突发行人、他车急刹）。
  - 两条链路：`pure_nn_pipeline` vs `structural_pipeline`。
  - 打印碰撞率、舒适度、规划耗时。
- **DoD**：结构化管线碰撞率明显低于纯 NN（模拟数据中）；输出 CSV 报告。

---

## Epic 4 · 端到端装配："给 AI 戴上物理的枷锁"

### PR-4-01 · 决策 Planner 主循环
- **背景**：结语节——把所有模块装配成一条运行链路。
- **范围**：
  - `StructuralPlanner.step(obs)`：
    1. 更新 `InteractionIntentGraph`。
    2. 从神经候选策略 `u_nn` 开始（可注入简单 MPC 或学习到的策略）。
    3. `CBFQPFilter.filter` → `ControlInvariantOperator.apply` → Lyapunov 监视 → 若失败则回退刹停。
  - 可观测性：每步输出 `trace` 字典，便于离线分析。
- **DoD**：`examples/demo_intersection.py` 能稳定完成一次十字路口左转避让。
- **文件**：`auto_decide/planner.py`、`examples/demo_intersection.py`。

### PR-4-02 · 可观测性与日志
- **背景**：工业级系统需要可审计链路。
- **范围**：结构化日志（JSON Lines），包含 `V(x), dV/dt, h_min, in_reachable, u_nn, u_safe, qp_status`。
- **DoD**：一次 demo 跑完产出 `trace.jsonl`，可被 pandas 直接读入。

### PR-4-03 · 单元测试 & CI
- **背景**：把上述约束固化为 guardrail。
- **范围**：
  - 每个 Epic 至少一组 pytest。
  - GitHub Actions 配置（可选）。
- **DoD**：`pytest -q` 绿灯，覆盖率 ≥ 70%。

---

## 附录 · PR 与论文段落的双向追溯

| PR 编号 | 论文定位 | 关键词 |
| --- | --- | --- |
| PR-1.1-01/02 | §1.1 离散层：交互意图图 | `G_I`, `V_I`, `E_I` |
| PR-1.2-01/02 | §1.2 连续层：高维非欧相空间 | `x=(x,v,a,μ)`, `ẋ=f(x,u)` |
| PR-1.3-01 | §1.3 非合作博弈中的动力学投影 | `ẋ = -∇Φ(x)` |
| PR-2.1-01/02 | §2.1 李雅普诺夫稳定性判据 | `dV/dt ≤ 0` |
| PR-2.2-01/02 | §2.2 可达集测度限制 | `R(x₀, T)` |
| PR-2.3-01 | §2.3 非完全信息博弈纳什均衡极限 | 安全冗余 |
| PR-3.1-01 | §3.1 控制不变集生成算子 | `u_safe = T_inv(u_nn)` |
| PR-3.2-01/02 | §3.2 屏障函数 & 搜索空间折叠 | `ḣ + αh ≥ 0` |
| PR-3.3-01 | §3.3 定量对比与安全性涌现 | benchmark |
| PR-4-01/02/03 | §4 结语 | 装配 & CI |
