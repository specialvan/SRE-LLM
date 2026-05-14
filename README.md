# starship-recovery

> 星舰 Super Heavy 助推器"筷子塔"回收算法的工程落地
> Engineering implementation of the SpaceX Starship chopstick-catch pipeline

本工程把 [`DOC/spacex/spacex.md`](../DOC/spacex/spacex.md) 中 19 张公式示意图梳理出的
**8 个数学支柱**全部落成可运行的 Python 模块，叙述性内容则按"**1 张图 = 1 个功能需求
PR**"的颗粒度翻译成 [`PR-REQUIREMENTS.md`](./PR-REQUIREMENTS.md)。

一句话定位：**星舰回收不是一个端到端神经网络问题，而是凸优化 + 刚体动力学 + 强约束
状态估计的组合系统**。火箭在 400 km/h 级别的末段自由落体中，靠 3 台 Raptor 节流 + 4
片栅格翼 + RCS 喷气把自己"夹"进塔架两根机械臂之间的几十厘米窗口——能做到这件事靠的
不是深度学习，而是 60 年积累的凸优化着陆制导 (G-FOLD / Lossless Convexification /
Successive Convexification) 在 20 Hz 实时解算循环里跑起来。

---

## 1. 文章 → 代码的 8 个数学支柱

| § | 论文章节 | 核心数学对象 | 代码模块 | 代表公式 |
| --- | --- | --- | --- | --- |
| 1 | **无损凸化** Lossless Convexification | 推力下界锥松弛 | [`lossless_convex.py`](./starship/lossless_convex.py) | `min −z_N  s.t.  ḟ = g + Γ/m,  Γ·n̂ ≥ σ·cosθ_max` |
| 2 | **序列凸规划** SCP / Successive Convexification | 轨迹迭代凸化 + 置信域 | [`scp.py`](./starship/scp.py) | `δẋ = A(t)δx + B(t)δu,  ‖δx‖ ≤ ε` |
| 3 | **6-DoF 刚体动力学** SO(3) | 四元数姿态 + 欧拉方程 | [`rigid_body.py`](./starship/rigid_body.py) | `q̇ = ½ Ω(ω) q,  ω̇ = I⁻¹(τ − ω × Jω)` |
| 4 | **推力指向锥约束** | 锥约束 + 幅值约束 | [`thrust_constraints.py`](./starship/thrust_constraints.py) | `n̂ᵀ u ≥ ‖u‖ cosθ_max,  ‖u‖ ≤ T_max` |
| 5 | **EKF 多源传感器融合** | 雷达 + IMU + 塔架视觉标志 | [`ekf.py`](./starship/ekf.py) | `x̂_{k\|k} = x̂_{k\|k−1} + K_k (z_k − h(x̂_{k\|k−1}))` |
| 6 | **MPC 滚动时域优化** | 二次代价 + 终端代价 | [`mpc.py`](./starship/mpc.py) | `J = Σ(x_kᵀ Q x_k + u_kᵀ R u_k) + x_NᵀP x_N` |
| 7 | **Belly-Flop → Landing-Flip** | 姿态翻转机动 | [`flip_maneuver.py`](./starship/flip_maneuver.py) | `τ_net = Σ(l_i × T_i) + τ_RCS,  I·α = τ_net` |
| 8 | **塔架机械臂捕获推力分配** | 推力重分配 + 姿态补偿 | [`catch_controller.py`](./starship/catch_controller.py) | `T_total = Σ T_i(1 + W_off(t)) + W_att = A · thrust` |

**19 张图 ↔ 节号**：`§1: 11,12` `§2: 13,14` `§3: 15,16` `§4: 17,18` `§5: 1,10,19`
`§6: 2,3,4` `§7: 5,6,7` `§8: image,8,9`。

---

## 2. 数学公式总览

下列公式全部在 `starship/` 对应模块里有可运行的 numpy/scipy 实现：

