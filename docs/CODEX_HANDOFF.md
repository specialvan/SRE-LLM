# Codex Handoff

分支：`spacex-session`

这份文档是给下一轮 Codex 的接棒说明，目标不是重复知识库，而是把当前工程状态、已完成内容、验证结果、风险和下一步工作讲清楚。

## 当前结论

这套 `spacex/` 工程已经完成了从“公开材料抽象”到“可运行 SRE 控制原语”的主链路：

- `starship/`：8 个数学支柱均已落成可运行模块。
- `sre_control/`：8 个 SRE 原生适配层已完成，`SREControlStack.step()` 已串联。
- `analysis/`：9 个 before/after 研究脚本可复现，并产出汇总文件。
- `docs/`：知识库、公式对照、方程深挖、架构文档、审查报告已落成。
- `docs/assets/`：机制图、GIF、SRE 栈图都已重建。

## 架构骨架

当前工程的推荐理解顺序是：

1. `DOC/spacex/`：公开文章与原始截图。
2. `starship/`：把 8 个支柱落成可运行控制模块。
3. `analysis/`：用 baseline vs after 证明这些模块确实带来收益。
4. `sre_control/`：把星舰原语翻译成 SRE 原语。
5. `sre_control/stack.py`：把 8 个原语串成一个控制回路。
6. `examples/`：提供可运行 demo。
7. `docs/`：把机制、公式、图像、GIF、架构和审查点集中成知识库。

推荐优先看的三份文档：

- [ARCHITECTURE.md](./ARCHITECTURE.md)
- [CODEX_REVIEW_REPORT.md](./CODEX_REVIEW_REPORT.md)
- [knowledge-base.html](./knowledge-base.html)

## 8 个支柱的工程抽象

| # | 支柱 | 工程能力 | SRE 映射 |
|---|---|---|---|
| 1 | Lossless Convexification | 非凸下界的凸化 | `PoolCapacityPlanner` |
| 2 | SCP | 线性化 + trust region 迭代 | `CanaryScheduler` |
| 3 | 6-DoF / SO(3) | 流形状态演化 | `TopologyState` |
| 4 | Thrust cone | 方向锥 + 幅值球硬护栏 | `SLOGuardrail` |
| 5 | EKF | 多源观测融合 | `SignalFusion` |
| 6 | MPC | 预测式滚动优化 | `PredictiveAutoscaler` |
| 7 | Flip | bang-bang 最短时间切换 | `FastTrafficSwitcher` |
| 8 | Allocation | 有界最小二乘分配 | `WeightedLoadBalancer` |

## 关键证据

最新汇总在 `analysis/artifacts/SUMMARY.txt`。关键数字如下：

- `1`：`pos_err 148.3 m -> 2.125e-6 m`
- `2`：`final_pos_err 8.08 m -> 2.87 m`
- `3`：`angle_rmse 0.05576 rad -> 5.715e-7 rad`
- `4`：`cone_violations 97.4% -> 0%`
- `5`：`vel_rmse 481.1 m/s -> 51.07 m/s`
- `6`：`final_err 0.01192 -> 3.463e-7`
- `7`：`final_pitch 36.37 deg -> 0 deg`
- `8`：`saturation_violation 33.75% -> 0%`
- SRE 栈：`SLO 25% -> 10%`，但平均副本数从 `18.43 -> 26.5`

这说明当前抽象不是“讲得通”，而是“可量化地复利”。

## 模块契约提醒

如果继续往下挖，不要再先写大故事，应该先看每个模块的契约：

- 输入是什么
- 输出是什么
- 状态是什么
- 哪些量是硬约束
- 哪些量只是目标项
- 典型失败模式是什么

这个方向已经在 `docs/ARCHITECTURE.md` 里做成了 module contract matrix。

## 已验证状态

当前可复现验证：

```bash
python -m pytest tests -q
python -m analysis.run_all
python -m scripts.build_kb
python -m examples.demo_sre_loop
python -m examples.demo_powered_descent
python -m examples.demo_catch_phase
```

注意：

- 在这个环境里，推荐用 `python -m pytest tests -q`，不要直接跑裸 `pytest`。
- `analysis.run_all` 会刷新 `analysis/artifacts/SUMMARY.txt`。

## 风险与坑

- `SCP`、`MPC`、`EKF` 都吃初值、尺度和协方差，数值上要保守。
- `cone`、`box`、`rank-deficient LS` 这些边界条件最容易把看起来“挺对”的方案打坏。
- `analysis` 的收益只证明“该场景有效”，不能直接泛化成普适结论。
- `SREControlStack` 的收益有明显成本，平均副本数上升是正常 trade-off。

## 下一轮优先级

1. 给每个 SRE 原语补一个 counter-example。
2. 把每个公开方法补成更清晰的 API contract。
3. 给 `stack.py` 补更细的降级路径说明。
4. 如果继续做 SRE 复利，优先补真实的运行时契约和失败状态日志，而不是继续加图。

