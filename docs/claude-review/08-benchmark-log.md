# Benchmark Log

> 每次 `python -m examples.compare_e2e_vs_structural --n N --seed S --metrics-out ...` 运行后，把摘要追加到本文件最上方（newest first），形成基线历史。
> 配套脚本 [scripts/run_benchmark.py](./06-suggested-patches/02-benchmark-ci.md) 完成后可自动追加。

## 配置说明

- **canonical 配置**：`--n 50 --seed 0 --horizon 100 --dt 0.1`
- 此配置用于对比历轮提交的趋势
- 其他配置（更大 n、不同 seed）可以跑，但对比基线以 canonical 为准

---

## 2026-05-12 · v2 baseline · pre-AI-02

**触发**：Claude review pack 完成、P1 易改项清理完毕后，作为 AI-02 的对比基线。
**代码状态**：`auto-decide-session` 分支，19/19 tests 绿，nominal policy 仍为 `GradientPolicy`（未升级）。
**命令**：
```bash
python -m examples.compare_e2e_vs_structural --n 50 --seed 0 \
    --metrics-out .local-artifacts/benchmark-metrics-seed0-n50.json
```

| 指标 | Pure E2E | Structural | Δ |
| --- | ---: | ---: | ---: |
| `collision_rate` | 28.00 % | **0.00 %** | ✅ −28.0 pp |
| `worst_clearance_m` | −0.58 m | +2.92 m | ✅ +3.50 m |
| `planner_emergency_rate` | — | **🚨 42.18 %** | SLO &lt; 0.5% 远未达标 |
| `cbf_fallback_rate` | — | **🚨 22.70 %** | SLO &lt; 5% 远未达标 |
| `guard_intervention_rate` | — | 25.72 % | — |
| `avg_jerk_rms_mps3` | 0.00 | 5.30 | — |
| `mean_step_time_ms` | 0.07 ms | 4.75 ms | ✅ 单帧预算 &lt; 15 ms |

**Planner status 分布**（total steps = 5000）：
- `non_increasing` = 2185 (43.7%)
- `emergency_brake` = 2109 (42.2%) 🚨
- `stable` = 706 (14.1%)

**CBF status 分布**：
- `nom_ok` = 3714 (74.3%)
- `fallback_brake` = 1135 (22.7%) 🚨
- `qp_ok` = 151 (3.0%)

**诊断**：
- 碰撞率达标，但完全依赖 emergency_brake 兜底；
- `nom_ok` 占 74% 说明 CBF 大多数帧"允许"了名义命令，说明 nominal 并没有太激进；
- 但当 nominal 偏差稍大时直接跌进 `fallback_brake`（没有中间的 `qp_ok` 解），说明网格搜索找不到"温和矫正"，只能刹停；
- → 核心问题是 nominal policy 没有 look-ahead，不能提前为 CBF 留余地；
- → 对应 [F-P0-02](./01-findings.md#f-p0-02) 与 [AI-02](./05-action-items.md#ai-02) PredictiveBrakePolicy。

**期望下一次采样**：
- AI-02 完成后 `planner_emergency_rate` 应 &lt; 10%（demo SLO）；
- `cbf_fallback_rate` 应 &lt; 10%；
- `collision_rate` 保持 0%；
- `worst_clearance_m` 轻微下降（因为 predictive brake 会"预刹"，让车离障碍远一点）到 1 ~ 2 m 级别。

---

## 如何追加新基线

1. 跑 canonical 命令（n=50, seed=0）；
2. 把结果摘要按**本文件已有格式**追加到 `## 2026-05-12` 这条**之上**（newest first）；
3. 标题写触发事件（哪个 AI 完成了）+ 关键 commit hash；
4. 保留 Planner status / CBF status 的具体计数，便于诊断。

追加示例：

```markdown
## 2026-05-?? · post-AI-02 · PredictiveBrakePolicy

**触发**：AI-02 完成，nominal 升级为 PredictiveBrakePolicy。
**代码状态**：commit `abc1234`，19+X / 19+X tests 绿。

| 指标 | baseline | current | Δ |
| --- | ---: | ---: | ---: |
| `planner_emergency_rate` | 42.18 % | <填> | Δ pp |
...
```

---

## 相关链接

- 指标 schema：[benchmark-metrics.md](../benchmark-metrics.md)
- SLO 源：[knowledge-base.html §6.1](../knowledge-base.html#sre-slo)
- 断言：[AI-01](./05-action-items.md#ai-01) 的 xfail 测试
- 策略升级：[AI-02](./05-action-items.md#ai-02) + [patch 01](./06-suggested-patches/01-barrier-aware-policy.md)
