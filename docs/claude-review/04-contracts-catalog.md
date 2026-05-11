# Contracts Catalog

> 9 个核心模块 + trace 的完整 **pre / post / invariant** 合约，格式统一。
> 用途：接口变更评审（"这个 PR 要动哪个模块？先看它的契约"）。

## 约定

每个合约用以下字段表达：

- **INPUTS**：前置参数与其类型/量纲/值域。
- **OUTPUTS**：返回值与其类型/量纲。
- **PRE**：调用前必须成立的条件（未满足是调用方的 bug）。
- **POST**：返回后保证成立的条件（未满足是被调方的 bug）。
- **INVARIANTS**：在整个生命周期保持的不变式（见 [03-invariants-catalog.md](./03-invariants-catalog.md)）。
- **SIDE EFFECTS**：对外可见的副作用（trace 写入、内部状态修改等）。
- **RAISES**：合法异常（不合法的入参）。

---

## Module · `auto_decide.graph.InteractionIntentGraph`

### `add_node(node)`
- **IN**：`node: Node`（`node_id` 非空，`position`/`velocity` 形状 (2,)）
- **OUT**：None
- **PRE**：`node.node_id` 在图中唯一
- **POST**：`node in self.nodes` 且 `_edges` 暂不更新
- **SIDE**：修改 `_nodes` dict

