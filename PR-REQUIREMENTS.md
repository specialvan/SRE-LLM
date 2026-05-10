# PR 级功能需求清单 — 星舰筷子塔回收

把 [`DOC/spacex/`](../DOC/spacex/) 19 张公式示意图逐项翻译成可独立交付的 PR。
每个 PR 都有：**背景 → 范围 → 公式/引用 → DoD（Definition of Done）→ 文件**。
颗粒度按 "1 张图 = 1 个 PR、1~2 天、≤400 行代码" 切分。

> 命名规约：`PR-<section>-<seq>: <短标题>`
> 例：`PR-1-01: 无损凸化 PDG 问题构造`
>
> 章节与图片的映射（按图片文件名）：
>
> | § | 主题 | 图片 |
> | --- | --- | --- |
> | 1 | Lossless Convexification | image-11, image-12 |
> | 2 | Successive Convex Programming | image-13, image-14 |
> | 3 | 6-DoF Rigid Body on SO(3) | image-15, image-16 |
> | 4 | Thrust Pointing Constraint | image-17, image-18 |
> | 5 | EKF 传感器融合 | image-1, image-10, image-19 |
> | 6 | MPC 滚动时域 | image-2, image-3, image-4 |
> | 7 | Belly-Flop / Landing-Flip | image-5, image-6, image-7 |
> | 8 | Chopstick-catch 推力分配 | image.png, image-8, image-9 |

---

## Epic 1 · 无损凸化 (Lossless Convexification)

### PR-1-01 · 动力下降 PDG 问题结构 (`image-11`)
- **背景**：原图 `image-11` 展示了 Starship 下降段"无损凸化"的问题框架：把原本含
  `ρ1 ≤ ‖Γ‖ ≤ ρ2` 的非凸推力下界松弛成凸问题。
- **范围**：
  - `LosslessPDG` 数据类：初始/终止状态、重力、Isp、ρ1/ρ2、θ_max、时间网格。
  - `assemble()` 返回决策变量、线性动力学约束、指向锥约束与目标。
  - 对数质量变换 `z = ln m` 以避免 `Γ/m` 非线性。
- **公式**：`ṙ = v`，`v̇ = g + Γ/m`，`ṁ = −‖Γ‖ / (Isp g0)`，`z = ln m`。
- **DoD**：
  - 最小规模问题（N=20）能在 100 ms 内组装完成并求解到 KKT 容差 ≤1e-4。
  - 求解得到的 `‖Γ_k‖ ∈ [ρ1, ρ2]` 自然恢复（松弛紧）。
- **文件**：`starship/lossless_convex.py`、`tests/test_lossless_convex.py`。

### PR-1-02 · 最小燃耗代价函数 (`image-12`)
- **背景**：`image-12` 补充 `min −z_N s.t. ḟ = g + Γ/m, Γ·n̂ ≥ σ·cos θ_max`。
- **范围**：
  - 代价 `min −z(T)` ↔ 最大化末端质量。
  - `solve()` 返回 `(trajectory, thrust_profile, status, objective)`。
  - 求解器：scipy `linprog` 的 SOCP 替代（使用 scipy 的 `minimize` 内点法）；若用户装
    了 cvxpy 则自动切换。
- **DoD**：
  - 给定无大气重力场景，得到的轨迹在末态位置/速度误差 ≤ 1 m / 1 m·s⁻¹。
  - 不依赖 cvxpy 也能跑（scipy-only 回退）。
- **文件**：`starship/lossless_convex.py` 中 `LosslessPDG.solve()`。

---

## Epic 2 · Successive Convex Programming

### PR-2-01 · 参考轨迹线性化 (`image-13`)
- **背景**：`image-13` 给出 `δẋ = A(t)δx + B(t)δu, ‖δx‖ ≤ ε`。
- **范围**：
  - `linearize(traj_ref, dynamics)` 返回 `(A_k, B_k, c_k)` 序列。
  - 支持 6-DoF 刚体动力学（§3）和简化 3-DoF 质点动力学。
  - 数值雅可比回退：`scipy.optimize.approx_fprime`。
- **DoD**：
  - 单步线性化误差 `‖f(x+δx, u+δu) − f(x,u) − Aδx − Bδu‖ = O(‖δ‖²)`。
- **文件**：`starship/scp.py` 中 `linearize()`。

### PR-2-02 · 置信域 SCP 主循环 (`image-14`)
- **背景**：`image-14` 强调"迭代：δx→0 收敛"。
- **范围**：
  - `SCP.iterate(x0, N, max_iters=10)`：
    1. 初猜参考轨迹（直线或上一次解）；
    2. 线性化得到凸子问题；
    3. 求解 QP（带 trust-region `‖δx‖_∞ ≤ η_x`, `‖δu‖_∞ ≤ η_u`）；
    4. 动态调整 `η`：改进比 ρ>0.7 放大、ρ<0.1 缩小。
  - 终止条件：`‖x^{k+1}−x^k‖ < ε_tol` 或超出 `max_iters`。
