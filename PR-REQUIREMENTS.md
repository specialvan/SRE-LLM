---
spec: starship-recovery · PR-level functional requirements
version: 0.3.7
updated: 2026-05-12
owner: spacex-session
baseline-commit: cf9c8dc
head-commit: (post-v0.3.7 commit · see git log)
status-legend:
  - "✅ SHIPPED  · 已实现 · 有测试 + 证据"
  - "🟡 IN-PROG  · 已开工 · 尚未合并"
  - "🔵 PROPOSED · 仅 spec · 等待拉取"
  - "❌ DROPPED  · 放弃理由见 change-log"
invariants:
  - I-1 依赖方向单向：starship/ 绝不 import sre_control/（由 test_import_graph.py 自动守护）
  - I-2 事件 schema 封闭：新 kind 必须同步 EVENT_COUNTEREXAMPLES + schema + 测试
  - I-3 降级路径对齐：runtime.degraded=True 必然伴随 DEGRADED_* 状态和至少 1 条 event
  - I-4 文档不钉死 HEAD：不得在文档里写"最新 commit = <具体 SHA>"，用"近期日志包含 <关键 commit>"表达
  - I-5 adapter 异常不崩栈：任何 SREControlStack 阶段抛异常必须转为 stability_violation event + DEGRADED_<stage>
quality-gates:
  - pytest tests -q                 # 51 passed
  - python -m analysis.run_all      # 10 studies finish <4s
  - python -m scripts.build_kb      # 16 assets rebuild
  - python -m examples.demo_sre_loop
  - HTML well-formed (html.parser)
event-kinds-total: 10
---

# PR 级功能需求清单 — 星舰筷子塔回收 + SRE 复利栈

