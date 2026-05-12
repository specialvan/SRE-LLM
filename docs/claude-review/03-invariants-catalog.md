# Invariants Catalog

> 完整的系统级与模块级不变式目录。每条有：ID / 陈述 / 守护者 / 证明/理由 / 测试锚点 / 违反后果。
> 这是 Codex 每次 PR 的 guardrail 清单——修改前先扫一遍。

## 使用方式

- **PR 前自检**：扫 "守护者" 列，如果你的改动落在任何一行的守护者范围，必须在 PR 描述里解释为什么不破坏该条不变式。
- **Review 时**：按 ID 逐条打勾。
- **CI**：标注 `AUTO` 的不变式可以/应该写成自动化断言（见 [07-codex-directives.md](./07-codex-directives.md#auto-asserts)）。

---

## 全局不变式（INV-G*）

### INV-G1 · 动力学可行性
**陈述**：对于任何 <code>state = planner.step(...)</code> 返回的状态 `x`：
```
manifold.min_distance(x) ≥ 0
```
**守护者**：`cbf.py` + `invariant.py` 联合。
**理由**：CBF 过滤器把会进入障碍的命令剪掉；T_inv 的 fallback 永远是刹停，不会越过当前位置的障碍边界。
**测试**：`test_planner.py::test_intersection_left_turn_no_collision` · `test_emergency_brake_when_obstacle_ahead` ✅
**违反后果**：发生碰撞——P0 回退整个 PR。
**标注**：`AUTO`（可 CI 断言）

### INV-G2 · 唯一执行入口
**陈述**：所有 `u_safe` 必须出自 `StructuralPlanner.step()`；`dynamics.step` 不得被 planner 外的业务路径调用。
**守护者**：代码拓扑 + 静态 grep。
**合法例外**（记录在 [01-findings.md](./01-findings.md#f-p2-06)）：
- `cbf.py` / `lyapunov.py` 内部用 `dynamics.step` 做 `h_dot` / `dV_dt` 的有限差分评估；
- `examples/compare_e2e_vs_structural.py::_pure_e2e_step` 作为对比基线刻意绕过。
**测试**：`scripts/check_invariants.py` + `tests/test_invariants.py::test_invariant_script_passes` ✅（AI-11）。
**违反后果**：硬约束被绕过——P0 回退 PR。
**标注**：`AUTO`（grep 脚本）

### INV-G3 · 物理约束双层 clamp
**陈述**：在任何时刻：
```
|state.a| ≤ state.mu · g
0 ≤ state.v ≤ v_max
|u.steer| ≤ max_steer
|u.jerk| ≤ jerk_max
```
**守护者**：`BicycleModel.f` 内的 jerk clamp + `BicycleModel.step` 末端 clamp。
**测试**：`test_dynamics.py::test_friction_envelope_clamped` ✅
**违反后果**：轨迹偏出物理包络——轨迹不可复现。
**标注**：`AUTO`

### INV-G4 · Fallback 可行性
**陈述**：`Control(steer=0, jerk=-params.jerk_max)` 在任何 `state` 下都满足：
1. `|u.steer| ≤ max_steer` ✅（0 总成立）
2. `|u.jerk| ≤ jerk_max` ✅（按定义）
3. 作用到 dynamics.step 后仍满足 INV-G3
**守护者**：执行器参数定义 + T_inv.apply 末端分支。
**测试**：无独立测试（属于类型系统保证）。
**违反后果**：T_inv 无终止出口——P0。
**标注**：`AUTO`（静态断言 `VehicleParams`）

### INV-G5 · trace 契约向后兼容
**陈述**：`trace.py` 输出的 JSON 对象必须包含以下字段（v1.x，当前 v1.1）：
```
schema_version, step, t, dt, state, next_state,
u_nn, u_safe, min_dist, V, dV_dt, status, cbf_status,
cbf_slack, cbf_violations, cbf
```
新字段可以追加，已有字段不得删除或改语义。
**守护者**：`auto_decide/trace.py::build_trace_record`。
**测试**：`test_trace.py::test_trace_record_is_json_safe_and_versioned` ✅
**违反后果**：下游 review / benchmark 工具链崩。
**标注**：`AUTO`（JSON Schema 验证）

### INV-G6 · trace 严格 JSON 可解析
**陈述**：`trace.jsonl` 每行都能被 `json.loads(line, allow_nan=False)` 成功解析；`inf`/`NaN` 必须清洗为 `null`。
**守护者**：`trace.py::_jsonable`。
**测试**：`test_trace.py` ✅
**违反后果**：trace 回放/分析管道崩。
**标注**：`AUTO`

### INV-G7 · T_inv 有限步终止
**陈述**：`ControlInvariantOperator.apply` 最多评估 `relax_steps + 1` 次 dV/dt（当前 9 次）后必然返回。
**守护者**：`invariant.py::apply` 的 for 循环边界 + fallback 分支。
**证明草图**：jerk 单调递减，最多 N 步到 `-jerk_max`；此时 fallback 总可行（INV-G4）。
**测试**：隐含在集成测试里（未独立）—— 建议补（AI-12）。
**违反后果**：单帧时延不可控。
**标注**：`MANUAL + AUTO`（加一个 "步数 ≤ 9" 的断言）

### INV-G8 · 硬约束不软化
**陈述**：CBF 条件 `ḣ + αh ≥ 0` 和 Lyapunov 条件 `dV/dt ≤ 0` 以**不等式**进入数值搜索，不作为损失函数的正则项。
**守护者**：`cbf.CBFQPFilter._objective` + `invariant.ControlInvariantOperator.apply`。
**测试**：代码 review（无自动测试）。
**违反后果**：失去前向不变性证明，系统可能会"平均安全但存在违规"。
**标注**：`MANUAL`

### INV-G9 · Lyapunov V 纯稳定性语义
**陈述**：`QuadraticLyapunov.V(x)` 只含速度跟踪项 `½·q_v·(v-v*)²`，不含距离项。
**守护者**：`lyapunov.py::QuadraticLyapunov`。
**理由**：见 [equations-digest.html E-17](../equations-digest.html#e17)，把距离项塞进 V 会让目标前进触发 `dV/dt > 0`。
**测试**：`test_lyapunov.py::test_V_monotonic_with_velocity_error` 间接守护。
**违反后果**：demo 连刹不前（已踩过的坑）。
**标注**：`MANUAL`

### INV-G10 · VehicleParams 只读
**陈述**：`VehicleParams` 是 `@dataclass(frozen=True)`；任何模块不得 mutate 同一个实例。
**守护者**：Python `frozen=True`。
**测试**：类型系统（`FrozenInstanceError`）。
**违反后果**：多车型场景下状态污染。
**标注**：`AUTO`（类型系统自动）

### INV-G11 · 意图图每帧重建
**陈述**：`InteractionIntentGraph.update()` 在调用时先 `_edges.clear()` 再重建，不做增量更新。
**守护者**：`graph.py::update`。
**理由**：避免陈旧边（已离场 agent 的边）留存。
**测试**：`test_graph.py` 间接守护。
**违反后果**：下游势能/博弈项被陈旧边影响。
**标注**：`MANUAL`

### INV-G12 · status 枚举封闭
**陈述**：`trace["status"]` ∈ {stable, relaxed_exp, relaxed, non_increasing, best_effort, emergency_brake}；`trace["cbf_status"]` ∈ {nom_ok, qp_ok, fallback_brake}。
**守护者**：`auto_decide.trace.PLANNER_STATUS_VALUES` / `CBF_STATUS_VALUES` + `invariant.py` / `cbf.py` 返回值。
**测试**：`test_trace.py::test_planner_status_enum_contents`、`test_trace.py::test_cbf_status_enum_contents`、`strict=True` trace 校验 ✅（AI-03b）。
**违反后果**：下游 metric 聚合统计漏类。
**标注**：`AUTO`（新加）

### INV-G13 · CBF/Lyapunov 状态组合无矛盾
**陈述**：不允许出现以下 (status, cbf_status) 组合：
- (stable, fallback_brake)
- (relaxed_exp, fallback_brake)
- (relaxed, fallback_brake)
- (non_increasing, fallback_brake)
- (best_effort, fallback_brake)

原因：CBF 退化为 fallback 时，T_inv 不应再标成稳定、松弛成功或 `best_effort`——因为此时用的是 `Control(0, -j_max)` 而不是名义轨迹上的命令。
**守护者**：`invariant.py::apply` 的返回逻辑。
**测试**：`tests/test_planner.py::test_no_forbidden_tinv_cbf_status_combinations` ✅（AI-12）。
**违反后果**：trace 统计逻辑矛盾，reviewer 会质疑。
**标注**：`AUTO`（新加）

---

## 模块级不变式（INV-M*）

### INV-M-GRAPH-1 · 图权重有界
**陈述**：每条边 `w_ij ∈ [0, 1]`。
**守护者**：`_edge_weight` 的乘积形式（每项 ∈ [0,1]）。
**测试**：`test_graph.py`（隐含）。

### INV-M-GRAPH-2 · 图剪枝一致
**陈述**：`w_ij < EPS (1e-3)` 的边不得出现在 `_edges` 字典。
**守护者**：`update()` 的 `if w >= self.EPS` 分支。
**测试**：`tests/test_graph.py::test_edges_respect_eps_cutoff` ✅（AI-13）。

### INV-M-DYN-1 · f 输出形状
**陈述**：`BicycleModel.f(state, u)` 返回 `np.ndarray(shape=(6,), dtype=float)`。
**守护者**：返回语句。
**测试**：隐含在 `test_dynamics.py`。

### INV-M-DYN-2 · μ 不自行演化
**陈述**：`f(state, u)[5] == 0.0`；`state.mu` 只能由外部感知写入。
**守护者**：`f` 的 `mu_dot = 0`。
**违反后果**：与感知上游不一致。

### INV-M-POT-1 · 梯度大小有界
**陈述**：`PotentialField.grad_xy` 返回值不得包含 `NaN` 或 `inf`。
**守护者**：`obstacle_potential` 的 `max(d, 0.05)` 与 `interaction_potential` 的 `max(d, 0.5)`。
**违反后果**：nominal policy 输出 NaN，污染整个链路。

### INV-M-LYAP-1 · V 非负
**陈述**：`QuadraticLyapunov.V(x) ≥ 0`。
**守护者**：二次型定义（`q_v > 0` 且平方）。
**测试**：类型系统级（正定性）。

### INV-M-CBF-1 · QP 总返回
**陈述**：`CBFQPFilter.filter` 永远返回 `(Control, dict)`，不抛异常，不返回 `None`。
**守护者**：`filter` 末端的 fallback 分支。
**测试**：`test_cbf.py` ✅

### INV-M-CBF-2 · fallback 行为
**陈述**：当 `info["status"] == "fallback_brake"`，返回的 `u = Control(0, -jerk_max)`。
**守护者**：`cbf.py::filter` 的 fallback 分支。
**测试**：应补（AI-12）。

### INV-M-INV-1 · 松弛单调
**陈述**：`ControlInvariantOperator.apply` 的松弛循环里，jerk 单调不增。
**守护者**：`new_jerk = max(u.jerk - j_max/N, -j_max)`。
**理由**：保证 dV/dt 单调下降（E-18 的推论）。
**测试**：应补（AI-12）。

### INV-M-INV-2 · info 字段完整
**陈述**：`apply` 返回的 `info` 字典必须包含 `{"cbf", "V", "dV_dt", "status"}`。
**守护者**：`apply` 的 info 初始化与更新。
**测试**：`test_trace.py` 间接守护。

### INV-M-PLAN-1 · step 返回 3 元
**陈述**：`StructuralPlanner.step` 返回 `(State, Control, dict)`，trace 字典严格符合 INV-G5 的 16 字段。
**守护者**：`planner.py::step`。
**测试**：`test_trace.py::test_planner_run_emits_schema_versioned_jsonl` ✅

### INV-M-PLAN-2 · run 产出长度
**陈述**：`run(horizon_steps=N)` 返回 `(states, controls, traces)` 中 `len(states) == N+1`，`len(controls) == len(traces) == N`。
**守护者**：`planner.py::run`。
**测试**：`test_trace.py` ✅

### INV-M-TRACE-1 · schema_version 不自动升级
**陈述**：`TRACE_SCHEMA_VERSION = "1.1"` 在代码里是常量；bump 必须是显式 PR。
**守护者**：`trace.py` 顶部常量。

### INV-M-TRACE-2 · 向量长度固定
**陈述**：`trace["state"]` / `trace["next_state"]` 长度 = 6；`trace["u_nn"]` / `trace["u_safe"]` 长度 = 2。
**守护者**：`build_trace_record` 的实现。
**测试**：`test_trace.py` ✅

---

## 契约演进不变式（INV-C*）

### INV-C-TRACE
**陈述**：trace schema 演进规则：
- 新字段 → 保持 `schema_version` 不变（v1.x）；
- 删字段 / 改字段语义 → bump 到 v2.0 并在 CHANGELOG 写迁移；
- 下游读取前必须 `if schema_version != expected: abort`。
**守护者**：`trace-schema.md`（AI-04 补充）。

### INV-C-BENCH
**陈述**：同上，针对 `benchmark.metrics.v1`。
**守护者**：`benchmark-metrics.md`（AI-04 补充）。

### INV-C-PARAM
**陈述**：`VehicleParams` 字段的删除 / 改名必须走整车 OTA 级发布流程（见 knowledge-base.html §6.5）。

---

## 总数与覆盖统计

| 类别 | 数量 | 有自动断言 | 有独立测试 | 仅 manual review |
| --- | --- | --- | --- | --- |
| 全局 INV-G | 13 | 8 | 5 | 2 |
| 模块 INV-M | 13 | 5 | 6 | 2 |
| 契约 INV-C | 3 | 0 | 0 | 3 |
| **合计** | **29** | **13** | **11** | **7** |

目标：下一轮让 `有自动断言` + `有独立测试` 覆盖 ≥ 80%（当前 82.7%）。

---

## 附：新建 invariants 的模板

```markdown
### INV-X-NAME · 标题
**陈述**：... （数学/代码形式的断言）
**守护者**：... （哪个模块/哪行代码负责）
**理由 / 证明草图**：... （为什么必须成立）
**测试**：... （测试文件::测试名 · 或 "缺失 + 打算补"）
**违反后果**：... （最坏情况）
**标注**：AUTO / MANUAL / AUTO + MANUAL
```