### `update(dt=0.0)`
- **IN**：`dt` 形式参数，当前实现忽略
- **OUT**：None
- **POST**：`_edges` 完全重建，只含 `w ≥ EPS` 的边
- **INV**：[INV-G11](./03-invariants-catalog.md#inv-g11)、[INV-M-GRAPH-1](./03-invariants-catalog.md#inv-m-graph-1)
- **复杂度**：O(n²)
- **SIDE**：`_edges` 全量替换

### `to_adjacency()`
- **OUT**：`np.ndarray(shape=(n, n))`，权重按 `_nodes` 插入序排列
- **POST**：`A[i,i] == 0`、`A[i,j] ∈ [0, 1]`

---

## Module · `auto_decide.dynamics.BicycleModel`

### `f(state, u) → np.ndarray(6,)`
- **IN**：`state: State`，`u: Control`
- **OUT**：`dx/dt`，形状 (6,)
- **PRE**：`state.mu > 0`
- **POST**：
  - `dx_dt[5] == 0.0`（μ 不自演，INV-M-DYN-2）
  - 若 `|state.a| ≥ state.mu*g`，则 jerk 在 f 内被 clamp（[INV-G3](./03-invariants-catalog.md#inv-g3)）
- **INV**：[INV-M-DYN-1](./03-invariants-catalog.md#inv-m-dyn-1)

### `step(state, u, dt) → State`
- **IN**：`dt ∈ (0, 0.1]`（超过 0.1 会让 RK4 精度下降，不强制但推荐）
- **OUT**：新 `State`
- **POST**：
  - `|out.a| ≤ out.mu * g`（INV-G3）
  - `0 ≤ out.v ≤ v_max`
  - `out.mu == state.mu`
- **复杂度**：4 次 f 调用 + 末端 clamp
- **典型时延**：< 0.1 ms

### `rollout(state, controls, dt) → List[State]`
- **OUT**：`len = len(controls) + 1`（包含初始状态）

---

## Module · `auto_decide.dynamics.Manifold`

### `is_feasible(state) → bool`
- **POST**：返回 `True` 当且仅当 state 同时满足 (1) `v ∈ [0, v_max*1.05]`（含容差）、(2) `|a| ≤ μ*g + 1e-3`、(3) 所有障碍的 `signed_distance > 0`

### `min_distance(state) → float`
- **POST**：若无障碍返回 `inf`；否则返回最小 signed distance
- **INV**：单调：离最近障碍越近返回值越小

---

## Module · `auto_decide.potential.PotentialField`

### `value(state, manifold, graph=None, ego_id="ego") → float`
- **OUT**：`Φ(x) ≥ 0` 的浮点数
- **POST**：有限值（不含 inf/NaN），由 `max(d, 0.05)` 下限保证
- **INV**：[INV-M-POT-1](./03-invariants-catalog.md#inv-m-pot-1)

### `grad_xy(state, manifold, graph=None, ego_id="ego", eps=1e-3) → np.ndarray(2,)`
- **IN**：`eps` 数值差分步长，默认 1e-3 m
- **OUT**：`∂Φ/∂(px, py)` 的数值差分估计
- **POST**：形状 (2,)，无 NaN
- **复杂度**：两次 `value` 调用

### `flow_direction(...) → np.ndarray(2,)`
- **OUT**：单位向量 `-∇Φ / ‖∇Φ‖` 或零向量（当 ‖∇Φ‖ < 1e-6）

---

## Module · `auto_decide.lyapunov.QuadraticLyapunov`

### `V(state, target_speed) → float`
- **OUT**：`½·q_v·(v - v*)²`，非负
- **INV**：[INV-G9](./03-invariants-catalog.md#inv-g9)（纯速度项）

### `V_full(state, manifold, target_speed) → float`
- **OUT**：等同 `V`（manifold 参数仅保持 API 兼容）

### `dV_dt(state, u, dynamics, manifold, target_speed, dt=0.01) → float`
- **IN**：`dt` 有限差步长，默认 0.01 s
- **OUT**：$(V_{t+dt} - V_t) / dt$ 的数值估计
- **POST**：有限值
- **SIDE**：调用 `dynamics.step` 一次（合法的 INV-G2 内部例外）

---

## Module · `auto_decide.reachable.ReachableSet`

### `sample(state0, rng=None) → np.ndarray(N, 2)`
- **IN**：`rng` 可选 numpy Generator
- **OUT**：N 个终点的 (px, py) 坐标
- **POST**：形状 `(n_samples, 2)`
- **复杂度**：`N × (T/dt)` 次 `dynamics.step`（典型 200×20 = 4000）
- **SIDE**：设置 `self._endpoints`

### `hull(state0=None) → (endpoints, hull_vertices)`
- **POST**：`hull_vertices` 是 `endpoints` 的凸包顶点（`scipy.spatial.ConvexHull`）
- **FALLBACK**：若 `n < 3` 或 `ConvexHull` 失败，返回所有点作为 hull

### `in_reachable(state0, target) → bool`
- **OUT**：ray-casting 点在多边形中测试

---

## Module · `auto_decide.reachable.DeadZoneDetector`

### `check(state, threat_position, threat_velocity) → (bool, float)`
- **OUT**：`(in_dead_zone, min_clearance)`
- **POST**：`in_dead_zone == True` 当且仅当最坏情况刹停下仍与匀速威胁相撞
- **假设**：ego 全力刹（`jerk = -jerk_max`），威胁匀速（见 E-22）

---

## Module · `auto_decide.game.WorstCaseGame`

### `safe_buffer(rel_speed, belief) → float`
- **OUT**：缓冲距离（米）
- **POST**：
  - 单调：`rel_speed ↑ ⇒ buffer ↑`
  - 单调：`belief.entropy ↑ ⇒ buffer ↑`
  - 下界：`buffer ≥ base_buffer`

### `aggregate_buffer(rel_speeds, beliefs) → float`
- **OUT**：所有对手的 max buffer（最坏情况）
- **POST**：若 lists 为空，返回 `base_buffer`

---

## Module · `auto_decide.cbf.CBFQPFilter`

### `filter(state, u_nom, coarse=11, fine=21) → (Control, dict)`
- **IN**：`u_nom: Control`
- **OUT**：
  - `u_safe: Control`，满足 `|steer| ≤ max_steer`, `|jerk| ≤ jerk_max`
  - `info: dict`，键包含 `{"status", "slack", "violations"}`
- **PRE**：至少一条 barrier 返回有限值
- **POST**：
  - `info["status"] ∈ {"nom_ok", "qp_ok", "fallback_brake"}`（[INV-G12](./03-invariants-catalog.md#inv-g12)）
  - 若 `status == "fallback_brake"`，则 `u_safe == Control(0, -jerk_max)`
- **不抛异常**：[INV-M-CBF-1](./03-invariants-catalog.md#inv-m-cbf-1)
- **复杂度**：`O((coarse² + fine²) × n_barriers)`
- **典型时延**：3~6 ms

---

## Module · `auto_decide.invariant.ControlInvariantOperator`

### `apply(state, u_nn) → (Control, dict)`
- **IN**：`u_nn: Control`
- **OUT**：
  - `u_safe: Control`
  - `info: dict`，键 `{"cbf", "V", "dV_dt", "status"}`
- **POST**：
  - `info["status"] ∈ {"stable", "relaxed_exp", "relaxed", "non_increasing", "emergency_brake"}`（INV-G12）
  - 若 `status ∈ {"stable", "relaxed_exp", "relaxed", "non_increasing"}`：`info["dV_dt"] ≤ tol`
  - 若 `status == "emergency_brake"`：`u_safe == Control(0, -jerk_max)`（INV-M-CBF-2 同构）
- **终止性**：[INV-G7](./03-invariants-catalog.md#inv-g7)，最多 `relax_steps + 1` 次评估
- **禁止组合**：[INV-G13](./03-invariants-catalog.md#inv-g13) 的 4 种非法 (status, cbf_status) 对

---

## Module · `auto_decide.planner.StructuralPlanner`

### `step(state, graph, dt=0.1, step_index=None) → (State, Control, dict)`
- **IN**：
  - `state: State`
  - `graph: InteractionIntentGraph`（已 `update()` 过的）
  - `dt ∈ (0, 0.1]`
  - `step_index: Optional[int]`
- **OUT**：
  - `next_state`（Lyapunov+CBF 约束下演化的下一状态）
  - `u_safe`
  - `trace: dict`（16 字段，[INV-G5](./03-invariants-catalog.md#inv-g5)）
- **PRE**：`self.nominal` 已初始化（由 `__post_init__` 保证）
- **POST**：
  - [INV-G1](./03-invariants-catalog.md#inv-g1) · [INV-G2](./03-invariants-catalog.md#inv-g2) · [INV-G5](./03-invariants-catalog.md#inv-g5) 全部成立
  - trace 字段完整且 JSON-safe（[INV-G6](./03-invariants-catalog.md#inv-g6)）
- **SIDE**：无（step 是无副作用的；副作用在 `run` 的 trace 写入）

### `run(initial, graph, horizon_steps=80, dt=0.1, trace_path=None) → (states, controls, traces)`
- **POST**：
  - `len(states) == horizon_steps + 1`
  - `len(controls) == len(traces) == horizon_steps`
  - 若 `trace_path` 给定，文件包含 `horizon_steps` 行 JSONL
- **SIDE**：若 `trace_path`，追加写入（不会先清空，调用方需注意）
- **INV**：[INV-M-PLAN-2](./03-invariants-catalog.md#inv-m-plan-2)

---

## Cross-cutting · `auto_decide.trace`

### `build_trace_record(*, step_index, dt, state, next_state, u_nn, u_safe, info, min_dist) → dict`
- **IN**（全 keyword-only）：
  - `step_index: Optional[int]`
  - `dt: float`
  - `state, next_state: State`
  - `u_nn, u_safe: Control`
  - `info: Mapping[str, Any]`（包含 `{"cbf", "V", "dV_dt", "status"}` 四个键）
  - `min_dist: float`
- **OUT**：`dict`，16 个字段，严格 JSON-safe
- **POST**：
  - `output["schema_version"] == "1.0"`
  - `all(isinstance(x, (int, float, str, list, dict, type(None), bool)) for ...)`
  - inf/NaN 已清洗为 None
- **INV**：[INV-G5](./03-invariants-catalog.md#inv-g5) · [INV-G6](./03-invariants-catalog.md#inv-g6) · [INV-M-TRACE-2](./03-invariants-catalog.md#inv-m-trace-2)

---

## 契约变更规则

### 何时可以加字段？
- trace 里加字段：只要不删除/改现有字段的语义，`schema_version` 不用 bump。
- planner.step 的 trace 里加字段：同上。
- CBF / Lyapunov 的 status 加一个新值：必须在 [INV-G12](./03-invariants-catalog.md#inv-g12) 里添加，并在 [01-findings.md](./01-findings.md) 里找到相应 finding 跟进。

### 何时必须 bump schema_version？
- 删字段；
- 改字段语义（单位变、类型变）；
- `status` 值的删除。

### 何时触发整体回归？
- 任何模块级契约的 POST 变更 → 依赖该模块的测试 / 下游需要回归。
- 跨层方程修改（见 [02-architecture-deep.html §6](./02-architecture-deep.html#eq-arch)）。

---

## PR 自检表

Codex 在提交 PR 前按这个表走一遍：

- [ ] 我动了哪些模块？列出来。
- [ ] 对每个动到的模块：contract 的 IN / OUT / PRE / POST / INV 是否改变？
- [ ] 如果改变了：是加字段还是改语义？是加值还是删值？
- [ ] schema_version 需要 bump 吗？
- [ ] 相关 invariant 是否仍然成立？
- [ ] 测试是否覆盖？新增测试或扩充既有？
- [ ] README / architecture / handoff / deep-dive / trace-schema / benchmark-metrics 是否需要同步？