> 本 spec 把 `DOC/spacex/` 19 张公式示意图 + 后续 SRE 抽象 + 可观测性 + 契约 + 移交包
> **全部** 翻译成可独立交付的 PR。颗粒度按 "1 个 PR = 1~2 天 / ≤400 行代码" 切分。
>
> 本版 (v0.3) 相对 v0.2 的变化见 [Change Log](#change-log)。

---

## 0 · 如何阅读本 spec

| 你要做什么 | 跳到 |
| --- | --- |
| 接手并开工 | [§NFR](#nfr--non-functional-requirements) + [§Refine Loop](#refine-loop--本工程的工作节奏) + [§Backlog](#backlog--proposed-prs) |
| 审查某个 PR 是否达到 DoD | 该 PR 下方的 `Status` / `Evidence` 字段 |
| 追溯图片 / 公式 / 代码 / 测试 / 证据 | [§Traceability](#traceability--pr--图--公式--文件--测试--证据--commit) |
| 看 spec 自己怎么演化 | [§Change Log](#change-log) |

---

## 1 · 章节 ↔ 图片映射

| § | 主题 | 图片 |
| --- | --- | --- |
| 1 | Lossless Convexification | image-11, image-12 |
| 2 | Successive Convex Programming | image-13, image-14 |
| 3 | 6-DoF Rigid Body on SO(3) | image-15, image-16 |
| 4 | Thrust Pointing Constraint | image-17, image-18 |
| 5 | EKF 传感器融合 | image-1, image-10, image-19 |
| 6 | MPC 滚动时域 | image-2, image-3, image-4 |
| 7 | Belly-Flop / Landing-Flip | image-5, image-6, image-7 |
| 8 | Chopstick-catch 推力分配 | image.png, image-8, image-9 |

命名规约：`PR-<section>-<seq>: <短标题>` — 例：`PR-1-01: 无损凸化 PDG 问题构造`。

---

## NFR · Non-Functional Requirements

### NFR-1 · Quality Gates（每个 PR 合并前全部绿）

| Gate | 命令 | 预期 |
|---|---|---|
| 单元测试 | `python -m pytest tests -q` | **51 passed** |
| 基准证据 | `python -m analysis.run_all` | All 10 studies finish in ~3 s |
| 资产构建 | `python -m scripts.build_kb` | 16 assets rebuilt |
| 端到端 Demo | `python -m examples.demo_sre_loop` | 12 行 trace 无异常 |
| PDG Demo | `python -m examples.demo_powered_descent` | 末态位置 ~2e-6 m |
| Catch Demo | `python -m examples.demo_catch_phase` | lateral_error 稳定在窗口内 |
| HTML | `html.parser` validation | `issues == []` |
| JSON trace | `json.dumps(stack.trace)` | 无异常，无 `numpy.bool_` 泄漏 |

### NFR-2 · Invariants（三大硬约束，违反即拒绝合并）

- **I-1 依赖方向单向**：`starship/` 绝不 `import sre_control/`。验证：
  ```
  python -m pytest tests/test_import_graph.py -q
  ```
  （由 `dd9cd7a` 合入 AST 护栏后自动守护。手工 grep 仍可用作 sanity：
  `grep -rE "^(from|import) sre_control" starship/` 必须空。）
- **I-2 事件 schema 封闭**：新增 runtime event `kind` 必须同步：
  1. `sre_control/events.py::EVENT_COUNTEREXAMPLES` 加条目
  2. 产生 event 的 adapter 代码路径
  3. `tests/test_event_schema.py` 让新 kind 被真实触发
  4. `docs/EVENT_SCHEMA.md` + `docs/V2_Knowledge/knowledge-base.html` 索引表
- **I-3 降级路径对齐**：`runtime.degraded=True` 必然伴随至少 1 个 `DEGRADED_*` 状态
  和至少 1 条 event。验证：`tests/test_contracts.py::test_sre_stack_*_upward`
  系列（5 条）必须 pass。
- **I-4 文档不钉死 HEAD**（2026-05-12 新增，来自 `CODEX_TRIAGE.md §4`）：
  - handoff / checklist / knowledge base **不得**写"最新 commit = `<具体 SHA>`"
  - 应改写为"近期日志应包含 `<关键 review commit>`"
  - 否则每次新增文档 commit 就会让清单过期、误导下一轮 agent
  - 例：`HANDOFF_CHECKLIST.md` 和 `V2_Knowledge/knowledge-base.html` 已被 `dd9cd7a` 按此规则修正
- **I-5 adapter 异常不崩栈**（2026-05-12 新增，来自 PR-M-04）：
  - `SREControlStack.step()` 的 5 个阶段每一步都必须包在 try/except 里
  - 任何 stage 抛异常必须转为 `stability_violation` event + `DEGRADED_<stage>`
  - 必须提供安全回退值（fusion→x̂=forecast，plan→replicas 不变，
    guard→零动作，allocate→零 shares），让剩余阶段继续运行
  - 验证：`tests/test_contracts.py::test_sre_stack_survives_adapter_exception`
    + `tests/test_contracts.py::test_sre_stack_survives_autoscaler_exception`

### NFR-3 · 依赖图护栏

```
allowed   : starship/*    ← no imports from sre_control/
allowed   : sre_control/* ← may import starship/*
allowed   : sre_control/events.py ← no imports from starship/
disallowed: starship/*    ← cannot import sre_control/events
disallowed: docs/*        ← no runtime code
```

### NFR-4 · 复现性

- 所有分析脚本必须 `np.random.default_rng(seed=0)`。
- 任何随机化组件（MPC warm-start 初值、EKF 初始 P）必须给确定性 default。
- `analysis/artifacts/SUMMARY.txt` 的 before/after 数字在重跑时误差 ≤ ±5%。

### NFR-5 · 可审查性

- 每个 adapter 必须在 `step()/allocate()/audit()/plan()` 里同时返回：
  `result` + `local_states: list[str]` + `events: list[dict]`。
- 栈级 `SREControlStack.step()` 必须汇总所有 adapter 本地事件到 `runtime.events`。
- 每轮 PR 合并前，`docs/CODEX_HANDOFF.md` 的"本轮做了什么"必须更新。

### NFR-6 · 低依赖

- 运行时依赖锁定在 `numpy>=1.24, scipy>=1.10` + 可视化的 `matplotlib, pillow`。
- 禁止引入 `cvxpy/osqp/torch/pandas` 作为**硬依赖**（可作为 optional fallback）。

---

## Refine Loop · 本工程的工作节奏

### R-1 · 单 PR 推进顺序

1. **把数学/契约定义对齐** — 先动 `docs/*.md`，不动代码
2. **定 baseline** — 在 `analysis/sXX_*.py` 里把"不用这个公式"的对照组写清
3. **实现 after 路径** — 在 `starship/` 或 `sre_control/` 写最小可运行模块
4. **证据** — 证据曲线、before/after 数字进 `analysis/artifacts/SUMMARY.txt`
5. **边界测试** — 在 `tests/` 补边界 case（失效、rank-deficient、缺失观测）
6. **文档包装** — 最后才改 `docs/knowledge-base.html` / `V2_Knowledge/`

### R-2 · 每轮 PR 必答的 6 个问题

- 这个模块的状态是否定义完整（State × Input × Output × Invariant）？
- 约束是硬的还是软的？是否被误写成了目标项？
- baseline 是否公平？不是故意做坏 baseline 来凸显 after？
- after 的收益是否来自真正机制，而不是场景偏置？
- 有没有边界输入会把模块打坏？是否有 counter-example？
- 这个模块能否被 SRE 语义无损迁移？迁移层是否产生了合法的 event？

### R-3 · 验收准则

一个 PR 算"够用"至少满足：

- 能独立运行（`python -m examples.demo_*` 或 `pytest tests/test_*`）
- 能给出 before / after 证据（analysis/artifacts 有条目）
- 能被 SRE 解释（counter-example 写入 `EVENT_COUNTEREXAMPLES` 或 spec）
- 能经受边界测试（至少 1 条故意触发 failure path 的用例）
- 不破坏 NFR-2 三大不变量

### R-4 · 优先级排序

1. **correctness**（数学正确）
2. **constraint handling**（约束与边界）
3. **numerical stability**（Joseph form / warm-start / rank 处理）
4. **evidence quality**（seed 固定、baseline 公平）
5. **docs polish**

---

## Epic 1 · 无损凸化 (Lossless Convexification)

### PR-1-01 · 动力下降 PDG 问题结构 (`image-11`)

- **Status**: ✅ SHIPPED (baseline commit `cf9c8dc`)
- **背景**：原图 `image-11` 展示 Starship 下降段"无损凸化"的问题框架：把原本含
  `ρ1 ≤ ‖Γ‖ ≤ ρ2` 的非凸推力下界松弛成凸问题。
- **范围**：
  - `LosslessPDG` 数据类：初始/终止状态、重力、Isp、ρ1/ρ2、θ_max、时间网格。
  - `assemble()` 返回决策变量、线性动力学约束、指向锥约束与目标。
  - 对数质量变换 `z = ln m` 以避免 `Γ/m` 非线性。
- **公式**：`ṙ = v`，`v̇ = g + Γ/m`，`ṁ = −‖Γ‖ / (Isp g0)`，`z = ln m`。
- **DoD**：
  - 最小规模问题（N=20）能在 100 ms 内组装完成并求解到 KKT 容差 ≤1e-4。
  - 求解得到的 `‖Γ_k‖ ∈ [ρ1, ρ2]` 自然恢复（松弛紧）。
- **Evidence**：
  - 文件 `starship/lossless_convex.py`
  - 测试 `tests/test_lossless_convex.py`（通过）
  - 证据 `analysis/s01_lossless_convex.py` → `pos_err 148.3 → 2.125e-6 m`

### PR-1-02 · 最小燃耗代价函数 (`image-12`)

- **Status**: ✅ SHIPPED
- **背景**：`image-12` 补充 `min −z_N s.t. ḟ = g + Γ/m, Γ·n̂ ≥ σ·cos θ_max`。
- **范围**：
  - 代价 `min −z(T)` ↔ 最大化末端质量。
  - `solve()` 返回 `(trajectory, thrust_profile, status, objective)`。
  - 求解器：scipy `minimize` 内点法；装了 cvxpy 则可切换（optional）。
- **DoD**：
  - 无大气重力场景末态位置/速度误差 ≤ 1 m / 1 m·s⁻¹。
  - 不依赖 cvxpy 也能跑（scipy-only 回退）。
- **Evidence**：
  - 文件 `starship/lossless_convex.py :: LosslessPDG.solve()`
  - Demo `examples/demo_powered_descent.py` 末态 2.125e-6 m
  - 证据 analysis s01 `cone_margin_min > 0`


---

## Epic 2 · Successive Convex Programming

### PR-2-01 · 参考轨迹线性化 (`image-13`)

- **Status**: ✅ SHIPPED
- **背景**：`image-13` 给出 `δẋ = A(t)δx + B(t)δu, ‖δx‖ ≤ ε`。
- **范围**：
  - `linearize(traj_ref, dynamics)` 返回 `(A_k, B_k, c_k)` 序列。
  - 支持 6-DoF 刚体动力学（§3）和简化 3-DoF 质点动力学。
  - 数值雅可比回退：`scipy.optimize.approx_fprime`。
- **DoD**：单步线性化误差 `‖f(x+δx, u+δu) − f(x,u) − Aδx − Bδu‖ = O(‖δ‖²)`。
- **Evidence**：
  - 文件 `starship/scp.py :: linearize()`
  - 证据 analysis s02 `final_pos_err 8.08 → 2.87`

### PR-2-02 · 置信域 SCP 主循环 (`image-14`)

- **Status**: ✅ SHIPPED
- **背景**：`image-14` 强调"迭代：δx→0 收敛"。
- **范围**：
  - `SCP.iterate(x0, N, max_iters=10)`：初猜 → 线性化 → QP（带 trust-region）→ 更新。
  - 动态调整 `η`：改进比 ρ>0.7 放大、ρ<0.1 缩小。
  - 终止条件：`‖x^{k+1}−x^k‖ < ε_tol` 或超出 `max_iters`。
- **DoD**：软/硬着陆标准测试能在 ≤6 轮收敛；给出收敛历史日志。
- **Evidence**：
  - 文件 `starship/scp.py :: SCP`
  - GIF `docs/assets/s02_benefit.gif` 演示相邻迭代 ‖Δx‖ 指数收敛

---

## Epic 3 · 6-DoF 刚体动力学

### PR-3-01 · 四元数工具箱

- **Status**: ✅ SHIPPED
- **背景**：SO(3) 上的姿态必须用单位四元数避免欧拉角奇异。
- **范围**：`Quaternion` 数据类 + `mul/conj/normalize/to_matrix/from_axis_angle/Omega`
  + 指数映射 `exp(½·ω·dt)` 用于离散积分。
- **DoD**：四元数乘法与 `scipy.spatial.transform.Rotation` 一致，误差 ≤ 1e-12。
- **Evidence**：
  - 文件 `starship/quaternion.py`
  - 测试 `tests/test_quaternion.py` 3 条全通过
  - 证据 analysis s03 `quat_norm_drift ~ 1e-12`（积分 1000 次）

### PR-3-02 · 6-DoF 动力学 `q̇/ω̇/ṙ/v̇` (`image-15`, `image-16`)

- **Status**: ✅ SHIPPED
- **背景**：`image-15/16` 给出 `q̇=½Ω(ω)q`, `ω̇ = I⁻¹(τ − ω×Jω)`。
- **范围**：
  - `State6DOF` 数据类 `[r, v, q, ω, m]`。
  - `RigidBody.f(state, force_body, torque_body)` 返回 `dstate/dt`。
  - RK4 积分 `step()`，四元数事后归一化。
- **DoD**：
  - 零力矩自由落体 2 s 后位置误差 ≤ 1e-6 m；角动量守恒 ≤ 1e-8。
  - 纯绕 z 轴力矩产生的姿态与解析积分一致。
- **Evidence**：
  - 文件 `starship/rigid_body.py`
  - 测试 `tests/test_rigid_body.py` 2 条全通过
  - 证据 analysis s03 `angle_rmse 0.0558 rad → 5.7e-7 rad`（×10⁵）

---

## Epic 4 · 推力指向 / 幅值约束

### PR-4-01 · 推力器与约束定义 (`image-17`)

- **Status**: ✅ SHIPPED
- **背景**：`image-17` 要求 `n̂ᵀu ≥ ‖u‖ cos θ_max, ‖u‖ ≤ T_max`。
- **范围**：
  - `Thruster` + `ThrusterBank`（默认 3 台 Raptor 底部 120°）
  - `assemble_pointing_cone(u, n_hat, theta_max)` 返回凸约束 callable。
- **DoD**：满足锥约束时约束函数 ≥ 0，违反时 < 0。
- **Evidence**：
  - 文件 `starship/thrust_constraints.py`
  - 测试 `tests/test_thrust_constraints.py` 3 条全通过

### PR-4-02 · 锥+幅值约束的解析投影 (`image-18`)

- **Status**: ✅ SHIPPED
- **背景**：把 `u_nom` 投影到锥约束 & 幅值约束上。
- **范围**：`ConeQPFilter.filter(u_nom)` 闭式三阶段投影（内/极/侧）再按比例缩到球。
- **DoD**：锥外输入被矫正至锥边；锥内输入不变；解析解与数值 QP 差 ≤ 1e-8。
- **Evidence**：
  - 文件 `starship/thrust_constraints.py :: ConeQPFilter`
  - 证据 analysis s04 `cone_violations 97.4% → 0%`

---

## Epic 5 · EKF 多源传感器融合

### PR-5-01 · EKF 骨架 (`image-1`)

- **Status**: ✅ SHIPPED
- **背景**：`image-1` 给出经典 EKF 更新式。
- **范围**：`EKF.predict(u, dt)` + `EKF.update(z, h, H, R)`；状态 `x ∈ R^13`；
  Jacobian 支持解析或数值回退。
- **DoD**：1-D 自由落体小型测试 RMSE 随量测噪声线性变化。
- **Evidence**：
  - 文件 `starship/ekf.py`
  - 测试 `tests/test_ekf.py` 通过

### PR-5-02 · 雷达量测模型 (`image-10`)

- **Status**: ✅ SHIPPED
- **范围**：`RadarMeasurement.h(x) = [‖r−p_tower‖, az, el]` + 解析 Jacobian。
- **DoD**：与数值雅可比差 ≤ 1e-6。
- **Evidence**：`starship/ekf.py :: RadarMeasurement`

### PR-5-03 · IMU + 塔架视觉 Fiducial 融合 (`image-19`)

- **Status**: ✅ SHIPPED
- **范围**：`IMUMeasurement` + `FiducialMeasurement` + `MultiSensorEKF.step()`
  逐源顺序 update。
- **DoD**：雷达失效 1 s 内仅用 IMU+视觉仍可把位置 drift ≤ 1 m。
- **Evidence**：
  - 文件 `starship/ekf.py`
  - 证据 analysis s05 `vel_rmse 481.1 → 51.07 m/s`（×9.4）

---

## Epic 6 · MPC 滚动时域

### PR-6-01 · 线性离散化 (`image-2`)

- **Status**: ✅ SHIPPED
- **范围**：`LinearDiscretizer.zoh(dt)`：零阶保持 `A_d = e^{A·dt}`。
- **DoD**：`A_d`, `B_d` 与 `scipy.signal.cont2discrete` 一致。
- **Evidence**：`starship/mpc.py :: LinearDiscretizer`

### PR-6-02 · 二次 MPC 代价 + 终端代价 (`image-3`)

- **Status**: ✅ SHIPPED
- **范围**：`QuadraticMPC.solve(x0)` 组装稠密 QP；`scipy.optimize.minimize(L-BFGS-B)`。
- **DoD**：双积分器系统在 20 步内把位置/速度收敛到 ≤ 1e-3。
- **Evidence**：
  - 文件 `starship/mpc.py :: QuadraticMPC`
  - 测试 `tests/test_mpc.py` 通过
  - 证据 analysis s06 `final_err 0.01192 → 3.46e-7`（×3.4e4）

### PR-6-03 · 热启动与执行 u₀ (`image-4`)

- **Status**: ✅ SHIPPED
- **范围**：`QuadraticMPC.step(x0)` 返回 `u_0` + shift warm-start。
- **DoD**：热启动平均迭代数下降 ≥ 30%（对比 cold-start）。
- **Evidence**：`starship/mpc.py :: QuadraticMPC.step()`

---

## Epic 7 · Belly-Flop → Landing-Flip

### PR-7-01 · Belly-flop 气动参考 (`image-5`)

- **Status**: ✅ SHIPPED
- **范围**：`bellyflop_reference(altitude, target)` 返回名义四元数 + 空气阻力简化模型。
- **DoD**：参考姿态连续、模值 1 误差 ≤ 1e-9。
- **Evidence**：`starship/flip_maneuver.py :: bellyflop_reference`

### PR-7-02 · 力矩合成 τ_net (`image-6`)

- **Status**: ✅ SHIPPED
- **范围**：`net_torque(thrusters, T_cmds, rcs_cmd)` → `τ_body ∈ R³`。
- **DoD**：单元测试验证矩臂×推力叉积方向。
- **Evidence**：`starship/flip_maneuver.py :: net_torque`

### PR-7-03 · Landing-flip 规划 (`image-7`)

- **Status**: ✅ SHIPPED
- **范围**：`FlipPlanner.plan(state0, t_span, I, theta_max)` bang-bang 最小时间翻转。
- **DoD**：末态俯仰角误差 ≤ 2°、角速度 ≤ 5°/s。
- **Evidence**：
  - 文件 `starship/flip_maneuver.py :: FlipPlanner`
  - 证据 analysis s07 `final_pitch_deg 36.37 → 0`

---

## Epic 8 · 塔架机械臂捕获段

### PR-8-01 · 捕获段坐标系 & 对接窗口 (`image.png`)

- **Status**: ✅ SHIPPED
- **范围**：`CatchGeometry` + `lateral_window(altitude)`（随高度线性收窄）。
- **DoD**：给定典型参数 `(height=150 m, width=5 m)`，窗口函数单调递减。
- **Evidence**：`starship/catch_controller.py :: CatchGeometry`

### PR-8-02 · 多推力器冗余分配 (`image-8`)

- **Status**: ✅ SHIPPED
- **范围**：`allocate(T_demand, τ_demand, bank)` 解带 box 约束的最小二乘。
- **DoD**：3 台推力器需求可重构误差 ≤ 1e-6。
- **Evidence**：
  - 文件 `starship/catch_controller.py :: ThrustAllocator`
  - 测试 `tests/test_allocation.py` 通过

### PR-8-03 · 捕获段主控制器 (`image-9`)

- **Status**: ✅ SHIPPED
- **范围**：`CatchController.step(state_est, ref, dt)` 外环 MPC + 内环 allocate。
- **DoD**：`demo_catch_phase.py` 模拟 50 m→0 m 下降，末态位置误差 ≤ 0.5 m，姿态 ≤ 2°。
- **Evidence**：
  - 文件 `starship/catch_controller.py :: CatchController`
  - Demo `examples/demo_catch_phase.py` 跑通

---

## Epic 9 · 端到端装配与回归

### PR-9-01 · Pipeline 串联 EKF → MPC → 分配

- **Status**: ✅ SHIPPED
- **范围**：`pipeline.RecoveryPipeline.step(sensors)` 返回 `thrust_commands`。
- **DoD**：`demo_powered_descent.py` 跑通 10 km → 塔架，末态位置误差 ≤ 1 m。
- **Evidence**：`starship/pipeline.py` + `examples/demo_powered_descent.py`

### PR-9-02 · 可观测性 trace

- **Status**: ✅ SHIPPED
- **范围**：每步输出 JSONL：`{t, x̂, u_cmd, T_i, θ_cone_margin, solve_ms}`。
- **DoD**：一次 demo 跑完产出可被 `pandas.read_json(lines=True)` 读入的 trace。
- **Evidence**：`starship/pipeline.py` trace output

### PR-9-03 · 单元测试 & CI

- **Status**: ✅ SHIPPED
- **范围**：每个 Epic 至少一组 pytest；`pytest -q` 全绿，覆盖率 ≥ 70%。
- **DoD**：本地 `pytest` 通过。
- **Evidence**：`tests/test_*.py` 共 33 条用例，全通过


---

## Epic 10 · SRE 翻译层（retroactive · 2026-05-10）

> 把 8 个星舰原件 1:1 翻译成 SRE 原生适配器；每条都是单文件 < 100 行。
> 整个 Epic 以 commit `43b58a9` 为 baseline（首次引入 `sre_control/`）。

### PR-10-01 · `PoolCapacityPlanner`（§1 对应）

- **Status**: ✅ SHIPPED (commit `43b58a9` + `d9cecb7` 加 events)
- **范围**：把 `LosslessPDG` 的 `ρ1 ≤ σ ≤ ρ2, pool ≤ σ` 形式化到连接池规划。
- **公式**：`σ_k = clip(ceil(forecast_k / rps_per_conn), min_keep_alive, max_capacity)`
- **DoD**：
  - `min_keep_alive ≤ pool ≤ max_capacity` 无论如何保持
  - 预测超过上限时返回非零 `capacity_shortfall_rps`
- **Evidence**：
  - 文件 `sre_control/pool_planner.py`
  - 测试 `tests/test_sre_control.py::test_pool_planner_*`（2 条）

### PR-10-02 · `CanaryScheduler`（§2 对应）

- **Status**: ✅ SHIPPED (commit `43b58a9` + `2c82861` 加 events)
- **范围**：SCP 置信域搬到灰度发布：`ρ>0.7 扩 ×1.5, ρ<0.1 缩 ×0.5, burn SLO 冻结`。
- **DoD**：
  - trust region 始终 ∈ `[eta_min, eta_max]`
  - SLO 烧穿时 `accepted=False` 且 `events` 含 `rollout_rejected`
- **Evidence**：
  - 文件 `sre_control/canary_scheduler.py`
  - 测试 `tests/test_sre_control.py::test_canary_*`（2 条）

### PR-10-03 · `TopologyState`（§3 对应）

- **Status**: ✅ SHIPPED (commit `43b58a9` + `d9cecb7` 加 repair events)
- **范围**：单位四元数 + exp-map 搬到 ring/Raft/版本拓扑状态演化。
- **DoD**：
  - 1000 步 step 后 `‖q‖` 偏差 ≤ 1e-8
  - 输入非有限 / 近零四元数会自动 repair + 产生 `topology_state_repaired` event
- **Evidence**：
  - 文件 `sre_control/topology_state.py`
  - 测试 `tests/test_sre_control.py::test_topology_*`（2 条）

### PR-10-04 · `SLOGuardrail`（§4 对应）

- **Status**: ✅ SHIPPED (commit `43b58a9` + `5e0a94e` 加 events)
- **范围**：闭式锥+球投影作为 AI/ML 建议的硬护栏。
- **DoD**：
  - 锥外 proposal 投影后 cone_margin ≥ 0
  - magnitude 超上限时缩到上限
  - 触发投影时 `events` 含 `unsafe_proposal_projected`
- **Evidence**：
  - 文件 `sre_control/slo_guardrail.py`
  - 测试 `tests/test_sre_control.py::test_guardrail_*`（2 条）

### PR-10-05 · `SignalFusion`（§5 对应）

- **Status**: ✅ SHIPPED (commit `43b58a9` + `5e0a94e` 加 events)
- **范围**：EKF 搬到 metrics + traces + RUM 融合；OU 过程模型作为默认 drift。
- **DoD**：
  - 200 步模拟后后验与 truth 距离 ≤ 30（`[1200, 30, 0.4]` 量纲）
  - sensor reading 为 None 时 skip update 并产 `missing_sensor` event
- **Evidence**：
  - 文件 `sre_control/signal_fusion.py`
  - 测试 `tests/test_sre_control.py::test_signal_fusion_*`（2 条）

### PR-10-06 · `PredictiveAutoscaler`（§6 对应）

- **Status**: ✅ SHIPPED (commit `43b58a9` + `2c82861` 加 events)
- **范围**：`QuadraticMPC` 搬到 (replicas, rps_served) 双积分器，每拍解 QP 只下发 u₀。
- **DoD**：
  - 输出必须是 `int` 且 ∈ `[replicas_min, replicas_max]`
  - 打到硬边界时 `last_trace["events"]` 含 `replica_bound_active`
- **Evidence**：
  - 文件 `sre_control/predictive_autoscaler.py`
  - 测试 `tests/test_sre_control.py::test_autoscaler_*`（2 条）

### PR-10-07 · `FastTrafficSwitcher`（§7 对应）

- **Status**: ✅ SHIPPED (commit `43b58a9` + `2c82861` 加 events)
- **范围**：bang-bang 最短时间公式 `T_min = 2·√(|Δshare| · J / τ_max)` 搬到紧急切换。
- **DoD**：
  - 末态 share 与目标差 ≤ 1e-6，末态速率 = 0
  - `T_min > deadline_s` 时 `events` 含 `deadline_exceeded`
- **Evidence**：
  - 文件 `sre_control/fast_switcher.py`
  - 测试 `tests/test_sre_control.py::test_switcher_*`（2 条）

### PR-10-08 · `WeightedLoadBalancer`（§8 对应）

- **Status**: ✅ SHIPPED (commit `43b58a9` + `5e0a94e` 加 events + `4319a41` 修 bool)
- **范围**：带 box 约束的 `lsq_linear` 搬到多实例 RPS 分配。
- **DoD**：
  - 所有返回 `saturation` 列表是 Python `bool`，可 JSON 序列化
  - 可达目标时 `rps_residual < 1e-6`
  - box 饱和或残差不可消时 `events` 含 `bounded_ls_residual`
- **Evidence**：
  - 文件 `sre_control/weighted_balancer.py`
  - 测试 `tests/test_sre_control.py::test_balancer_*`（1 条）

### PR-10-09 · `SREControlStack` 端到端装配

- **Status**: ✅ SHIPPED (commit `43b58a9` + `70c1d6a` 加 runtime trace + `41cdea8` 对齐 DEGRADED_GUARD)
- **范围**：把 8 个 adapter 组成 OBSERVE → PLAN → GUARD → ALLOCATE → EXECUTE 数据流。
- **DoD**：
  - 一次 `step()` 产出完整 JSON-serializable trace
  - adapter 可选化（canary / switcher / pool / topology）但 trace 不丢字段
  - adapter 降级时 `runtime.states` 补 `DEGRADED_*`、`runtime.events` 补 event
- **Evidence**：
  - 文件 `sre_control/stack.py`
  - Demo `examples/demo_sre_loop.py`（60 s 仿真）
  - 证据 `analysis/s09_sre_stack.py` → `slo_violation_pct 25 → 10`（×2.5）

---

## Epic 11 · Runtime 可观测性（retroactive · 2026-05-11）

> 把"每个 adapter 可以报自己失效"形式化为跨 adapter 的共享 schema。

### PR-11-01 · Event Schema 定义

- **Status**: ✅ SHIPPED (commit `1ee8ae5`)
- **范围**：
  - `sre_control/events.py`：`REQUIRED_EVENT_FIELDS`、`make_event`、`validate_event`
  - `EVENT_COUNTEREXAMPLES` 8 条 kind 必带 counter-example
  - `docs/EVENT_SCHEMA.md` 文档
- **DoD**：
  - 新 kind 不在 `EVENT_COUNTEREXAMPLES` 时 `make_event` 抛 `ValueError`
  - 所有 8 种 kind 都能由真实 adapter 触发并满足 `validate_event`
- **Evidence**：
  - 文件 `sre_control/events.py`、`docs/EVENT_SCHEMA.md`
  - 测试 `tests/test_event_schema.py` 2 条通过

### PR-11-02 · 栈级 runtime.states / events / degraded

- **Status**: ✅ SHIPPED (commit `70c1d6a` + `41cdea8`)
- **范围**：
  - `SREControlStack.step()` 返回 `entry["runtime"] = {states, events, degraded}`
  - observe/plan/guard/allocate 四阶段各自有 `DEGRADED_*` 状态和事件上浮
- **DoD**：
  - `runtime.degraded` 必然伴随至少一个 `DEGRADED_*` 和一条 event（I-3）
  - 5 条 `test_sre_stack_*_upward` 测试全通过
- **Evidence**：
  - 文件 `sre_control/stack.py`
  - 测试 `tests/test_contracts.py` 5 条通过
  - 文档 `docs/RUNTIME_STATES.md`

### PR-11-03 · 每个 adapter 下沉本地 events

- **Status**: ✅ SHIPPED (commit `5e0a94e` / `2c82861` / `d9cecb7`)
- **范围**：8 种 event kind 一一映射到 adapter 代码路径（见 PR-10-01..08）。
- **DoD**：见各 PR-10 的 Evidence；整体约束是 I-2（schema 封闭）。

---

## Epic 12 · 契约 + 不变量（retroactive · 2026-05-11）

### PR-12-01 · API Contracts 文档

- **Status**: ✅ SHIPPED (commit `4319a41`)
- **范围**：`docs/API_CONTRACTS.md` 列出 10 个公开接口的 input/output/state/failure/counter-example。
- **DoD**：每条 contract 都能追溯到一个测试文件和具体测试函数。
- **Evidence**：文档 `docs/API_CONTRACTS.md` §3 Contract-to-Test Map

### PR-12-02 · Runtime States FSM

- **Status**: ✅ SHIPPED (commit `4319a41`)
- **范围**：`docs/RUNTIME_STATES.md` 列出栈级 + 每模块的状态机、转移、降级矩阵。
- **DoD**：栈级状态与 `runtime.states` 字段一一对应。
- **Evidence**：`docs/RUNTIME_STATES.md`

### PR-12-03 · Contract 测试

- **Status**: ✅ SHIPPED (commit `4319a41` + `41cdea8`)
- **范围**：`tests/test_contracts.py` 5 条，覆盖 JSON trace / missing sensor /
  canary / guardrail / allocator 五种栈级事件传播。
- **DoD**：5 条测试全通过，trace 可 `json.dumps`。
- **Evidence**：`tests/test_contracts.py`

### PR-12-04 · 方程逐项拆解

- **Status**: ✅ SHIPPED (commit `e2658f6`)
- **范围**：`docs/EQUATION_DEEP_DIVE.md` 每条公式每个符号的量纲、作用、去掉会怎样。
- **DoD**：覆盖 §1 的 `ln m` 变换、§3 的 ½ 因子、§4 的锥代数展开三大关键推导。
- **Evidence**：`docs/EQUATION_DEEP_DIVE.md`

---

## Epic 13 · Handoff 移交包（retroactive · 2026-05-12）

### PR-13-01 · Claude Review 六件套

- **Status**: ✅ SHIPPED (commit `59389ee`)
- **范围**：`docs/claude-review/` 六份互补文档：
  - `README.md` · 导航
  - `REVIEW_OF_CODEX_SESSION.md` · 上一 session 的评审
  - `DETAILED_ARCHITECTURE.md` · 5 视图 + 依赖护栏
  - `EVENT_LIFECYCLE.md` · 单 tick 时序 + 3 场景逐帧
  - `FAILURE_MODES.md` · 每模块 symptom/cause/degrade/recover
  - `HANDOFF_CHECKLIST.md` · 15 分钟环境核查
- **DoD**：
  - 任何 agent 只读这 6 份文档即可决定是否接手
  - 第一个 commit message 末尾必须含 `Acknowledged: docs/claude-review/README.md`
- **Evidence**：`docs/claude-review/`

### PR-13-02 · V2 Knowledge Base

- **Status**: ✅ SHIPPED (commit `e2658f6`)
- **范围**：`docs/V2_Knowledge/knowledge-base.html` 把 V1 的机制图 + GIF + SRE 映射
  + Runtime Event 指南 + 失效模式 + 三大不变量 + 接手清单合成一页。
- **DoD**：
  - HTML well-formed（`html.parser` 无 issue）
  - 资产自包含（16 PNG/GIF 拷贝进 `V2_Knowledge/assets/`）
- **Evidence**：`docs/V2_Knowledge/knowledge-base.html`（52 KB）

### PR-13-03 · CODEX_HANDOFF 更新

- **Status**: ✅ SHIPPED (commit `e2658f6`)
- **范围**：`docs/CODEX_HANDOFF.md` 以 claude-review 为主读路径，加事件 kind 映射表、
  三大不变量、按优先级分档的下一步。
- **DoD**：下一轮 Codex 不读别的文档也能知道从哪里开始。
- **Evidence**：`docs/CODEX_HANDOFF.md`


---

## Backlog · PROPOSED PRs

> 来源：`docs/claude-review/REVIEW_OF_CODEX_SESSION.md §6` + `DETAILED_ARCHITECTURE.md §8` +
> `FAILURE_MODES.md §哨兵测试`。按颗粒度分 小 / 中 / 大 三档。

### 小档（非阻塞 · 清理）

#### PR-S-01 · test_event_schema 宽松签名

- **Status**: ✅ SHIPPED (commit `dd9cd7a`)
- **背景**：当前 `"Do not" in counterexample` 字符串签名脆，未来改 "Avoid" 会挂。
- **范围**：`tests/test_event_schema.py::test_every_event_kind_has_a_specific_counterexample`
- **DoD**：改成 `startswith(("Do not", "Avoid"))` 或直接删除该断言，靠
  `len >= 60` + kind ∈ EVENT_COUNTEREXAMPLES 足矣。
- **Evidence**：Codex 把匹配放宽为 `startswith(("Do not", "Avoid"))`，测试保留但更鲁棒。

#### PR-S-02 · CatchController 属性澄清

- **Status**: ✅ SHIPPED (v0.3.6 · 见 git log)
- **背景**：`API_CONTRACTS.md §2.9 CatchController` 放在 SRE 文档里容易误导。
- **范围**：加一段"属 starship 物理层，不反向依赖 sre_control"说明。
- **Evidence**：`docs/API_CONTRACTS.md §2.9` 顶部加 note 块，明确引用 I-1 不变量。

#### PR-S-03 · 收敛 CatchController wrapper 建议

- **Status**: ✅ SHIPPED (v0.3.6 · 见 git log)
- **背景**：`ARCHITECTURE.md §4.5` + `CODEX_HANDOFF.md §下一步` + `claude-review/FAILURE_MODES.md`
  同时提到 "未来做 CatchController SRE wrapper"，重复 3 次。
- **范围**：收敛到 `CODEX_HANDOFF.md` 一处；`ARCHITECTURE.md` 只保留依赖边界说明。
- **Evidence**：`docs/ARCHITECTURE.md §4.5` 第 5 条从原来的"建议 wrap"改成"已搬移"
  指针（指向 CODEX_HANDOFF）。

### 中档（单 commit 可完成）

#### PR-M-01 · 依赖方向护栏测试

- **Status**: ✅ SHIPPED (commit `dd9cd7a`)
- **背景**：I-1 至今靠人类守。需要 pytest 自动护栏。
- **范围**：`tests/test_import_graph.py`：遍历 `starship/*.py` AST，禁止 `import sre_control`；
  额外约束 `sre_control/events.py` 不得依赖 `starship/`。
- **DoD**：
  - 对现有代码通过
  - 故意在 starship 里加一行 `from sre_control import events` 会失败
- **Evidence**：新增文件 `tests/test_import_graph.py`；`pytest` 现为 **35 passed**。

#### PR-M-02 · Failure-trace before/after · event-level 证据

- **Status**: ✅ SHIPPED (本轮 commit · 见 git log)
- **背景**：之前 9 项 before/after 证据都在证明"控制效果变好"，但
  `EVENT_LIFECYCLE.md` 里的 brown-out / surge 事件密度只是叙事。PR-M-02 把它变成
  可复现的事件级证据。
- **范围**（实现在 `analysis/s10_failure_trace.py`）：
  1. 在同一条 300 s 仿真里主动注入三类故障：
     - `t ∈ [40, 60]` · 丢失 primary sensor reading
     - `t ∈ [120, 140]` · 收紧 `replicas_max = 18` 强制 MPC 打顶
     - `t ∈ [220, 230]` · 发出 78° 偏离 nominal 的 NN proposal
  2. 产出 3 件证据：
     - `docs/assets/s10_event_density.png` + `V2_Knowledge/assets/` 同步
     - `docs/assets/s10_cooccurrence.png` + `V2_Knowledge/assets/` 同步
     - `analysis/artifacts/s10_trace_sample.jsonl`（10 行）
  3. `analysis.run_all` STUDIES 列表追加 s10（→ 10 studies）。
  4. `docs/V2_Knowledge/knowledge-base.html` 的 `#lifecycle` 节嵌入两张图。
- **DoD**（全部达成）：
  - ✅ `python -m analysis.s10_failure_trace` 跑通；3 件证据写入对应路径
  - ✅ `analysis.run_all` 报告 **All 10 studies finished**
  - ✅ `SUMMARY.txt` 新增 `§10 · Failure trace` 条目，带 event_count / distinct_kinds / mttr
  - ✅ 新产物不破坏 I-2 / I-3 / I-4（无新 event kind，无钉死 SHA）
  - ✅ 新增 `tests/test_failure_trace.py` 4 条契约测试固化证据可复现
- **Evidence**：
  - 文件 `analysis/s10_failure_trace.py`（280 LOC）
  - 测试 `tests/test_failure_trace.py`（4 条，全通过）
  - 证据 before=`0 events / 0 kinds`, after=`83 events / 4 kinds`
  - HTML 更新 `docs/V2_Knowledge/knowledge-base.html` 的 `#lifecycle` 节

#### PR-M-03 · SignalFusion innovation gating

- **Status**: ✅ SHIPPED (本轮 commit · 见 git log)
- **背景**：`FAILURE_MODES.md §SignalFusion` 指出：单次 10σ 尖峰观测会把 EKF 后验拉飞，
  线上 Prometheus/trace 链路里这种情况并不罕见（瞬时网络抖动 / clock skew）。
- **范围**：
  1. 给 `starship/ekf.py::EKF.update` 增加 optional 参数 `gate_threshold`——
     当 innovation Mahalanobis σ `√(yᵀS⁻¹y)` 超过阈值则**跳过 update**，返回
     `{"gated": True, "innovation_mahalanobis": d}`。
  2. 给 `sre_control/signal_fusion.py::SignalFusion` 加字段 `gate_threshold`
     (默认 `None` = 关闭，保持向后兼容)。启用时在 trace 中记录每次更新的 `d` 值。
  3. 注册新 event kind `outlier_rejected` 并按 I-2 流程全套同步：
     - 加入 `EVENT_COUNTEREXAMPLES`
     - 让 `tests/test_event_schema.py::_collect_local_events` 真实触发它
     - 加入 `docs/EVENT_SCHEMA.md` 和 V2_Knowledge 的索引表
  4. 新增 2 条专门测试：gating 生效 / 关闭 gate 保留旧行为。
- **DoD**（全部达成）：
  - ✅ 10σ 观测在 `gate_threshold=3.0` 时被拒，posterior 不动
  - ✅ `gate_threshold=None` 时行为与 v0.3.3 完全一致（向后兼容）
  - ✅ `outlier_rejected` event 能被真实 adapter 路径触发
  - ✅ schema closure 测试（I-2 守护）：新 kind 必须有真实 producer 且通过 validate_event
  - ✅ 总 event kind 数从 8 → 9
- **Evidence**：
  - 代码 `starship/ekf.py::EKF.update` (+30 LOC)
  - 代码 `sre_control/signal_fusion.py::SignalFusion` (+1 字段, +20 LOC 逻辑)
  - schema `sre_control/events.py::EVENT_COUNTEREXAMPLES["outlier_rejected"]`
  - 测试 `tests/test_sre_control.py` (+2 条) + `tests/test_event_schema.py` (+outlier 触发路径)
  - 文档 `docs/EVENT_SCHEMA.md` + `docs/V2_Knowledge/knowledge-base.html` 索引表
- **注意事项**：
  - `EKF.update` 原先返回 `None`，现在返回 dict。**这是公共 API 的破坏性变化**，
    但 `sre_control/signal_fusion.py` 是唯一的工程调用者，已同步更新；
    `analysis/s05_ekf.py` 里的 `.update()` 调用忽略返回值仍可工作。
  - 若未来把 gate 默认打开，必须先评估对 baseline 分析脚本的影响。

#### PR-M-04 · Stack 异常转成 event

- **Status**: ✅ SHIPPED (本轮 commit · 见 git log)
- **背景**：`FAILURE_MODES.md §哨兵测试` + `CODEX_TRIAGE.md §3` 都指出：当前
  `SREControlStack.step()` 任意 adapter 抛异常会中断控制循环——这是生产级不能接受的。
- **范围**：
  1. 给 step 的 5 个阶段（observe / plan / canary / guard / allocate）分别包
     try/except，异常时产 `stability_violation` event 并用**安全回退值**保证
     下游阶段继续跑。
  2. 注册新 event kind `stability_violation` 走完 I-2 全套同步。
  3. **升格 I-5 为新不变量**：任何 stage 抛异常必须转为
     `stability_violation` event + `DEGRADED_<stage>` + 安全回退。
  4. 新增 2 条专门测试：fusion 崩 + autoscaler 崩，分别验证回退。
- **DoD**（全部达成）：
  - ✅ `test_sre_stack_survives_adapter_exception` pass（fusion 抛 → 返完整 trace）
  - ✅ `test_sre_stack_survives_autoscaler_exception` pass（autoscaler 抛 → replicas 不变）
  - ✅ I-2 schema closure 测试通过（stability_violation 必须被真实触发）
  - ✅ 总 event kind 数从 9 → **10**
  - ✅ I-5 明文写入 NFR-2
- **安全回退值策略**：
  - SignalFusion 崩 → `observed_rps = forecast_rps`，清空 signals
  - PredictiveAutoscaler 崩 → `replicas_next = clip(current)`，不扩不缩
  - CanaryScheduler 崩 → `canary_step = None`
  - SLOGuardrail 崩 → `approved = 0` 向量（零动作永远安全）
  - WeightedLoadBalancer 崩 → `shares = zeros(n)`（等同于关掉流量）
- **Evidence**：
  - 代码 `sre_control/stack.py` (+~90 LOC，`_stability_event` 静态方法)
  - schema `sre_control/events.py::EVENT_COUNTEREXAMPLES["stability_violation"]`
  - 测试 `tests/test_contracts.py` (+2 条) + `tests/test_event_schema.py` 扩展
  - 文档 `docs/EVENT_SCHEMA.md` + V2 HTML 索引表 + 新增 I-5 不变量

### 大档（跨 session）

#### PR-L-01 · Lyapunov stability monitor

- **Status**: ✅ SHIPPED (本轮 commit · 见 git log)
- **背景**：§2.1 物理红线 `dV/dt ≤ 0` 在 `starship/` 层面尚未落地；SRE 侧等价物是
  "关键 SLI 的 Lyapunov 候选（如 error-rate 平方误差）不得连续上升" —— 这是自激震荡
  的经典特征。此 PR 把文章里的概念真正落成代码并接入现有事件体系。
- **范围**：
  1. **物理层**（新模块 `starship/stability_monitor.py`）：
     - `StabilityMonitor` 类：`V_fn`, `tolerance`, `k_violations`, `window`
     - `StabilityVerdict` 数据类（每 tick 的结构化结论）
     - 便捷 builder：`kinetic_plus_potential_V`, `quadratic_V`
     - 严格 **no import of sre_control**（守护 I-1）
  2. **迁移层**（新模块 `sre_control/stability_guard.py`）：
     - `StabilityGuard` 薄包装：把物理层的 `triggered` 翻译成 `stability_violation`
       event，stage 前缀 `StabilityGuard/<label>`
     - 复用 PR-M-04 注册的 `stability_violation` kind（两个合法 producer）
  3. **装配层**：`SREControlStack` 加 optional `stability` 字段，在 OBSERVE 之后
     PLAN 之前运行；触发时补 `DEGRADED_PLAN`
  4. **测试**：
     - `tests/test_stability_monitor.py` 7 条（物理层）
     - `tests/test_contracts.py::test_stability_guard_triggers_*` 1 条（端到端）
- **DoD**（全部达成）：
  - ✅ 单调上升的 V 在 `k_violations` 个 tick 后 `triggered=True`
  - ✅ 单次 blip 不触发（噪声容忍）
  - ✅ `reset()` 清理状态
  - ✅ `stability_violation` 事件能由 `StabilityGuard` 真实触发（I-2 第三次演练）
  - ✅ `DEGRADED_PLAN` 出现在 `runtime.states`（I-3）
  - ✅ `starship/stability_monitor.py` 不依赖 `sre_control/*`（I-1）
- **为什么事件 kind 数量不增加**：`stability_violation` 由 PR-M-04 的 adapter 异常路径
  和 PR-L-01 的监视器触发路径**共享**。用 `stage` 字段区分：`"SignalFusion"` /
  `"PredictiveAutoscaler"` 等是异常路径；`"StabilityGuard/<label>"` 是监视器路径。
  counter-example 保持不变（两个路径都在"不能靠放宽安全路径消化"的原则下）。
- **Evidence**：
  - 代码 `starship/stability_monitor.py`（~170 LOC）
  - 代码 `sre_control/stability_guard.py`（~100 LOC）
  - 代码 `sre_control/stack.py`（+stability stage，~30 LOC）
  - 测试 `tests/test_stability_monitor.py` 7 条 + `test_contracts.py` +1 条
  - 文档 `docs/EVENT_SCHEMA.md` + V2 HTML：`stability_violation` 行加第二个 producer

#### PR-L-02 · docs/knowledge-base.html 换模板

- **Status**: 🔵 PROPOSED
- **背景**：V1 比 V2 缺 5 节（event guide、lifecycle、failure、invariants、handoff）。
- **范围**：用 V2 模板整体重排 V1 HTML。
- **DoD**：V1 与 V2 目录一致；V1 成为 canonical，V2 可以 deprecate 或只保留 diff。

---

## Traceability · PR ↔ 图 ↔ 公式 ↔ 文件 ↔ 测试 ↔ 证据 ↔ commit

### Starship 层（Epic 1-9）

| PR | 图片 | 公式 | 文件 | 测试 | Analysis 证据 | Baseline commit |
| --- | --- | --- | --- | --- | --- | --- |
| PR-1-01 | image-11 | `ṙ=v, v̇=g+Γ/m, z=ln m` | `starship/lossless_convex.py` | `test_lossless_convex.py` | s01 `pos_err 148→2e-6` | `cf9c8dc` |
| PR-1-02 | image-12 | `min −z(T), Γ·n̂ ≥ σ cosθ_max` | 同上 | 同上 | s01 `cone_margin_min>0` | `cf9c8dc` |
| PR-2-01 | image-13 | `δẋ = A(t)δx + B(t)δu` | `starship/scp.py :: linearize` | `test_scp.py`（隐于 s02） | s02 `final_pos_err 8→3` | `cf9c8dc` |
| PR-2-02 | image-14 | SCP iterate + trust region | `starship/scp.py :: SCP` | s02 | s02 收敛曲线 | `cf9c8dc` |
| PR-3-01 | (预备) | Quaternion algebra | `starship/quaternion.py` | `test_quaternion.py` (3) | s03 `quat_norm_drift 1e-12` | `cf9c8dc` |
| PR-3-02 | image-15/16 | `q̇=½Ω(ω)q, ω̇=J⁻¹(τ−ω×Jω)` | `starship/rigid_body.py` | `test_rigid_body.py` (2) | s03 `angle_rmse 0.056→5.7e-7` | `cf9c8dc` |
| PR-4-01 | image-17 | `n̂ᵀu ≥ ‖u‖cosθ, ‖u‖≤T` | `starship/thrust_constraints.py` | `test_thrust_constraints.py` (3) | — | `cf9c8dc` |
| PR-4-02 | image-18 | Cone + ball 闭式投影 | 同上 `ConeQPFilter` | 同上 | s04 `cone_viol 97.4%→0%` | `cf9c8dc` |
| PR-5-01 | image-1 | EKF predict/update | `starship/ekf.py :: EKF` | `test_ekf.py` | s05 | `cf9c8dc` |
| PR-5-02 | image-10 | Radar h/H | `ekf.py :: RadarMeasurement` | 同上 | s05 | `cf9c8dc` |
| PR-5-03 | image-19 | IMU + Fiducial + MultiSensor | `ekf.py` | 同上 | s05 `vel_rmse 481→51` | `cf9c8dc` |
| PR-6-01 | image-2 | ZOH 离散 | `starship/mpc.py :: LinearDiscretizer` | `test_mpc.py` | s06 | `cf9c8dc` |
| PR-6-02 | image-3 | `J=ΣxᵀQx+uᵀRu+x_NᵀPx_N` | `mpc.py :: QuadraticMPC` | 同上 | s06 `final_err 0.012→3e-7` | `cf9c8dc` |
| PR-6-03 | image-4 | Warm-start shift | 同上 `.step()` | 同上 | s06 | `cf9c8dc` |
| PR-7-01 | image-5 | Belly-flop ref | `starship/flip_maneuver.py` | `test_flip_maneuver.py` | s07 | `cf9c8dc` |
| PR-7-02 | image-6 | `τ_net=Σ(l×T)+τ_RCS` | 同上 | 同上 | s07 | `cf9c8dc` |
| PR-7-03 | image-7 | `I·α=τ_net` bang-bang | `flip_maneuver.py :: FlipPlanner` | 同上 | s07 `pitch 36.4°→0°` | `cf9c8dc` |
| PR-8-01 | image.png | Catch geometry | `starship/catch_controller.py :: CatchGeometry` | `test_allocation.py` | s08 | `cf9c8dc` |
| PR-8-02 | image-8 | Bounded LS allocation | `catch_controller.py :: ThrustAllocator` | 同上 | s08 `sat 33.75%→0%` | `cf9c8dc` |
| PR-8-03 | image-9 | Catch controller | `catch_controller.py :: CatchController` | 同上 + demo | `demo_catch_phase.py` | `cf9c8dc` |
| PR-9-01 | — | Pipeline compose | `starship/pipeline.py` | — | `demo_powered_descent.py` | `cf9c8dc` |
| PR-9-02 | — | JSONL trace | 同上 | — | trace output | `cf9c8dc` |
| PR-9-03 | — | pytest + CI | `tests/*.py` | 33 passed | — | `cf9c8dc` |

### SRE 翻译层（Epic 10）

| PR | 对应支柱 | 文件 | 测试 | Event kind | Commit |
| --- | --- | --- | --- | --- | --- |
| PR-10-01 | §1 | `sre_control/pool_planner.py` | `test_sre_control.py::test_pool_*` (2) | `pool_capacity_clipped` | `d9cecb7` |
| PR-10-02 | §2 | `canary_scheduler.py` | `test_canary_*` (2) | `rollout_rejected` | `2c82861` |
| PR-10-03 | §3 | `topology_state.py` | `test_topology_*` (2) | `topology_state_repaired` | `d9cecb7` |
| PR-10-04 | §4 | `slo_guardrail.py` | `test_guardrail_*` (2) | `unsafe_proposal_projected` | `5e0a94e` |
| PR-10-05 | §5 | `signal_fusion.py` | `test_signal_fusion_*` (2) | `missing_sensor` | `5e0a94e` |
| PR-10-06 | §6 | `predictive_autoscaler.py` | `test_autoscaler_*` (2) | `replica_bound_active` | `2c82861` |
| PR-10-07 | §7 | `fast_switcher.py` | `test_switcher_*` (2) | `deadline_exceeded` | `2c82861` |
| PR-10-08 | §8 | `weighted_balancer.py` | `test_balancer_*` (1) | `bounded_ls_residual` | `5e0a94e` + `4319a41` |
| PR-10-09 | all | `stack.py` | `test_contracts.py` (5) | 汇总 DEGRADED_* | `70c1d6a` + `41cdea8` |

### 可观测性 + 契约（Epic 11-12）

| PR | 文档 | 代码/测试 | Commit |
| --- | --- | --- | --- |
| PR-11-01 | `docs/EVENT_SCHEMA.md` | `sre_control/events.py` + `test_event_schema.py` (2) | `1ee8ae5` |
| PR-11-02 | `docs/RUNTIME_STATES.md` | `stack.py` runtime 字段 | `70c1d6a` + `41cdea8` |
| PR-11-03 | 同上 | 8 个 adapter 的 events | `5e0a94e` / `2c82861` / `d9cecb7` |
| PR-12-01 | `docs/API_CONTRACTS.md` | — | `4319a41` |
| PR-12-02 | `docs/RUNTIME_STATES.md` | — | `4319a41` |
| PR-12-03 | — | `test_contracts.py` (5) | `4319a41` + `41cdea8` |
| PR-12-04 | `docs/EQUATION_DEEP_DIVE.md` | — | `e2658f6` |

### 移交包（Epic 13）

| PR | 产物 | Commit |
| --- | --- | --- |
| PR-13-01 | `docs/claude-review/` 6 件套 | `59389ee` |
| PR-13-02 | `docs/V2_Knowledge/knowledge-base.html` + assets | `e2658f6` |
| PR-13-03 | 刷新 `docs/CODEX_HANDOFF.md` | `e2658f6` |

---

## Spec ↔ Triage · 两端反馈循环

> **谁在读 spec？** 人类 reviewer + 各种 agent（Codex/Claude/future agents）。
>
> **谁在修 spec？** 任何在本工程推进一步的 agent，修完自己那步后同时更新 spec。

观察：截至 v0.3.2，spec 已经演化出一套稳定的两端协议：

```
                   +-------------------+
                   |  PR-REQUIREMENTS  |
                   |  (single source   |
                   |   of truth)       |
                   +---+--------+------+
                       |        ^
     Claude refine     |        |     Codex triage
     (加 Backlog)       |        |     (挑 PROPOSED 实施)
                       v        |
              +--------+--------+------+
              |  docs/claude-review/   |
              |  · REVIEW              |
              |  · DETAILED_ARCH       |
              |  · EVENT_LIFECYCLE     |
              |  · FAILURE_MODES       |
              |  · HANDOFF_CHECKLIST   |
              |  · CODEX_TRIAGE  ←新增 |
              +------------------------+
                       |
                       v
                实际代码 / 测试 / 证据
```

- Claude 负责**纵向深入 + 打回点整理**：产出 `docs/claude-review/` 6 件套。
- Codex 负责**横向清单化 + 逐项推进**：产出 `CODEX_TRIAGE.md` 把 review 变成可执行队列。
- Spec 本身（本文件）是两端共同的**状态账本**：
  - Backlog 节是"接下来做什么"
  - Traceability 是"过去做了什么"
  - Invariants 是"永远不能违反什么"
  - Change Log 是"何时由谁推进了什么"

**反面案例**（未来 agent 可能犯的错）：
- 只改代码不更新 spec → spec 和现实脱节
- 只改 spec 不同步 claude-review / CODEX_TRIAGE → 下一轮 agent 看到矛盾
- 在 HANDOFF / checklist 里写"HEAD 必须 = `<某 SHA>`"（违反 I-4）→ 每次新 commit 都过期

**验收本循环健康的信号**：

1. `git log --oneline` 里的 commit 顺序是 `spec refine → code/test → triage update → spec sync` 交替。
2. Backlog 节的 🔵 条目数量单调下降（PROPOSED 逐轮被拉走变 ✅）。
3. Change Log 每条 entry 都能链回具体 commit SHA 和被改动的 Backlog PR。
4. `docs/claude-review/CODEX_TRIAGE.md` 的打回项 triage 表第 3 列（当前状态）最终都变成"已修"。

**当前循环健康度**：

- v0.3.0 → v0.3.1：Codex 在 `dd9cd7a` 里一口气拉走 PR-S-01 和 PR-M-01，并新建 `CODEX_TRIAGE.md` 把剩余工作队列化。✅
- v0.3.1 → v0.3.2：Claude 本次把 `CODEX_TRIAGE.md §4 文档漂移` 升格为 I-4 不变量，并把 PR-M-02 按 Codex 推荐的细节展开成可拉取的清单。✅
- 下一步期望：Codex 或其他 agent 拉取 PR-M-02，并产出 `analysis/s10_failure_trace.py`。

---

## Change Log

### v0.3.7 · 2026-05-12 · Claude Reviewer（PR-L-01 · Lyapunov 落地）

- **PR-L-01 SHIPPED**（本轮 commit）：完成 §2.1 Lyapunov 红线的代码化落地。
  这是本 session 首个跨层 PR，同时新增 `starship/` 和 `sre_control/` 模块。
- **新模块 `starship/stability_monitor.py`**：通用 `V(x)` 监视器，`n` 维状态 ×
  任意标量 Lyapunov 候选。不依赖 `sre_control/`（I-1）。
- **新模块 `sre_control/stability_guard.py`**：薄包装，把物理层 `triggered` 翻译成
  `stability_violation` event。**无需新 event kind**——和 PR-M-04 共享。
- **`SREControlStack` 扩展**：加 optional `stability` 字段，在 OBSERVE 与 PLAN 之间
  跑一次；触发即补 `DEGRADED_PLAN`。向后兼容（default `None`）。
- **第三次演练 I-2 全套同步**：这次是"复用已有 kind 但扩展合法 producer 集合"的
  变种，schema 不变但需要更新 doc 索引表的 `producer` 列。
- **quality gate**：`pytest` 43 → **51 passed**（+8 条）；event kind 数保持 10；
  `analysis.run_all` 仍 10 studies。
- **Backlog 剩余从 2 降到 1**（只剩 PR-L-02 V1 HTML 重排）。

### v0.3.6 · 2026-05-12 · Claude Reviewer（清空小档 Backlog）

- **PR-S-02 SHIPPED**：`API_CONTRACTS.md §2.9 CatchController` 顶部加"属 starship 物理
  层"note，引用 I-1 不变量。
- **PR-S-03 SHIPPED**：`ARCHITECTURE.md §4.5` 第 5 条改为"已搬移"指针；
  `CODEX_HANDOFF.md` 成为 CatchController wrapper 建议的 single source。
- 无代码改动。Backlog 从 3 条降到 **2 条**（都是大档 cross-session，PR-L-01/PR-L-02）。

### v0.3.5 · 2026-05-12 · Claude Reviewer（PR-M-04 · 不变量升格到 5 条）

- **PR-M-04 SHIPPED**（本轮 commit）：`SREControlStack.step()` 5 个阶段全部包进
  try/except，adapter 抛异常转为 `stability_violation` event + 安全回退，不再崩栈。
- **I-5 升格为不变量**：与 I-2 / I-3 并列，任何未来修改 stack 都必须保持"异常不崩栈 +
  转事件 + 回退"三件事同步。
- **第二次演练 I-2 全套同步**：这次是带着 PR-M-03 的经验，schema 封闭测试在第一次
  `git run` 就发红，立刻修补路径——比上一轮更丝滑。
- **quality gate**：`pytest` 41 → **43 passed**；event kind 数 9 → **10**。
- **Backlog 剩余从 4 降到 3**。

### v0.3.4 · 2026-05-12 · Claude Reviewer（PR-M-03 · 首次走完 I-2 全套同步）

- **PR-M-03 SHIPPED**（本轮同一 commit）：SignalFusion innovation gating。
  这是本工程**首次**新增 runtime event kind，因此完整走了一遍 I-2 流程作为模板：
  1. `EVENT_COUNTEREXAMPLES` 加 `outlier_rejected`
  2. adapter 代码路径真实触发
  3. `tests/test_event_schema.py` 扩展 `_collect_local_events` 以触发新 kind
  4. `docs/EVENT_SCHEMA.md` + V2 HTML 索引表同步
- **过程证据**：我加了 `EVENT_COUNTEREXAMPLES` 条目但忘了让它被真实触发时，
  `test_all_runtime_events_follow_shared_schema` 立刻红灯——这正是 I-2 守护成功的案例。
- **API 变化**：`starship/ekf.py::EKF.update` 签名从 `-> None` 变成 `-> dict`。
  唯一生产调用者 `SignalFusion` 已同步；`analysis/s05_ekf.py` 忽略返回值仍工作。
- **quality gate**：`pytest` 39 → **41 passed**；event kind 数 8 → **9**。

### v0.3.3 · 2026-05-12 · Claude Reviewer（自封闭 PR-M-02）

- **PR-M-02 SHIPPED**（本轮同一 commit）：Claude 拉取自己上轮写的 spec，实现
  `analysis/s10_failure_trace.py` (280 LOC) + `tests/test_failure_trace.py` (4 tests) +
  3 件证据（density PNG / co-occurrence heatmap / JSONL sample）+ V2_Knowledge 嵌入。
- **quality gate 升级**：`pytest` 35 → **39 passed**；`analysis.run_all` 9 → **10 studies**。
- **证据级别升级**：SRE 栈除了"控制效果变好"的 9 条证据，现在多了 1 条"可观测性
  本身"的数值证据。Before: `0 events` / After: `83 events, 4 distinct kinds`。
- **反馈循环再证明**：Claude 写 spec → Codex triage → Claude 回填 spec + 写测试 + 补证据。
  Backlog 的 🔵 条目在两轮里减了 3 条（PR-S-01 / PR-M-01 / PR-M-02）。

### v0.3.2 · 2026-05-12 · Claude Reviewer（吸收 Codex triage）

- **新增 I-4 不变量**：文档不得钉死 HEAD commit SHA（来源 `CODEX_TRIAGE.md §4`，
  Codex 在 `dd9cd7a` 里已把 `HANDOFF_CHECKLIST.md` / `V2_Knowledge/knowledge-base.html`
  按此规则修正）。
- **PR-M-02 大幅展开**：从 1 段模糊建议升级为"150 行 Python + 3 件证据 + SUMMARY 新条目"
  的可拉取清单，含反面案例和依赖声明。
- **新增 Spec ↔ Triage 反馈循环节**：显式描述 Claude（纵向深入）+ Codex（横向清单化）
  + Spec（状态账本）三端协议，并给出健康度验收信号。
- **quality gate 注脚更新**：`analysis.run_all` 目前 9 studies，PR-M-02 合并后 → 10。
- head-commit 维持 `dd9cd7a`；本轮无代码改动。

### v0.3.1 · 2026-05-12 · 同步 Codex 下轮产出

- **PR-S-01** 状态 `🔵 PROPOSED → ✅ SHIPPED`（commit `dd9cd7a`）：counter-example 签名
  放宽为 `startswith(("Do not", "Avoid"))`。
- **PR-M-01** 状态 `🔵 PROPOSED → ✅ SHIPPED`（commit `dd9cd7a`）：新增
  `tests/test_import_graph.py` 用 AST 固化依赖方向护栏。
- quality gate 从 33 passed → **35 passed**。
- head-commit 从 `e2658f6` → `dd9cd7a`。

这说明 spec 的 Backlog 节本身就是可执行的任务列表——Codex 已经照清单做了 2 项。

### v0.3.0 · 2026-05-12 · Claude Reviewer

**重大改动**：

- 加 YAML front-matter（version / status legend / invariants / quality gates）
- 给现有 21 个 PR（Epic 1-9）打 `Status: ✅ SHIPPED` + `Evidence` 三字段
- **新增 Epic 10-13**（retroactive）：把已交付但没进 spec 的 SRE 翻译层 / 可观测性 /
  契约 / 移交包补齐，共 15 个 PR 记录
- 新增 **NFR** 章节：6 条非功能需求 + 3 条不变量 + 依赖图护栏
- 新增 **Refine Loop** 章节：固化我们用的 6 步推进法 + 6 个必答问题 + 验收准则
- 新增 **Backlog** 章节：8 条 PROPOSED PR 分小/中/大档
- **升级 Traceability**：PR ↔ 图 ↔ 公式 ↔ 文件 ↔ 测试 ↔ 证据 ↔ commit 七列表格
- 新增本 **Change Log**

**未触碰**：代码（`starship/` / `sre_control/`）、`analysis/`、`tests/`。

**向后兼容**：v0.2 的 21 PR 编号保持不变；新增编号 `PR-10-*` 起。

### v0.2.0 · 2026-05-11 · Codex

- 追加 SRE 映射说明（但未正式分 PR）
- 刷新数值 Evidence（EKF 速度 RMSE、SRE 栈 SLO%）

### v0.1.0 · 2026-05-10 · Claude

- 初始版本：9 个 Epic / 21 个 PR（图-公式-代码三向追溯）

---

## 附录 A · Quick Lookup

- **图片 → PR**：见 [Traceability](#traceability--pr--图--公式--文件--测试--证据--commit) 的"Starship 层"表第 2 列。
- **PR → 文件**：第 4 列。
- **PR → commit SHA**：最后一列。
- **PR → Analysis 证据**：第 6 列，直接对应 `analysis/sXX_*.py` 脚本名。
- **Event kind → PR**：[SRE 翻译层表](#sre-翻译层epic-10)第 5 列。

## 附录 B · 外部参考

- 黄大年茶思屋·芮博数理工场·结构智能专栏（原文 OCR 截图在 `DOC/spacex/`）
- Behçet Açıkmeşe & Scott Ploen · *Convex Programming Approach to Powered Descent
  Guidance for Mars Landing* (JGCD 2007) — §1 Lossless Convexification 的数学依据
- Malyuta, Reynolds, Szmuk et al. · *Convex Optimization for Trajectory Generation*
  (Annual Reviews in Control 2022) — §2 SCP 的现代综述
- Ames, Coogan, Egerstedt et al. · *Control Barrier Functions* (ECC 2019) — §4 锥
  约束的 CBF 视角（非本仓库选用但值得参考）

## 附录 C · 不是这个 spec 管的东西

- **真实 SpaceX 实现**：本仓库只是依据公开材料的工程复现，不代表任何内部算法。
- **生产级 GNC**：不含实时 RTOS / 冗余通信 / 故障树分析。
- **ML/LLM-driven policy learning**：`nn_proposal` 接口存在但不提供学习管线。
- **完整 SRE 控制平面**：`SREControlStack` 是编排骨架，不是 Kubernetes operator
  或 Envoy filter。
