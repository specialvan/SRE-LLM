# 设计说明（结构智能视角）

## 1. 分层结构
论文把自动驾驶决策抽象为两层耦合：
- **离散层（§1.1）**：交互意图图 `G_I`，捕捉博弈/冲突关系。
- **连续层（§1.2）**：非欧流形上的车辆动力学 `ẋ = f(x, u)`。

两者通过 `§1.3` 的"受限梯度流"耦合：势能 `Φ` 用图里边权调制排斥项，
梯度方向再投影到连续流形的切空间。

在代码里：
- `graph.py` 产出 `edges`，内含博弈权重；
- `potential.interaction_potential(...)` 把这些权重注入势能；
- `planner.GradientPolicy` 把 `-∇Φ` 变成 `(steer, jerk)` 候选命令；
- `cbf.CBFQPFilter` 和 `invariant.ControlInvariantOperator` 负责切空间投影。

## 2. 三道闸门
论文 §2 指出三种数学边界——我们把它们做成三道必过的闸门：

| 闸门 | 模块 | 失败后果 |
| --- | --- | --- |
| 李雅普诺夫稳定 | `StabilityMonitor` | 命令被 `T_inv` 降档（减速）直至恢复 |
| 可达集 | `ReachableSet` / `DeadZoneDetector` | 提前识别死区，触发减速/停车 |
| 博弈安全冗余 | `WorstCaseGame` | 放大障碍的安全边距 `base_buffer` |

## 3. 为什么是 QP 而不是惩罚项？
论文 §3.2 特意强调：惩罚项会把硬约束软化，等价于允许违反。
代码里：
- CBF 条件作为 **不等式约束** 进入 QP（`_objective` 里 `ok=False` 直接丢弃）；
- Lyapunov 条件作为 **松弛变量为 0** 的硬约束；
- 只有当所有闸门都失败，才退化到**刹停回退**，而不是"带惩罚继续跑"。

## 4. 神经网络放在哪里？
答：放在 `StructuralPlanner.nominal`。
- 默认用 `GradientPolicy`（势能梯度），方便做示例；
- 实际工程里把它替换为任何学习到的策略（imitation / RL / MPC），
  后面的 CBF + `T_inv` 仍然保证硬约束。

这样神经网络得到**最大限度的灵活性**，但它的输出必须能被投影进可行集。

## 5. 实时预算
- 所有模块只做一次前向仿真或一个 QP 规模 ≤ 10。
- 默认 horizon 2 s、dt=0.1s，一步规划在几 ms 量级（无并行）。
- `ReachableSet.sample` 仅在"感知到显著不确定性"时触发，不进入每帧闭环。