- **DoD**：
  - 软/硬着陆标准测试能在 ≤6 轮收敛。
  - 给出收敛历史日志（可选 JSON 输出）。
- **文件**：`starship/scp.py` 中 `SCP` 类。

---

## Epic 3 · 6-DoF 刚体动力学

### PR-3-01 · 四元数工具箱 (`image-15` 预备)
- **背景**：SO(3) 上的姿态必须用单位四元数避免欧拉角奇异。
- **范围**：
  - `Quaternion` 数据类：`w, x, y, z`。
  - `mul`、`conj`、`normalize`、`to_matrix`、`from_axis_angle`、`Omega(ω)`。
  - 指数映射 `exp(½·ω·dt)` 用于离散积分。
- **DoD**：
  - 四元数乘法与 `scipy.spatial.transform.Rotation` 一致，误差 ≤1e-12。
- **文件**：`starship/quaternion.py`、`tests/test_quaternion.py`。

### PR-3-02 · 6-DoF 动力学 `q̇/ω̇/ṙ/v̇` (`image-15`, `image-16`)
- **背景**：`image-15/16` 给出 `q̇=½Ω(ω)q`, `ω̇ = I⁻¹(τ − ω×Jω)`。
- **范围**：
  - `State6DOF` 数据类：`r (3,), v (3,), q (4,), ω (3,), m (scalar)`。
  - `RigidBody.f(state, force_body, torque_body)` 返回 `dstate/dt`。
  - RK4 积分 `step(state, wrench, dt)`，四元数事后归一化。
- **DoD**：
  - 零力矩自由落体 2 s 后位置误差 ≤1e-6 m；角动量守恒 ≤1e-8。
  - 纯绕 z 轴力矩产生的姿态与解析积分一致。
- **文件**：`starship/rigid_body.py`、`tests/test_rigid_body.py`。

---

## Epic 4 · 推力指向 / 幅值约束

### PR-4-01 · 推力器与约束定义 (`image-17`)
- **背景**：`image-17` 要求 `n̂ᵀu ≥ ‖u‖ cos θ_max, ‖u‖ ≤ T_max`。
- **范围**：
  - `Thruster` 数据类：`position_body (3,)`, `direction_body (3,)`, `T_min`,
    `T_max`, `theta_max_deg`。
  - `ThrusterBank` 管理多台 Raptor：默认 3 台布置在底部 120°。
  - `assemble_pointing_cone(u, n_hat, theta_max)` 返回凸约束表达（callable）。
- **DoD**：
  - 给定任意 `u` 满足锥约束时约束函数返回 ≥0；违反时 <0。
- **文件**：`starship/thrust_constraints.py`。

### PR-4-02 · 锥+幅值约束的 QP 滤波器 (`image-18`)
- **背景**：把 `u_nom` 投影到锥约束 & 幅值约束上。
- **范围**：`ConeQPFilter.filter(u_nom)` 求解：
  ```
  min ‖u − u_nom‖²
  s.t. ‖u‖ ≤ T_max,  n̂ᵀu ≥ ‖u‖ cos θ_max
  ```
  采用"先幅值裁剪再锥投影"的解析解以免调 QP。
- **DoD**：
  - 锥外输入被矫正至锥边；锥内输入不变；解析解与数值解差 ≤1e-8。
- **文件**：`starship/thrust_constraints.py`。

---

## Epic 5 · EKF 多源传感器融合

### PR-5-01 · EKF 骨架 (`image-1`)
- **背景**：`image-1` 给出经典 EKF 更新式：
  `x̂_{k|k} = x̂_{k|k−1} + K_k(z_k − h(x̂_{k|k−1}))`。
- **范围**：
  - `EKF` 类：`predict(u, dt)`, `update(z, h, H, R)`.
  - 状态向量 `x ∈ R^13`：`[r, v, q, ω]`，过程噪声 `Q` 为块对角。
  - Jacobian 支持解析或 `scipy.optimize.approx_fprime` 数值回退。
- **DoD**：
  - 1-D 自由落体小型测试里 RMSE 随量测噪声线性变化。
- **文件**：`starship/ekf.py`、`tests/test_ekf.py`。

### PR-5-02 · 雷达量测模型 (`image-10`)
- **背景**：`image-10` 标注 "雷达" 通道，量测量为方位/距离。
- **范围**：
  - `RadarMeasurement`：`h(x) = [‖r−p_tower‖, atan2(ry, rx), atan2(rz, ‖r_xy‖)]`。
  - 解析 Jacobian。
- **DoD**：
  - 与数值雅可比差 ≤1e-6。