```
# §1 Powered Descent Guidance — 无损凸化 (Açıkmeşe & Ploen)
min  −z(T)                               # 燃料最优：z = ln m，最大化末端质量
s.t.  ṙ = v
      v̇ = g + Γ / m
      ṁ = −‖Γ‖ / (Isp · g0)
      Γ·n̂ ≥ σ·cos θ_max                  # 推力指向锥（松弛为凸）
      ρ1 ≤ σ ≤ ρ2                        # 推力幅值下/上界（节流范围）
      ‖Γ‖ ≤ σ                            # 无损松弛，等价原 ρ1 ≤ ‖Γ‖ ≤ ρ2

# §2 Successive Convex Programming
δẋ = A(t) δx + B(t) δu                   # 沿参考轨迹线性化
‖δx‖_∞ ≤ η_x,  ‖δu‖_∞ ≤ η_u              # 置信域（trust region）
迭代直到 ‖x^{k+1} − x^k‖ < ε

# §3 6-DoF Rigid-Body Dynamics on SO(3)
q̇ = ½ · Ω(ω) · q,     Ω(ω) = [[0,-ωᵀ],[ω, −[ω]×]]
ω̇ = J⁻¹ (τ − ω × J ω)                   # 欧拉刚体方程
ṙ = v,  v̇ = g + (1/m) · R(q) · F_body

# §4 Thrust Pointing / Magnitude Constraint
‖u‖ ≤ T_max                              # Raptor 推力上限
n̂ᵀ u ≥ ‖u‖ cos θ_max                     # 推力矢量与箭体轴夹角 ≤ θ_max

# §5 Extended Kalman Filter (radar + IMU + tower fiducials)
Predict:  x̂_{k|k−1} = f(x̂_{k−1|k−1}, u_k)
          P_{k|k−1} = F_k P_{k−1|k−1} F_kᵀ + Q_k
Update:   S_k = H_k P_{k|k−1} H_kᵀ + R_k
          K_k = P_{k|k−1} H_kᵀ S_k⁻¹
          x̂_{k|k} = x̂_{k|k−1} + K_k (z_k − h(x̂_{k|k−1}))
          P_{k|k}   = (I − K_k H_k) P_{k|k−1}

# §6 Model Predictive Control (Receding Horizon)
min   J = Σ_{k=0}^{N−1} (x_kᵀ Q x_k + u_kᵀ R u_k) + x_NᵀP x_N
s.t.  x_{k+1} = A_d x_k + B_d u_k
      u_min ≤ u_k ≤ u_max
      x_0 = x̂_now                         # 热启动自上一步尾
→ 仅施加 u_0，下一拍 shift + re-solve

# §7 Belly-Flop / Landing-Flip
τ_net = Σ_i (l_i × T_i) + τ_RCS
I · α  = τ_net − ω × J ω                # 大俯仰角翻转（~90°→~0°）

# §8 Chopstick-catch thrust allocation
T_total(t) = Σ_{i=1..3} T_i · (1 + w_off,i(t)) + w_att · τ_demand
           = A(x, t) · thrust_cmd         # 过约束最小二乘
```

> 注：§1 的"无损凸化"来自 Behçet Açıkmeşe 等人的 G-FOLD，不是 SpaceX 的内部算法。
> SpaceX 从未公开官方回收算法；文章的主张是：**即便外部不知道内部实现，数学结构上
> 能实现 meter-scale 精度的方案就是这一套。** 本仓库沿这一假设做学习/工程复现，不代
> 表 SpaceX 官方实现。

---

## 3. 目录结构

跨会话项目知识库入口见 [`wiki/README.md`](./wiki/README.md)，用于沉淀当前架构、证据边界和 review backlog。

```
spacex/
├── README.md                  # 你正在看的这份
├── PR-REQUIREMENTS.md         # 叙述性内容翻译成 PR 级功能需求（每图一条）
├── pyproject.toml
├── requirements.txt
├── docs/
│   └── FORMULA_MAP.md         # 公式 ↔ 代码逐行对照
├── starship/
│   ├── __init__.py
│   ├── types.py               # 基础数据类型 (State6DOF, Quaternion, Thruster)
│   ├── quaternion.py          # 四元数运算 (乘法/共轭/旋转矩阵/指数映射)
│   ├── rigid_body.py          # §3 6-DoF 刚体动力学 + RK4 积分
│   ├── lossless_convex.py     # §1 无损凸化 PDG 问题构造
│   ├── scp.py                 # §2 Successive Convex Programming 迭代器
│   ├── thrust_constraints.py  # §4 推力锥/幅值约束工具
│   ├── ekf.py                 # §5 扩展卡尔曼滤波（雷达/IMU/Fiducial）
│   ├── mpc.py                 # §6 线性 MPC 滚动时域求解器
│   ├── flip_maneuver.py       # §7 Belly-flop → Landing-flip 参考轨迹
│   ├── catch_controller.py    # §8 塔架捕获段推力重分配 + 姿态补偿
│   └── pipeline.py            # 端到端：EKF → MPC → 推力分配
├── examples/
│   ├── demo_powered_descent.py    # 跑一整条从末端高空到塔架捕获的仿真
│   └── demo_catch_phase.py        # 只跑最后 50 m 的机械臂捕获
└── tests/
    ├── test_quaternion.py
    ├── test_rigid_body.py
    ├── test_lossless_convex.py
    ├── test_ekf.py
    ├── test_mpc.py
    └── test_catch_controller.py
```

