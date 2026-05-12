# Codex Review Report

本轮目标：把 `DOC/spacex/` 的 8 个数学支柱继续抽象成 SRE 控制原语，补强知识库图像 / GIF / HTML，并给出可审查的证据链。

## 当前状态

- `spacex/starship/`：8 个星舰支柱均已落成可运行模块。
- `spacex/sre_control/`：8 个 SRE 原生适配层 + `SREControlStack.step()` 已串联完成。
- `spacex/analysis/`：9 个 before/after 研究脚本可复现，汇总写入 `analysis/artifacts/SUMMARY.txt`。
- `spacex/docs/`：`knowledge-base.html`、`FORMULA_MAP.md`、`EQUATION_DEEP_DIVE.md` 已形成三层知识库。
- `spacex/docs/assets/`：8 张机制图 + 8 个 benefit GIF + `s09_sre_stack.png` 已重建。
- `spacex/sre_control/events.py`：10 种 runtime event 已覆盖本地 adapter、innovation gating 与 stability guard 的主要边界条件。

## 8 个支柱地图

| # | 星舰支柱 | 核心能力 | SRE 原语 |
|---|---|---|---|
| 1 | Lossless Convexification | 非凸边界条件下的凸化与安全下界 | `PoolCapacityPlanner` |
| 2 | SCP | 线性化 + trust region + 迭代收敛 | `CanaryScheduler` |
| 3 | 6-DoF / SO(3) | 流形上状态演化与姿态一致性 | `TopologyState` |
| 4 | Thrust cone | 方向锥 + 幅值球的硬护栏投影 | `SLOGuardrail` |
| 5 | EKF | 多源观测融合与不确定性传播 | `SignalFusion` |
| 6 | MPC | 预测式滚动优化与 warm-start | `PredictiveAutoscaler` |
| 7 | Belly-flop -> flip | bang-bang 最短时间切换 | `FastTrafficSwitcher` |
| 8 | Catch allocation | 有界最小二乘分配 | `WeightedLoadBalancer` |

## before / after 证据

来自 `spacex/analysis/artifacts/SUMMARY.txt` 的实测结果：

| # | 主题 | Before | After | 证据含义 |
|---|---|---:|---:|---|
| 1 | Lossless PDG | pos_err 148.3 m | 2.125e-6 m | 凸化后能把末端误差压到近数值精度 |
| 2 | SCP | final_pos_err 8.08 m | 2.87 m | 迭代线性化把局部轨迹拉回可行域 |
| 3 | 6-DoF | angle_rmse 0.05576 rad | 5.715e-7 rad | 流形积分优于朴素姿态累积 |
| 4 | Cone filter | cone_violations 97.4% | 0% | 硬护栏把不合法推力彻底投影掉 |
| 5 | EKF | vel_rmse 481.1 m/s | 51.07 m/s | 融合显著改善速度估计 |
| 6 | MPC | final_err 0.01192 | 3.463e-7 | 滚动优化优于静态 PD |
| 7 | Flip | final_pitch 36.37 deg | 0 deg | bang-bang 达到最短收敛 |
| 8 | Allocation | saturation_violation 33.75% | 0% | 有界 LS 消除了超界分配 |
| SRE | Stack | SLO 25% | 10% | 复利式栈把稳定性换成更高副本成本 |

## 可迁移抽象

- `observe -> fuse -> predict -> plan -> guard -> allocate -> execute`
- `hard constraints first, objective second`
- `trust region` 作为灰度发布半径
- `warm-start` 作为滚动决策复用
- `projection` 作为安全护栏
- `bounded LS` 作为资源分配器
- `state on manifold` 作为拓扑 / 一致性状态建模
- `runtime event schema` 作为 failure trace 的共同语言，让单点能力能在 SRE 栈里复利

## 风险与坑

- 数值问题：`SCP` / `MPC` / `EKF` 都会被初值、尺度、协方差放大效应拖偏。
- 建模问题：观测模型若不识别 velocity / topology 等隐状态，融合会“看起来很稳，实际很飘”。
- 边界条件：cone、box、rank-deficient 分配器在边界上最容易出错。
- 架构边界：`CatchController` 属于 `starship/` 物理层，不应为了 SRE event trace 反向依赖 `sre_control/`。
- 证据问题：`analysis` 的 before/after 只证明“在该场景下有效”，不能当作普适结论。
- 运行问题：推荐使用 `python -m pytest tests -q`，避免不同 `pytest` 入口带来的解释器差异。

## 下一步

1. 把 `EVENT_COUNTEREXAMPLES` 映射成 HTML 知识库里的可检索事件索引。
2. 给 `analysis/` 增加 failure-state before/after 图，展示 event 触发前后的 trace。
3. 若要上生产级解释，补一层“约束违例日志”与“数值稳定性注释”。
