# Evidence Ledger

## 当前质量门口径

最近 review packet 记录的基线：

```bash
python -m pytest tests -q      # 51 passed
python -m analysis.run_all     # All 10 studies finished
```

这说明当前工程可运行、测试可复现，但不等于生产 ready。

## Studies 证据边界

| Study | 当前观察 | 可以说明 | 不能说明 |
|---|---|---|---|
| §1 Lossless | `pos_err 148.3 -> 2.125e-6` | 合成 PDG 场景中凸化路径有效 | SpaceX 官方实现或所有着陆场景 |
| §4 Cone | `cone_violations 0.974 -> 0` | 硬护栏能消除越界动作 | 投影后业务收益仍保持 |
| §5 EKF | `vel_rmse 481.1 -> 51.07` | 场景内 filtering 改善速度估计 | 强多源融合或真实传感器完整性 |
| §8 Allocation | `saturation_violation_pct 33.75 -> 0` | 有界求解消除容量越界 | residual 消失或需求被满足 |
| §9 SRE Stack | `slo_violation_pct 25 -> 10` | 控制栈以更高副本成本换更低 SLO 违例 | 生产容量规划最优 |
| §10 Failure trace | `0 events / 0 kinds -> 83 events / 4 kinds` | event channel 可观测 | runtime 全程降级被严格证明 |

## §10 证据需要收敛的点

当前 refined spec 将 §10 列为 PR-A：

- 使用一个连续 `SREControlStack` 实例。
- 通过 injection windows 改变输入或约束，不切换 stack 来制造 event kind。
- 去掉 nominal path 中 always-on allocator residual。
- 用新指标替代 overloaded `degraded_tick_fraction`：
  - `event_visible_fraction`
  - `true_degraded_fraction`
  - `background_event_fraction`
  - `injected_window_coverage`
- 导出全量 `analysis/artifacts/s10_trace_full.jsonl`。

## 解释纪律

可以写：

- “质量门通过。”
- “合成场景内 before/after 显示机制收益。”
- “runtime events 具备可观测通道。”

不要写：

- “event lifecycle 已完整证明。”
- “控制栈 production-ready。”
- “这些算法就是 SpaceX 内部实现。”
- “合成 evidence 等价于生产 benchmark。”
