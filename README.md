# auto-decide

> 自动驾驶决策动力学 —— 李雅普诺夫硬约束下的不确定性导航
> Engineering implementation of the "Structural Intelligence" column 第 6 期

本工程把《自动驾驶的决策动力学 —— 李雅普诺夫硬约束下的不确定性导航》一文的数学结构系统性地落地为代码：
把论文里所有公式变成可运行的模块，把其他叙述性内容逐项拆成功能需求（见 [`PR-REQUIREMENTS.md`](./PR-REQUIREMENTS.md)），
然后在一个端到端 Demo 中串起来。

核心主张一句话：**决策不是概率拟合，而是在受约束的动力学流形上做受限梯度流。**
神经网络负责灵活性，物理不变量（Lyapunov / CBF / 可达集）负责可控性。

---

## 1. 文章结构与代码的一一映射

| 论文章节 | 核心数学对象 | 代码模块 |
| --- | --- | --- |
| 1.1 离散层：交互意图图 `G_I = (V_I, E_I)` | 加权有向时变图、意图语义 | [`auto_decide/graph.py`](./auto_decide/graph.py) |
| 1.2 连续层：高维非欧相空间 `x = (x, v, a, μ)`，`ẋ = f(x, u)` | 自行车模型、状态流形 | [`auto_decide/dynamics.py`](./auto_decide/dynamics.py) |
| 1.3 非合作博弈中的动力学投影 `ẋ = -∇Φ(x)` | 势能场、受限梯度流 | [`auto_decide/potential.py`](./auto_decide/potential.py) |
| 2.1 物理不变量：李雅普诺夫判据 `dV/dt ≤ 0` | Lyapunov 函数与衰减监视器 | [`auto_decide/lyapunov.py`](./auto_decide/lyapunov.py) |
| 2.2 拓扑边界：可达集 `R(x₀, T)` | 前向可达集采样、逻辑死区检测 | [`auto_decide/reachable.py`](./auto_decide/reachable.py) |
| 2.3 逻辑边界：非完全信息博弈纳什均衡 | 意图置信度、最坏情况缓冲区 | [`auto_decide/game.py`](./auto_decide/game.py) |
| 3.1 控制不变集生成算子 `u_safe = T_inv(u_nn)` | 神经输出到安全输出的算子 | [`auto_decide/invariant.py`](./auto_decide/invariant.py) |
| 3.2 屏障函数与搜索空间折叠 `ḣ + αh ≥ 0` | CBF-QP 安全过滤器 | [`auto_decide/cbf.py`](./auto_decide/cbf.py) |
| 3.3 定量对比 | 基准对照实验 | [`examples/compare_e2e_vs_structural.py`](./examples/compare_e2e_vs_structural.py) |
| 4 结语：给 AI 戴上物理的枷锁 | 端到端装配 | [`auto_decide/planner.py`](./auto_decide/planner.py) |

### 交付产出
- [PR-REQUIREMENTS.md](./PR-REQUIREMENTS.md) — PR 级功能需求清单
- [docs/FORMULA_MAP.md](./docs/FORMULA_MAP.md) — 公式 ↔ 代码对照表
- [docs/DESIGN.md](./docs/DESIGN.md) — 设计说明
- [docs/knowledge-base.html](./docs/knowledge-base.html) — **总览知识库**（SRE 评审报告 + Codex checklist）
- [docs/architecture.html](./docs/architecture.html) — **详细架构**（architecture / requirements / task breakdown / refine）
- [docs/trace-schema.md](./docs/trace-schema.md) — **Trace 契约**（JSONL 字段 / 不变式 / 回放）
- [docs/benchmark-metrics.md](./docs/benchmark-metrics.md) — **Benchmark 指标契约**（结构化回归 / metrics JSON / reviewer 解释规则）
- [docs/codex-handoff.md](./docs/codex-handoff.md) — **Codex 交接单**（当前状态 / 风险面 / 下一步）
- [docs/deep-dive.html](./docs/deep-dive.html) — **算法级深度拆解**（数据结构、逐行伪代码、失败矩阵、系统不变式）
- [docs/equations-digest.html](./docs/equations-digest.html) — **方程吃透手册**（E-01~E-35 · 每一条公式的推导 / 等价变形 / 陷阱 / SRE 对位）
- [docs/sre-adaptation.html](./docs/sre-adaptation.html) — **工程能力→SRE 迁移**（9 个命名模式 + 接口骨架 + 采用路线）