- **文件**：`starship/ekf.py` 中 `RadarMeasurement`.

### PR-5-03 · IMU + 塔架视觉 Fiducial 融合 (`image-19`)
- **背景**：`image-19` 强调多源融合——塔架视觉标志 (fiducial markers) 与 IMU 并网。
- **范围**：
  - `IMUMeasurement`：量测 `ω` 与比力 `a_body = R(q)ᵀ(v̇ − g)`。
  - `FiducialMeasurement`：塔架上若干已知位置的 AprilTag，量测 = 相机像素坐标。
  - `MultiSensorEKF.step(sensors, dt)` 逐源做 measurement update。
- **DoD**：
  - 雷达失效 1 s 内仅用 IMU+视觉也能把位置 drift 控制在 1 m 以内。
- **文件**：`starship/ekf.py`.

---

## Epic 6 · MPC 滚动时域

### PR-6-01 · 线性离散化 (`image-2`)
- **背景**：`image-2` 展示 MPC 的滚动时域图示。
- **范围**：
  - `LinearDiscretizer.discretize(A, B, dt)`：零阶保持 `A_d = e^{A·dt}`。
  - 对 6-DoF 刚体先在当前工作点做 Jacobian 线性化再 ZOH。
- **DoD**：
  - `A_d`, `B_d` 与 `scipy.signal.cont2discrete` 一致。
- **文件**：`starship/mpc.py`.

### PR-6-02 · 二次 MPC 代价 + 终端代价 (`image-3`)
- **背景**：`image-3` 公式 `J = Σ(x^T Q x + u^T R u) + x_N^T P x_N`。
- **范围**：
  - `QuadraticMPC.__init__(Q, R, P, N, ...)`.
  - `solve(x0)` 组装稠密 QP：`min ½zᵀHz + gᵀz s.t. Az≤b`.
  - 使用 `scipy.optimize.minimize(method='SLSQP')` 或自带 Gauss-Newton 回退。
- **DoD**：
  - 测试：双积分器系统在 20 步内把位置/速度收敛到 ≤1e-3。
- **文件**：`starship/mpc.py`、`tests/test_mpc.py`.

### PR-6-03 · 热启动与执行 u₀ (`image-4`)
- **背景**：`image-4` 展示实时滚动。
- **范围**：
  - `QuadraticMPC.step(x0)`：返回 `u_0`，记录上次 `U_prev` 作为下次热启动。
  - Shift-and-append：`U_warm = [U_prev[1:], U_prev[-1]]`。
  - 结构化日志：每步输出 `{x0, u0, J, solver_iter, solve_ms}` JSONL。
- **DoD**：
  - 热启动平均迭代数下降 ≥30%。
- **文件**：`starship/mpc.py`.

---

## Epic 7 · Belly-Flop → Landing-Flip

### PR-7-01 · Belly-flop 气动参考 (`image-5`)
- **背景**：`image-5` 示意大迎角扁体气动下落状态。
- **范围**：
  - `bellyflop_reference(altitude, target)` 返回名义四元数（箭体水平，腹部朝下）。
  - 空气阻力简化模型 `F_drag = −½ ρ C_d A ‖v‖ v`（用于 MPC 预测）。
- **DoD**：
  - 给定高度/末速，参考姿态连续、模值 1 误差 ≤1e-9。
- **文件**：`starship/flip_maneuver.py`.

### PR-7-02 · 力矩合成 τ_net (`image-6`)
- **背景**：`image-6` 公式 `τ_net = Σ(l_i × T_i) + τ_RCS`。
- **范围**：`net_torque(thrusters, T_cmds, rcs_cmd)` 返回 `τ_body ∈ R³`。
- **DoD**：单元测试验证矩臂×推力叉积方向。
- **文件**：`starship/flip_maneuver.py`.

### PR-7-03 · Landing-flip 规划 (`image-7`)
- **背景**：`image-7` 公式 `I·α = τ_net` — 由水平姿态在 5~7 s 内翻至垂直。
- **范围**：
  - `FlipPlanner.plan(state0, t_span, I, theta_max)` 生成一个 bang-bang 或最小时间
    翻转参考：满推力俯仰加速 → 反推减速。
  - 输出参考 `(q_ref(t), ω_ref(t))` 供 MPC 跟踪。
- **DoD**：
  - 末态俯仰角误差 ≤2°、角速度 ≤5°/s（开环仿真）。
- **文件**：`starship/flip_maneuver.py`、`tests/test_flip_maneuver.py`.

---

## Epic 8 · 塔架机械臂捕获段

### PR-8-01 · 捕获段坐标系 & 对接窗口 (`image.png`)
- **背景**：首图给出"chopstick"塔架几何：两根机械臂之间的捕获窗口。
- **范围**：
  - `CatchGeometry` 数据类：塔架位置、机械臂开合宽度、垂直捕获高度。
  - `lateral_window(altitude)`：返回允许的横向偏差（随高度线性收窄）。