---

## 4. 快速开始

```bash
# 可选虚拟环境
python -m venv .venv && .venv\Scripts\activate

# 只需要 numpy / scipy
pip install -r requirements.txt

# 跑末端着陆仿真（PDG → SCP → MPC）
python -m examples.demo_powered_descent

# 跑塔架捕获段
python -m examples.demo_catch_phase

# 单元测试
pytest -q
```

---

## 5. 设计原则（从论文 + 工程实践提炼）

1. **先凸化再求解**：所有控制问题先写成凸形式，再用 scipy/osqp 级求解器。非凸约束
   一律走 successive convexification。
2. **状态估计先于控制**：MPC/推力分配拿到的都是 EKF 融合输出，绝不用裸雷达/裸 IMU。
3. **硬约束不降级**：推力锥 `n̂ᵀu ≥ ‖u‖cosθ_max` 是不等式约束，不是 loss 的正则项。
4. **滚动时域 + 热启动**：每一拍 20 Hz，用上一拍解作 warm start，实测可把 QP 求解时间
   降到 5 ms 以下。
5. **多传感器最坏情形融合**：雷达遮挡时信任 IMU + 塔架视觉标志（fiducial markers）。

---

## 6. 每条公式带来多少数据红利？— before vs after

`analysis/` 下每一个主题都有一个**基线版**（不用公式 / 用最朴素方案）和**论文版**
的并排对比脚本。跑 `python -m analysis.run_all` 会在 **< 3 秒**内输出一份结构化报
告并把对比图存到 `analysis/artifacts/*.png`。

---

## 7. 机制级 HTML 知识库（供 Codex 审阅）

把 8 个主题按"机制图 → 公式 → 动画数据收益 → SRE 控制映射 → 代码 → 局限"
的模板全部整理成一页 HTML，位于：

```
docs/knowledge-base.html
docs/EQUATION_DEEP_DIVE.md  # 方程逐项拆解（每符号·每项·为什么）
docs/assets/                # 8 张机制 PNG + 8 张 before/after GIF
```

新增一个系统前端控制中心，直接把 Python 控制栈输出打到前端态势屏：

```
docs/control-center.html          # 现代化控制中心前端
scripts/control_center_server.py  # 本地 HTTP 服务 + JSON API
analysis/control_center_data.py   # 控制栈 → 前端 payload
```

启动方式：

```bash
python -m scripts.control_center_server
# open http://127.0.0.1:8765/control-center
```

一条命令重生全部资产：

```bash
python -m scripts.build_kb       # == 机制图 + GIF，~1 分钟
```

HTML 包括一个专门的 **"Codex Review 指引"** 节，给 Codex 这类代码审查 agent
提供：P0/P1/P2 审查清单、设计取舍说明、复现实验最短指令、签收标准。

---

## 8. SRE 原生适配层（复利）

`sre_control/` 把 8 个 starship 原件封装成 SRE 语义的组件：

| 支柱 | SRE 适配 | 一句话功能 |
| --- | --- | --- |
| §1 `LosslessPDG` | `PoolCapacityPlanner` | 连接池最小保活+上限的凸规划 |
| §2 `SCP` | `CanaryScheduler` | 灰度发布的置信域自适应 |
| §3 `Quaternion` | `TopologyState` | 拓扑状态在 SO(3) 上的正确演化 |
| §4 `ConeQPFilter` | `SLOGuardrail` | AI 建议的 SLO 安全投影（O(1)） |
| §5 `MultiSensorEKF` | `SignalFusion` | 指标+追踪+RUM 的后验融合 |
| §6 `QuadraticMPC` | `PredictiveAutoscaler` | 预测式 HPA，warm-start 跨拍复用 |
| §7 `FlipPlanner` | `FastTrafficSwitcher` | 紧急切换 bang-bang 最小时间 |
| §8 `ThrustAllocator` | `WeightedLoadBalancer` | 带 box 约束的 RPS 多实例分配 |

