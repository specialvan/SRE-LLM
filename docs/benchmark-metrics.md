# Benchmark Metrics Schema

> 目的：说明 `examples/compare_e2e_vs_structural.py --metrics-out` 输出的机器可读指标，供 Codex review、CI、可视化页和 SRE 迁移复用。

## 命令

```bash
python -m examples.compare_e2e_vs_structural \
  --n 50 \
  --seed 0 \
  --horizon 100 \
  --dt 0.1 \
  --metrics-out artifacts/benchmark-metrics.json
```

不传 `--metrics-out` 时仍会输出人类可读摘要。

## 顶层结构

```json
{
  "schema_version": "benchmark.metrics.v1",
  "generated_by": "examples.compare_e2e_vs_structural",
  "params": {},
  "summaries": {
    "pure_e2e": {},
    "structural": {}
  },
  "deltas": {},
  "scenarios": []
}
```

## `params`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `seed` | int | 场景随机种子 |
| `n` | int | 场景数量 |
| `horizon` | int | 每个场景仿真步数 |
| `dt` | float | 单步时长，秒 |

## `summaries`

`pure_e2e` 和 `structural` 使用同一结构：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `name` | string | 链路名称 |
| `scenarios` | int | 场景数 |
| `collision_count` | int | 碰撞场景数 |
| `collision_rate` | float | 碰撞率 |
| `avg_clearance_m` | float | 平均最小安全余量 |
| `worst_clearance_m` | float | 最差安全余量 |
| `avg_jerk_rms_mps3` | float | 平均 jerk RMS |
| `mean_step_time_ms` | float | 平均单步耗时 |
| `guard_intervention_rate` | float | CBF 非 `nom_ok` 的比例，仅结构化链路有意义 |
| `cbf_fallback_rate` | float | CBF `fallback_brake` 比例 |
| `planner_emergency_rate` | float | `T_inv` emergency brake 比例 |
| `cbf_status_counts` | object | CBF 状态计数 |
| `planner_status_counts` | object | planner / T_inv 状态计数 |

## `deltas`

| 字段 | 说明 |
| --- | --- |
| `collision_rate_reduction` | `pure_e2e.collision_rate - structural.collision_rate` |
| `avg_clearance_gain_m` | 结构化链路平均安全余量提升 |
| `worst_clearance_gain_m` | 结构化链路最差安全余量提升 |
| `mean_step_time_delta_ms` | 结构化链路额外单步耗时 |

## Reviewer 解释规则

不要只看碰撞率。

reviewer 至少同时看四类指标：

1. 安全：`collision_rate`、`worst_clearance_m`。
2. 可用性：`guard_intervention_rate`、`cbf_fallback_rate`、`planner_emergency_rate`。
3. 舒适度：`avg_jerk_rms_mps3`。
4. 实时性：`mean_step_time_ms`。

如果结构化链路碰撞率低但 `planner_emergency_rate` 很高，说明系统更安全但可能过保守，下一步要调 CBF / T_inv / nominal policy 的边界，而不是只展示“0 碰撞”。

## 和 Trace 的关系

benchmark metrics 是 trace 的聚合层。

- trace 解释单步动作为什么被改写。
- metrics 解释一组场景里的总体收益和代价。
- 可视化页应该优先读取 metrics JSON，而不是手写收益数字。
