# Formula ↔ Code Map

每条公式的出处、数学形式、对应源码位置一一列出。

## §1 Lossless Convexification (PDG)

| 公式 | 数学形式 | 源码 |
| --- | --- | --- |
| 位置 ODE | `ṙ = v` | `lossless_convex.py :: _assemble_dynamics_constraints()` |
| 速度 ODE | `v̇ = g + Γ/m` | 同上 |
| 质量 ODE (对数变换) | `ż = −‖Γ‖/(Isp·g0·m)` | `lossless_convex.py :: _log_mass_ode()` |
| 推力幅值松弛 | `ρ1 ≤ σ ≤ ρ2`, `‖Γ‖ ≤ σ` | `lossless_convex.py :: _assemble_thrust_bounds()` |
| 推力指向锥 | `Γ·n̂ ≥ σ cos θ_max` | `thrust_constraints.py :: pointing_cone_constraint()` |
| 目标 | `min −z(T)` 即 `max m(T)` | `lossless_convex.py :: LosslessPDG.cost()` |

## §2 Successive Convex Programming

| 公式 | 数学形式 | 源码 |
| --- | --- | --- |
| 线性化 | `δẋ = A(t)δx + B(t)δu` | `scp.py :: linearize()` |
| 置信域 | `‖δx‖∞ ≤ η_x`, `‖δu‖∞ ≤ η_u` | `scp.py :: SCP._trust_region()` |
| 收敛判据 | `‖x^{k+1}−x^k‖ < ε` | `scp.py :: SCP.iterate()` |

## §3 6-DoF Rigid Body on SO(3)

| 公式 | 数学形式 | 源码 |
| --- | --- | --- |
| 四元数运动学 | `q̇ = ½ Ω(ω) q` | `rigid_body.py :: RigidBody.f()` |
| 欧拉动力学 | `ω̇ = J⁻¹(τ − ω × J ω)` | 同上 |
| 平动 | `ṙ = v, v̇ = g + (1/m)R(q)F_body` | 同上 |
| RK4 积分 | `x_{k+1} = RK4(f, x_k, u_k, dt)` | `rigid_body.py :: RigidBody.step()` |

## §4 Thrust Pointing Constraint

| 公式 | 数学形式 | 源码 |
| --- | --- | --- |
| 幅值约束 | `‖u‖ ≤ T_max` | `thrust_constraints.py :: magnitude_bound()` |
| 指向锥 | `n̂ᵀu ≥ ‖u‖ cos θ_max` | `thrust_constraints.py :: pointing_cone_constraint()` |
| 解析投影 | argmin ‖u − u_nom‖² on cone | `thrust_constraints.py :: ConeQPFilter.filter()` |

## §5 EKF Sensor Fusion

| 公式 | 数学形式 | 源码 |
| --- | --- | --- |
| Predict | `x̂_{k|k−1} = f(x̂_{k−1|k−1}, u)` | `ekf.py :: EKF.predict()` |
| Covariance predict | `P_{k|k−1} = F P F^T + Q` | 同上 |
| Innovation | `y_k = z_k − h(x̂)` | `ekf.py :: EKF.update()` |
| Kalman gain | `K = P Hᵀ (H P Hᵀ + R)⁻¹` | 同上 |
| State update | `x̂_{k|k} = x̂_{k|k−1} + K y` | 同上 |
| Radar model | `h(x) = [range, az, el]` | `ekf.py :: RadarMeasurement` |
| Fiducial model | 针孔相机 `z = π(K (R(q)(P−r)))` | `ekf.py :: FiducialMeasurement` |

## §6 Model Predictive Control

| 公式 | 数学形式 | 源码 |
| --- | --- | --- |
| 代价 | `J = Σ(xᵀQx + uᵀRu) + x_NᵀP x_N` | `mpc.py :: QuadraticMPC._cost()` |
| 离散动力学 | `x_{k+1} = A_d x_k + B_d u_k` | `mpc.py :: LinearDiscretizer.zoh()` |
| 输入界 | `u_min ≤ u ≤ u_max` | `mpc.py :: QuadraticMPC._bounds()` |
| 滚动执行 | 仅施加 `u_0`，再 shift | `mpc.py :: QuadraticMPC.step()` |

## §7 Belly-Flop / Landing-Flip

| 公式 | 数学形式 | 源码 |
| --- | --- | --- |
| 合成力矩 | `τ_net = Σ(l_i × T_i) + τ_RCS` | `flip_maneuver.py :: net_torque()` |
| 角加速度 | `I·α = τ_net − ω × J ω` | `rigid_body.py :: RigidBody.f()` |
| 参考轨迹 | bang-bang flip `q_ref(t), ω_ref(t)` | `flip_maneuver.py :: FlipPlanner.plan()` |

## §8 Chopstick-catch Thrust Allocation

| 公式 | 数学形式 | 源码 |
| --- | --- | --- |
| 几何矩阵 | `A = [[I, I, I]; [l1×, l2×, l3×]]` | `catch_controller.py :: ThrustAllocator._A_matrix()` |
| 分配 LS | `min ‖A t − [F;τ]‖²  s.t.  t_min ≤ t ≤ t_max` | `catch_controller.py :: ThrustAllocator.allocate()` |
| 总需求 | `T_total = Σ T_i(1+w_off)+w_att·τ` | `catch_controller.py :: CatchController.step()` |