- **DoD**：
  - 给定典型参数 (height=150 m, width=5 m)，窗口函数单调递减。
- **文件**：`starship/catch_controller.py`.

### PR-8-02 · 多推力器冗余分配 (`image-8`)
- **背景**：`image-8` 暗示 3 台 Raptor 同时工作，需要最小二乘分配。
- **范围**：
  - `allocate(T_demand, τ_demand, bank)` 解
    `min ‖A·t − [F; τ]‖²  s.t.  t_min ≤ t ≤ t_max`
    其中 `A` 是 6×N 的几何矩阵。
  - 使用 `scipy.optimize.lsq_linear`。
- **DoD**：
  - 3 台推力器需求 (F_demand, τ_demand) 可重构误差 ≤1e-6。
- **文件**：`starship/catch_controller.py`.

### PR-8-03 · 捕获段主控制器 (`image-9`)
- **背景**：`image-9` 给最终公式
  `T_total = Σ T_i(1 + W_off(t)) + W_att = A·thrust`。
- **范围**：
  - `CatchController.step(state_est, ref, dt)`：
    1. 计算横向误差 → 姿态指令
    2. 调 `allocate` 得到每台 Raptor 推力
    3. 饱和限制 + 速率限制
  - 与 MPC 结合：外环 MPC 规划 `(F_demand, τ_demand)`，内环 `allocate` 再分配。
- **DoD**：
  - `examples/demo_catch_phase.py` 模拟 50 m→0 m 下降，末态位置误差 ≤0.5 m，姿态
    误差 ≤2°。
- **文件**：`starship/catch_controller.py`、`tests/test_catch_controller.py`、
  `examples/demo_catch_phase.py`.

---

## Epic 9 · 端到端装配与回归

### PR-9-01 · Pipeline 串联 EKF → MPC → 分配
- **背景**：把 §5/§6/§8 装成 20 Hz 主循环。
- **范围**：`pipeline.RecoveryPipeline.step(sensors)` 返回 `thrust_commands`.
- **DoD**：`examples/demo_powered_descent.py` 能跑通一次从 10 km 高度到塔架捕获的
  全链路仿真，末态位置误差 ≤1 m。

### PR-9-02 · 可观测性 trace
- **背景**：工业级系统要审计。
- **范围**：每步输出 JSONL 行：`{t, x̂, u_cmd, T_i, θ_cone_margin, solve_ms}`；可直接
  `pandas.read_json(lines=True)`.
- **DoD**：一次 demo 跑完产出 `trace.jsonl`，字段齐全。

### PR-9-03 · 单元测试 & CI
- **范围**：
  - 每个 Epic 至少一组 pytest；
  - `pytest -q` 全绿，覆盖率 ≥70%。
- **DoD**：
  - 本地 `pytest` 通过；GitHub Actions 可选。

---

## 附录 · PR ↔ 图片 / 公式双向追溯

| PR | 图片 | 关键词 / 公式 |
| --- | --- | --- |
| PR-1-01 | image-11 | Lossless convexification framework |
| PR-1-02 | image-12 | `min −z_N  s.t. Γ·n̂ ≥ σ cosθ_max` |
| PR-2-01 | image-13 | `δẋ = Aδx + Bδu,  ‖δx‖ ≤ ε` |
| PR-2-02 | image-14 | SCP iteration loop |
| PR-3-01 | (预备) | Quaternion tool |
| PR-3-02 | image-15 / image-16 | `q̇ = ½Ω(ω)q,  ω̇ = I⁻¹(τ − ω×Jω)` |
| PR-4-01 | image-17 | `n̂ᵀu ≥ ‖u‖ cosθ_max,  ‖u‖ ≤ T` |
| PR-4-02 | image-18 | Cone + magnitude QP filter |
| PR-5-01 | image-1 | EKF skeleton |
| PR-5-02 | image-10 | Radar measurement |
| PR-5-03 | image-19 | IMU + fiducial fusion |
| PR-6-01 | image-2 | Linear discretization (ZOH) |
| PR-6-02 | image-3 | `J = Σ xᵀQx + uᵀRu + xNᵀPxN` |
| PR-6-03 | image-4 | Receding horizon warm start |
| PR-7-01 | image-5 | Belly-flop reference |
| PR-7-02 | image-6 | `τ_net = Σ(l_i × T_i) + τ_RCS` |
| PR-7-03 | image-7 | `I·α = τ_net` Landing flip |
| PR-8-01 | image.png | Catch geometry & window |
| PR-8-02 | image-8 | Multi-thruster allocation |
| PR-8-03 | image-9 | `T_total = Σ T_i(1+W_off)+W_att = A·thrust` |
