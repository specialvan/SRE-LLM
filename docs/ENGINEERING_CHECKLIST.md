# 特解方案工程落地清单

> 本文档记录每种特解方案从数学原理到可验证代码的完整工程映射。

---

## 目录

1. [EKF 融合 (§5)](#1-ekf-融合-signalfusion)
2. [Predictive Autoscaler (§6)](#2-predictive-autoscaler-mpc)
3. [Weighted Load Balancer (§8)](#3-weighted-load-balancer-bounded-ls)
4. [SLO Guardrail (§4)](#4-slo-guardrail-cone-projection)
5. [Stability Monitor (Lyapunov)](#5-stability-monitor-lyapunov)
6. [Canary Scheduler (§2)](#6-canary-scheduler-trust-region)
7. [Pool Capacity Planner (§1)](#7-pool-capacity-planner)
8. [Fast Traffic Switcher (§7)](#8-fast-traffic-switcher)
9. [SREControlStack 集成](#9-srecontrolstack-集成)

---

## 1. EKF 融合 (SignalFusion)

### 代码位置
- `starship/ekf.py`: EKF 核心实现 (91-98行: Joseph form)
- `sre_control/signal_fusion.py`: SRE adapter (per-sensor gate)

### 关键实现

| 功能 | 代码行 | 说明 |
|------|--------|------|
| Joseph form | `ekf.py:91-97` | `(I-KH)P(I-KH)^T + K·R·K^T` 数值稳定 |
| 对称化 | `ekf.py:97` | `0.5 * (posterior + posterior.T)` |
| Per-sensor gate | `signal_fusion.py:63-75` | 每个 Signal 可独立配置门限 |
| Mahalanobis 门限 | `ekf.py:82-89` | 异常观测拒绝保护后验 |
| 阈值追踪 | `signal_fusion.py:157` | `threshold_used` 写入 trace |

### 测试覆盖
- `tests/test_ekf.py`: 4个测试
  - `test_1d_constant_velocity_tracks_truth`: 收敛到真值
  - `test_update_keeps_covariance_symmetric`: 对称性 40次迭代
  - `test_update_keeps_covariance_psd_under_near_perfect_measurement`: PSD 正定
  - `test_gated_update_leaves_state_and_covariance_unchanged`: Gated 保护
- `tests/test_sre_control.py`: 6个 SignalFusion 测试
  - `test_signal_fusion_per_sensor_gate_rejects_one_accepts_other`: 混合接受/拒绝
  - `test_signal_fusion_inherits_fusion_default_when_signal_has_no_override`: 默认继承
  - `test_signal_fusion_consecutive_rejections_reset_on_acceptance`: 计数器重置

### 数值证据 (§5)
| 指标 | Before | After |
|------|--------|-------|
| vel_rmse | 481.1 | 51.07 |
| pos_rmse | 33.6 | 33.15 |

---

## 2. Predictive Autoscaler (MPC)

### 代码位置
- `starship/mpc.py`: MPC 核心
- `sre_control/predictive_autoscaler.py`: SRE autoscaler adapter

### 关键实现

| 功能 | 代码行 | 说明 |
|------|--------|------|
| 滚动时域 | `predictive_autoscaler.py:67-91` | horizon=10 步滚动优化 |
| SLO 成本 | `predictive_autoscaler.py:85` | `q_slo` 副本目标 |
| 整数化 | `predictive_autoscaler.py:99-103` | `round()` + `clip()` |
| 边界事件 | `predictive_autoscaler.py:104-113` | `replica_bound_active` |

### 测试覆盖
- `tests/test_mpc.py`: MPC 核心测试
- `tests/test_sre_control.py`:
  - `test_autoscaler_responds_to_forecast_growth`: 副本响应
  - `test_autoscaler_marks_replica_bound_as_local_event`: 边界事件

### 数值证据 (§6)
| 指标 | Before | After |
|------|--------|-------|
| final_err | 0.01192 | 3.463e-07 |
| tracking_rmse | 2.098 | 2.083 |

---

## 3. Weighted Load Balancer (Bounded LS)

### 代码位置
- `starship/catch_controller.py`: 物理层分配器
- `sre_control/weighted_balancer.py`: SRE adapter

### 关键实现

| 功能 | 代码行 | 说明 |
|------|--------|------|
| 有界约束 | `weighted_balancer.py:59-68` | `lsq_linear(A, b, bounds=(lb, ub))` |
| 饱和检测 | `weighted_balancer.py:70-72` | EPS 容差边界检测 |
| 残差报告 | `weighted_balancer.py:73-78` | rps/zone 双残差 |
| Fallback | `stack.py:277-294` | last-good + bootstrap |

### 测试覆盖
- `tests/test_allocation.py`: Bounded LS 测试
- `tests/test_contracts.py`:
  - `test_sre_stack_carries_allocator_events_upward`: 饱和事件上报
  - `test_sre_stack_reuses_last_successful_alloc_shares_on_recoverable_balancer_error`: 复用
  - `test_sre_stack_balancer_recoverable_error_bootstrap_falls_back_to_zero_shares`: 归零

### 数值证据 (§8)
| 指标 | Before | After |
|------|--------|-------|
| saturation_violation_pct | 33.75 | 0 |
| mean_saturation_excess | 7.928e+04 | 0 |

---

## 4. SLO Guardrail (Cone Projection)

### 代码位置
- `starship/thrust_constraints.py`: 物理层锥投影
- `sre_control/slo_guardrail.py`: SRE adapter

### 关键实现

| 功能 | 代码行 | 说明 |
|------|--------|------|
| 锥投影 | `slo_guardrail.py:53-73` | 角度约束 |
| 幅值裁剪 | `slo_guardrail.py:75-83` | magnitude_cap |
| 两阶段审计 | `slo_guardrail.py:39-52` | before/after 对比 |

### 测试覆盖
- `tests/test_thrust_constraints.py`: 物理层测试
- `tests/test_contracts.py`:
  - `test_sre_stack_carries_guardrail_events_upward`: 投影事件
- `tests/test_sre_control.py`:
  - `test_guardrail_projects_into_cone_and_ball`: 锥内投影
  - `test_guardrail_honours_magnitude_cap`: 幅值限制

### 数值证据 (§4)
| 指标 | Before | After |
|------|--------|-------|
| cone_violations | 0.974 | 0 |
| mag_violations | 0.7825 | 0 |

---

## 5. Stability Monitor (Lyapunov)

### 代码位置
- `starship/stability_monitor.py`: Lyapunov 监控核心
- `sre_control/stability_guard.py`: SRE wrapper

### 关键实现

| 功能 | 代码行 | 说明 |
|------|--------|------|
| V 函数 | `stability_monitor.py:40-47` | `V_fn` 用户定义 |
| 离散差分 | `stability_monitor.py:66-73` | `dV/dt ≈ (V - prev_V) / dt` |
| 锁存语义 | `stability_monitor.py:78-87` | `triggered` 保持到 `reset()` |
| SRE 包装 | `stability_guard.py:48-94` | `stability_violation` 事件 |

### 测试覆盖
- `tests/test_stability_monitor.py`: 7个测试
  - `test_trigger_latches_until_explicit_reset`: 锁存语义
  - `test_reset_clears_state`: 重置
  - `test_kinetic_plus_potential_V_for_falling_object`: 能量守恒
- `tests/test_contracts.py`:
  - `test_stability_guard_reports_sustained_trigger_without_new_event`: 持续触发
  - `test_stability_monitor_skips_observe_fallback_state`: fallback

### 数值证据
无独立 analysis study，主要通过单元测试验证。

---

## 6. Canary Scheduler (Trust Region)

### 代码位置
- `sre_control/canary_scheduler.py`: 金丝雀调度

### 关键实现

| 功能 | 代码行 | 说明 |
|------|--------|------|
| Trust Region | `canary_scheduler.py:67-103` | η 收缩/扩展 |
| SLO 预算 | `canary_scheduler.py:72` | `slo_error_budget` |
| 拒绝事件 | `canary_scheduler.py:95-103` | `rollout_rejected` |

### 测试覆盖
- `tests/test_sre_control.py`:
  - `test_canary_shrinks_trust_region_on_slo_burn`: 收缩
  - `test_canary_grows_trust_region_when_safe`: 扩展
- `tests/test_contracts.py`:
  - `test_sre_stack_carries_canary_local_events_upward`: 事件上报

---

## 7. Pool Capacity Planner

### 代码位置
- `sre_control/pool_planner.py`: 连接池规划

### 关键实现

| 功能 | 代码行 | 说明 |
|------|--------|------|
| 容量规划 | `pool_planner.py:38-58` | min/max 约束 |
| 裁剪事件 | `pool_planner.py:52-59` | `pool_capacity_clipped` |

### 测试覆盖
- `tests/test_sre_control.py`:
  - `test_pool_planner_respects_keep_alive_floor`: 最低保持
  - `test_pool_planner_marks_capacity_clip_event`: 裁剪事件

---

## 8. Fast Traffic Switcher

### 代码位置
- `starship/flip_maneuver.py`: 物理层翻转
- `sre_control/fast_switcher.py`: SRE adapter

### 关键实现

| 功能 | 代码行 | 说明 |
|------|--------|------|
| Bang-Bang | `fast_switcher.py:39-49` | 最大速率切换 |
| Deadline 检测 | `fast_switcher.py:53-58` | `deadline_exceeded` |

### 测试覆盖
- `tests/test_sre_control.py`:
  - `test_switcher_hits_target_with_zero_residual_rate`: 收敛
  - `test_switcher_marks_deadline_exceeded_event`: 超时事件

---

## 9. SREControlStack 集成

### 代码位置
- `sre_control/stack.py`: 端到端编排

### 关键实现

| 功能 | 代码行 | 说明 |
|------|--------|------|
| 6阶段管道 | `stack.py:145-296` | OBSERVE→EXECUTING |
| Recoverable fallback | `stack.py:155-165` | SignalFusion safe fallback |
| 异常分类 | `sre_control/exceptions.py` | ControlDomainError 体系 |
| Adapter 事件聚合 | `stack.py:305` | runtime.events 汇总 |

### 测试覆盖
- `tests/test_contracts.py`: 15个集成测试
  - `test_sre_stack_emits_a_jsonish_contract_trace`: 合同格式
  - `test_sre_stack_survives_missing_sensor_readings`: 缺失观测
  - `test_sre_stack_does_not_swallow_programmer_error`: 程序员错误不吞
  - `test_sre_stack_recovers_from_recoverable_adapter_error`: 可恢复错误

### 数值证据 (§9 SRE Stack)
| 指标 | Before | After |
|------|--------|-------|
| slo_violation_pct | 25 | 10 |
| mean_replicas | 18.43 | 26.5 |

---

## 10. §10 Failure Trace

### 代码位置
- `analysis/s10_failure_trace.py`: 事件追踪研究

### 关键实现

| 功能 | 代码行 | 说明 |
|------|--------|------|
| 单一连续 stack | `s10_failure_trace.py:170` | `_build_stack()` 单次调用 |
| 故障注入 | `s10_failure_trace.py:177-188` | 三个窗口注入 |
| 可观测性指标 | `s10_failure_trace.py:224-277` | event_visible_fraction 等 |

### 测试覆盖
- `tests/test_failure_trace.py`: 9个测试
  - `test_s10_uses_one_continuous_stack_instance`: 连续性
  - `test_s10_background_event_fraction_is_bounded`: 背景 < 0.2
  - `test_s10_each_injected_window_has_kind_coverage`: 窗口覆盖

### 数值证据 (§10)
| 指标 | 值 |
|------|-----|
| event_visible_fraction | 0.846 |
| background_event_fraction | 0.0 |
| distinct_kinds | 4 |

---

## 11. 不变量守护

| 不变量 | 守护方式 | 测试文件 |
|--------|----------|----------|
| starship/ 不 import sre_control/ | AST import graph | `test_import_graph.py` |
| Event schema 封闭 | `validate_event` + counterexamples | `test_event_schema.py` |
| runtime.degraded 对齐 DEGRADED_* | 合同测试 | `test_contracts.py` |
| Adapter 异常不崩 tick | try/except + fallback | `test_contracts.py` |

---

## 12. 验证命令

```bash
# 单元测试
python -m pytest tests -q

# 分析研究
python -m analysis.run_all

# 单独运行 §10
python -m analysis.s10_failure_trace

# 导入图检查
python -m pytest tests/test_import_graph.py -q

# Event schema 检查
python -m pytest tests/test_event_schema.py -q
```

---

*文档版本: v0.3.0*
*最后更新: 2026-05-14*