---

## 2. 数学公式总览

下列公式全部在 `auto_decide/` 对应模块里有可运行的实现：

```
G_I = (V_I, E_I)                        # 交互意图图
x   = (x, v, a, μ)                      # 状态向量
ẋ  = f(x, u)                            # 车辆动力学
ẋ  = -∇Φ(x)                             # 受限梯度流 / 非合作博弈投影
dV(x)/dt ≤ 0                            # 李雅普诺夫稳定性判据
R(x₀, T) = { φ(t; x₀, u) | t∈[0,T], u∈U }   # 可达集
h(x) ≥ 0, ḣ(x, u) + α·h(x) ≥ 0         # 控制屏障函数
u_safe = T_inv(u_nn)                    # 控制不变集生成算子
```

---

## 3. 目录结构

```
auto-decide/
├── README.md                 # 你正在看的这份
├── PR-REQUIREMENTS.md        # 文章叙述翻译成 PR 级功能需求
├── pyproject.toml
├── requirements.txt
├── docs/
│   ├── FORMULA_MAP.md        # 公式 ↔ 代码逐行对照
│   └── DESIGN.md             # 结构智能视角下的设计说明
├── auto_decide/
│   ├── __init__.py
│   ├── types.py              # 基础数据类型与协议
│   ├── graph.py              # 交互意图图（离散层）
│   ├── dynamics.py           # 车辆动力学（连续层）
│   ├── potential.py          # 势能场 Φ 与受限梯度流
│   ├── lyapunov.py           # 李雅普诺夫稳定性
│   ├── reachable.py          # 前向可达集与逻辑死区
│   ├── cbf.py                # 控制屏障函数 & CBF-QP
│   ├── invariant.py          # 控制不变集生成算子 T_inv
│   ├── game.py               # 非完全信息博弈 & 安全冗余
│   └── planner.py            # 端到端决策装配
├── examples/
│   ├── demo_intersection.py
│   └── compare_e2e_vs_structural.py
└── tests/
    ├── test_graph.py
    ├── test_dynamics.py
    ├── test_lyapunov.py
    ├── test_cbf.py
    └── test_planner.py
```

---

## 4. 快速开始

```bash
# 可选：创建虚拟环境
python -m venv .venv && .venv\Scripts\activate

# 安装依赖（只需要 numpy / scipy，可选 cvxpy）
pip install -r requirements.txt

# 运行一个十字路口避让 Demo
python -m examples.demo_intersection

# 结构化 vs 端到端的安全性对比
python -m examples.compare_e2e_vs_structural

# 单元测试
pytest -q
```

---

## 5. 设计原则（摘自论文 + 工程裁剪）

1. **先有结构，再有参数**：神经网络只是候选策略发生器，最终落地的每一个控制指令必须经过 `T_inv`。
2. **硬约束不可降级**：`dV/dt ≤ 0` 和 `ḣ + αh ≥ 0` 永远是不等式约束，不是损失项。
3. **搜索空间折叠**：先用 CBF 剪掉不可行流形，再在可行流形里做优化，避免在全空间里盲搜。
4. **保留安全冗余**：在非完全信息博弈下，planner 默认假设他车走最坏意图，逼着自车留缓冲区。
5. **实时预算**：所有模块都要在 10 ms 量级内返回（QP 规模 ≤ 10 约束，Lyapunov 只做一次前向仿真）。

---

## 6. 致谢

论文来源：
[《自动驾驶的决策动力学 —— 李雅普诺夫硬约束下的不确定性导航》](https://www.chaspark.com/#/hotspots/1262929214745849856)
作者：芮祥麟 博士（Dr. Shang-Ling Jui），华为拉格朗日数学与计算中心。
本工程为纯学习/工程落地目的，对原文内容做了最小化重述并附加了可运行实现。
