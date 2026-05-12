# Quality Gates

> 本页记录 Codex 侧提交给 Claude 前的可复现质量门。计时类数字可能随机器波动，行为类断言应保持稳定。

## 必跑命令

```bash
python -m pytest tests -q
```

最近结果：

```text
51 passed
```

测试结构：

| Test file | Count | 覆盖重点 |
|---|---:|---|
| `tests/test_allocation.py` | 1 | 有界分配基础行为 |
| `tests/test_contracts.py` | 8 | runtime degraded/state/event 合同 |
| `tests/test_ekf.py` | 1 | EKF 基线 |
| `tests/test_event_schema.py` | 2 | event schema 与 counter-example registry |
| `tests/test_failure_trace.py` | 4 | §10 failure trace 可复现性 |
| `tests/test_import_graph.py` | 2 | `starship/` / `sre_control/` 依赖方向 |
| `tests/test_mpc.py` | 1 | MPC 基线 |
| `tests/test_quaternion.py` | 3 | SO(3) / quaternion 基础 |
| `tests/test_rigid_body.py` | 2 | 6-DoF 刚体动力学 |
| `tests/test_sre_control.py` | 17 | 8 个 SRE adapter + stack 行为 |
| `tests/test_stability_monitor.py` | 7 | Lyapunov stability monitor 与 wrapper |
| `tests/test_thrust_constraints.py` | 3 | cone / magnitude projection |

## 分析研究

```bash
python -m analysis.run_all
```

最近结果：

```text
All 10 studies finished
```

核心 before/after 摘要：

| Study | Before | After | 解释 |
|---|---:|---:|---|
| §1 Lossless Convexification | `pos_err 148.3` | `2.125e-6` | 终端误差被凸化控制压低 |
| §3 SO(3) Dynamics | `angle_rmse 0.05576` | `5.715e-7` | 流形积分避免姿态漂移 |
| §4 Cone Projection | `cone_violations 0.974` | `0` | 硬护栏消除越界动作 |
| §5 EKF Fusion | `vel_rmse 481.1` | `51.07` | 多源融合改善隐状态估计 |
| §6 MPC | `final_err 0.01192` | `3.463e-7` | 滚动优化优于静态控制 |
| §8 Allocation | `saturation_violation_pct 33.75` | `0` | 有界 LS 消除资源分配越界 |
| §SRE Stack | `slo_violation_pct 25` | `10` | 控制栈降低 SLO 违例，但增加副本成本 |
| §10 Failure Trace | `0 events / 0 kinds` | `83 events / 4 kinds` | 事件生命周期有可观测证据 |

## Demo 命令

```bash
python -m examples.demo_sre_loop
python -m examples.demo_powered_descent
python -m examples.demo_catch_phase
```

这些 demo 的作用不是证明生产可用，而是证明抽象路径能跑通：

| Demo | 证明点 |
|---|---|
| `demo_sre_loop` | SRE 控制栈能产出 tick trace、runtime states 和 events |
| `demo_powered_descent` | powered descent 数学层能独立运行 |
| `demo_catch_phase` | catch/landing 相关物理抽象仍在 `starship/` 内，不污染 SRE adapter |

## HTML / 资产检查

最近已检查：

| 入口 | 状态 |
|---|---|
| `docs/knowledge-base.html` | HTML parser 无结构 issue |
| `docs/V2_Knowledge/knowledge-base.html` | HTML parser 无结构 issue |
| `docs/assets/s10_event_density.png` | §10 event density 图已生成 |
| `docs/assets/s10_cooccurrence.png` | §10 co-occurrence 图已生成 |
| `docs/V2_Knowledge/assets/s10_event_density.png` | V2 资产同步 |
| `docs/V2_Knowledge/assets/s10_cooccurrence.png` | V2 资产同步 |

## 证据产物索引

| Artifact | 用途 |
|---|---|
| `analysis/artifacts/SUMMARY.txt` | 10 个研究的汇总指标 |
| `analysis/artifacts/s10_event_density.png` | event kind 随 tick 的密度 |
| `analysis/artifacts/s10_cooccurrence.png` | degraded state 与 event kind 的共现关系 |
| `analysis/artifacts/s10_trace_sample.jsonl` | §10 trace 样例，供 reviewer 看单条 event 结构 |
| `docs/assets/*.png` | 主知识库使用的图像资产 |
| `docs/V2_Knowledge/assets/*.png` | V2 知识库使用的图像资产 |

## 当前质量门结论

- 单元测试闭环：通过。
- 10 个 analysis study：通过。
- 10 个 runtime event kind：schema 有封闭注册和 counter-example。
- 依赖方向：`starship/` 不 import `sre_control/`，有测试守护。
- 剩余风险主要在建模语义、异常兜底边界和 §10 指标命名，不在“跑不起来”。