端到端装配：`sre_control.SREControlStack.step()` 把上面 8 件串成一条数据流：

```
observe (§5) → plan (§6) → canary (§2) → guardrail (§4) → allocate (§8)
     静态：§1 pool, §3 topology, 应急：§7 switch
```

验证脚本：

```bash
python -m examples.demo_sre_loop     # 60 s 模拟 + 按 5 s 打印 trace
python -m analysis.s09_sre_stack     # SLO 25% → 10%（brown-out + 流量翻倍场景）
pytest tests/test_sre_control.py -v  # 10 条单测
```

---

## 9. 核心指标（本机实测，seed=0）

| § | 主题 | 基线 | 论文公式 | 相对收益 |
| --- | --- | --- | --- | --- |
| 1 | Lossless Convexification (PDG) | 末端位置误差 148 m | **2e-6 m** | ~1e8× 精度 |
| 2 | Successive Convex Programming | 单次线性化 末端误差 8.08 m | **2.87 m** (6 轮收敛) | ~2.8× 精度 |
| 3 | 四元数 6-DoF 动力学 | 欧拉积分 5 s 姿态误差 3.2° | **3.3e-5°** (q̇=½Ωq) | ~1e5× 精度 |
| 4 | 推力指向锥约束 | 97.4% 样本违反锥约束 | **0%** | 把硬约束做成硬约束 |
| 5 | EKF 多源融合 | 雷达原始速度 RMSE 481 m/s | **51 m/s** | ~9.4× 精度 |
| 6 | 滚动时域 MPC | PD 末态误差 1.2e-2 | **3.5e-7** | ~3.4e4× 精度 |
| 7 | Belly-flop → Landing-flip | 恒定扭矩 末态俯仰 36.4° ω 33°/s | **0° / 0°/s** | bang-bang 把翻转做对 |
| 8 | 塔架捕获推力分配 | 伪逆 34% 样本超出节流极限 | **0%** | 硬饱和里严守边界 |

每个主题生成一张两栏图，左图是轨迹/状态时间序列，右图是收敛/误差分布。产物：

```
analysis/artifacts/
├── s01_lossless_convex.png   # 高度/速度对比
├── s02_scp.png               # 位置跟踪 + 收敛曲线
├── s03_rigid_body.png        # 姿态误差随时间增长
├── s04_thrust_cone.png       # (‖u_xy‖, u_z) 平面内锥+球投影前/后散点
├── s05_ekf.png               # 位置/速度 L2 误差时间序列
├── s06_mpc.png               # 跟踪响应 + 控制输入饱和
├── s07_flip_maneuver.png     # 俯仰/角速度 轨迹
├── s08_catch_allocation.png  # 残差直方图 + 越界直方图
└── SUMMARY.txt               # 每个主题的 before/after 指标表
```

> 读表的方法：§4 `cone_violations 97.4% → 0%` 说明没有 cone filter 时 NN 的候选推力
> 里 97% 都会让发动机打出可行范围；加上一条闭式锥投影，所有样本都落回凸集里。§5
> 的速度 RMSE 481 → 51 m/s 来自 9 倍提升的过程模型知识（EKF 知道 `v̇ = g`，基线
> 只会做有限差分）。

---

## 10. 致谢 & 免责声明

- 素材源自 [`DOC/spacex/`](../DOC/spacex/) 下的 19 张结构示意图，文章来自黄大年茶思屋
  "芮博数理工场·结构智能"专栏。
- SpaceX 未公开星舰的官方控制算法。本仓库基于 Açıkmeşe (JPL/UW) 的 G-FOLD / Lossless
  Convexification、Malyuta et al. (2021) 的 Convex Optimization for Trajectory
  Generation、以及经典 6-DoF MPC 做工程化复现，仅供学习研究，不代表 SpaceX 实现。
