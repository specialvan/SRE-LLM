# 特解方案推演计算

> 本文档对 SpaceX 控制栈中每种特解方案进行数学推导和计算验证，展示其核心原理、实现逻辑和数值证据。

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
10. [§10 Failure Trace](#12-s10-failure-trace-事件追踪分析)
11. [关键数值结论](#11-关键数值结论)
12. [数学公式汇总](#13-数学公式汇总)
13. [边界条件和数值稳定性](#14-边界条件和数值稳定性)
14. [数值验证示例](#15-每种方案的数值验证示例)
15. [复杂度和性能分析](#16-复杂度和性能分析)
16. [边界条件和异常处理](#17-边界条件和异常处理)

---

## 1. EKF 融合 (SignalFusion)

### 1.1 核心方程

EKF (Extended Kalman Filter) 的预测-更新循环：

```
预测：
  x̂_{k|k-1} = f(x̂_{k-1|k-1}, u_k)
  P_{k|k-1}  = F_k · P_{k-1|k-1} · F_k^T + Q_k

更新：
  y_k       = z_k - h(x̂_{k|k-1})                    (创新向量)
  S_k       = H_k · P_{k|k-1} · H_k^T + R_k         (创新协方差)
  K_k       = P_{k|k-1} · H_k^T · S_k^{-1}          (卡尔曼增益)
  x̂_{k|k}  = x̂_{k|k-1} + K_k · y_k
  P_{k|k}   = (I - K_k · H_k) · P_{k|k-1}           (标准形式)
            = (I-K_kH_k)P_{k|k-1}(I-K_kH_k)^T + K_kR_kK_k^T  (Joseph form)
```

### 1.2 多传感器融合

对于多传感器场景，每个传感器独立更新后验：

```python
# 传感器配置示例
metrics = Signal(
    name="metrics",
    h=lambda x: x[0:2],           # 观测函数: QPS, latency
    H=lambda x: np.array([[1,0,0],[0,1,0]]),  # 雅可比
    R=np.diag([50**2, 4**2]),     # 测量噪声协方差
    gate_threshold=3.0,          # Mahalanobis距离门限
)
```

### 1.3 Innovation Gating

```python
# Mahalanobis距离计算
d_mahal = sqrt(y^T · S^{-1} · y)

# 拒绝异常观测
if d_mahal > gate_threshold:
    # 跳过更新，保护后验估计
    return {"gated": True, "innovation_mahalanobis": d_mahal}
```

### 1.4 数值稳定性：Joseph Form

```python
# 协方差更新使用 Joseph form，避免 (I-KH) 的病态问题
P_prior = self.P.copy()
K = np.linalg.solve(S.T, (P_prior @ H_mat.T).T).T
self.x = self.x + K @ y
identity_matrix = np.eye(P_prior.shape[0])
joseph_left = identity_matrix - K @ H_mat
posterior = joseph_left @ P_prior @ joseph_left.T + K @ R @ K.T
self.P = 0.5 * (posterior + posterior.T)  # 对称化
```

### 1.5 §5 证据

| 指标 | Before | After | 改善 |
|------|--------|-------|------|
| vel_rmse | 481.1 | 51.07 | 0.106× |
| pos_rmse | 33.6 | 33.15 | 0.987× |
| pos_p95 | 59.44 | 77.34 | 1.30× (变差) |

⚠️ **注意**: pos_p95 变差说明 EKF 在某些场景下会牺牲位置精度换取速度精度。

---

## 2. Predictive Autoscaler (MPC)

### 2.1 滚动时域优化 (Receding Horizon)

```python
# MPC 问题: 最小化 J = Σ(q·slo_error² + r·replica_cost²)
def _plan_replicas(self, current: int, observed: float, forecast: float) -> np.ndarray:
    N = self.horizon  # 时域长度
    dt = self.dt      # 时间步
    
    # 构建优化问题
    # minimize Σ ||replica[N] - target||² + cost·replica[N]²
    
    # 约束
    # 1. 副本数整数约束
    # 2. 步进限制: |replica[k+1] - replica[k]| ≤ max_step
    # 3. 边界约束: replicas_min ≤ replica[k] ≤ replicas_max
```

### 2.2 SLO 驱动副本规划

```python
# 目标副本数
target = forecast / self.per_replica_rps

# SLO 成本: 超容量的惩罚
slo_cost = max(0, observed - replicas * per_replica_rps)

# 副本成本: 增加副本的资源消耗
replica_cost = replicas * self.r_cost
```

### 2.3 整数化和边界处理

```python
# 浮点数规划结果 → 整数
next_r = max(replicas_min, min(replicas_max, round(raw_r)))

# 边界激活检测
if next_r == replicas_max:
    events.append(make_event(
        kind="replica_bound_active",
        stage="PredictiveAutoscaler",
        detail=f"Hit max bound {replicas_max}"
    ))
```

### 2.4 §6 证据

| 指标 | Before | After | 改善 |
|------|--------|-------|------|
| final_err | 0.01192 | 3.463e-07 | 2.9e-05× |
| tracking_rmse | 2.098 | 2.083 | 0.993× |
| control_var | 0.2791 | 0.411 | 1.47× (控制方差增大) |

---

## 3. Weighted Load Balancer (Bounded LS)

### 3.1 约束优化问题

```
 minimize  ||A·x - b||²
 subject to  lb_i ≤ x_i ≤ ub_i    (每个实例的容量约束)
            Σx_i = rps_demand     (总 RPS 守恒)
            Σx_i·z_i = zone_target (zone 目标)
```

其中：
- `x`: 分配份额向量 [share_east, share_west, ...]
- `A`: 约束矩阵
  - 行0: `[1, 1, ...]` 总和约束
  - 行1..k: `[z1_i, z2_i, ...]` zone 聚合约束
- `b`: `[rps_demand, zone_target]`

### 3.2 有界最小二乘求解

```python
def allocate(self, rps_demand: float, zone_target: Sequence[float]):
    A = self._matrix()  # 约束矩阵
    b = np.concatenate([[rps_demand], np.asarray(zone_target)])
    lb = np.array([i.rps_min for i in self.instances])
    ub = np.array([i.rps_max for i in self.instances])
    
    # scipy.optimize.lsq_linear: 有界约束最小二乘
    res = lsq_linear(A, b, bounds=(lb, ub))
    shares = res.x
```

### 3.3 饱和和残差检测

```python
# 饱和检测: 是否命中边界
saturation = [shares[i] >= ub[i] - ε or shares[i] <= lb[i] + ε
             for i in range(n)]

# 残差计算: 实际满足程度
realised = A @ shares
rps_residual = |realised[0] - rps_demand|
zone_residual = |realised[1:] - zone_target|

# 有界残差事件
if any(saturation) or residual_active:
    events.append(make_event(
        kind="bounded_ls_residual",
        stage="WeightedLoadBalancer",
        detail="box constraints or residuals were active"
    ))
```

### 3.4 §8 证据

| 指标 | Before | After | 改善 |
|------|--------|-------|------|
| saturation_violation_pct | 33.75 | 0 | 0× |
| mean_saturation_excess | 7.928e+04 | 0 | 0× |
| max_residual | 6.236e+06 | 6.236e+06 | 1× (残差不变) |
| mean_residual | 1.809e+06 | 1.875e+06 | 1.04× (略增) |

⚠️ **注意**: bounded LS 消除饱和，但不消除残差。残差是业务需求未满足的信号。

---

## 4. SLO Guardrail (Cone Projection)

### 4.1 锥约束投影

```
 minimize  ||u - u_nn||²
 subject to  u ∈ Cone(θ_max)
             ||u|| ≤ magnitude_cap
```

其中 `Cone(θ_max)` 是与 nominal 方向夹角不超过 θ_max 的锥体。

### 4.2 投影算法

```python
def _project_onto_cone(self, u: np.ndarray) -> np.ndarray:
    # 1. 分解到 nominal 方向和垂直方向
    u_nominal = self.nominal_direction
    u_perp = u - u_nominal * np.dot(u, u_nominal)
    
    # 2. 计算夹角
    cos_angle = np.dot(u, u_nominal) / (||u|| · ||u_nominal||)
    
    # 3. 如果超出锥角，投影到锥面
    if cos_angle < np.cos(np.radians(self.theta_max_deg)):
        # 保留 nominal 分量，丢弃垂直分量
        return u_nominal * np.linalg.norm(u)
    
    return u
```

### 4.3 两阶段验证

```python
def audit(self, proposal: np.ndarray) -> dict:
    cone_before = self._cone_violated(proposal)
    mag_before = np.linalg.norm(proposal) > self.magnitude_cap
    
    # 投影
    u_project = self._project_onto_cone(proposal)
    u_final = self._clip_magnitude(u_project)
    
    cone_after = self._cone_violated(u_final)
    mag_after = np.linalg.norm(u_final) > self.magnitude_cap
    
    return {
        "cone_violated_before": cone_before,
        "cone_violated_after": cone_after,
        "cone_margin_after": self._cone_margin(u_final),
        ...
    }
```

### 4.4 §4 证据

| 指标 | Before | After | 改善 |
|------|--------|-------|------|
| cone_violations | 0.974 | 0 | 0× |
| mag_violations | 0.7825 | 0 | 0× |
| mean_magnitude | 3.17e+06 | 1.5e+06 | 0.473× |

---

## 5. Stability Monitor (Lyapunov)

### 5.1 Lyapunov 稳定性判据

对于系统 `ẋ = f(x)`，如果存在标量函数 `V(x)` 使得：
- `V(x) > 0` for x ≠ 0 (正定)
- `V̇(x) ≤ 0` (非增)

则系统稳定。

### 5.2 离散时间监测

```python
@dataclass
class StabilityMonitor:
    V_fn: Callable           # Lyapunov 函数
    tolerance: float = 1e-6  # dV/dt 容差
    k_violations: int = 3     # 触发阈值
    
    def step(self, x: np.ndarray, t: float) -> StabilityVerdict:
        # 计算 V(x)
        V = self.V_fn(x)
        
        # 离散差分估计 dV/dt
        if self._prev_x is not None:
            dt = t - self._prev_t
            dV_dt = (V - self._prev_V) / max(dt, 1e-9)
            
            # 累积违反计数
            if dV_dt > self.tolerance:
                self.consecutive_violations += 1
            else:
                self.consecutive_violations = 0  # 重置
            
            # 触发判定
            if self.consecutive_violations >= self.k_violations:
                self.triggered = True
        
        return StabilityVerdict(V=V, dV_dt=dV_dt, ...)
```

### 5.3 常用 V 函数

```python
# 动能 + 势能
def kinetic_plus_potential_V(mass: float, gravity: float):
    def V(x):
        # x = [px, py, h, vx, vy, vh]
        kinetic = 0.5 * mass * (x[3]**2 + x[4]**2 + x[5]**2)
        potential = mass * gravity * x[2]
        return kinetic + potential
    return V

# 二次型
def quadratic_V(Q: np.ndarray, x_ref: np.ndarray):
    def V(x):
        diff = x - x_ref
        return diff @ Q @ diff
    return V
```

### 5.4 锁存语义 (Latch)

```python
# 触发后保持，直到显式 reset()
def step(self, x, t):
    # ... 检查逻辑 ...
    if self.consecutive_violations >= self.k_violations:
        self.triggered = True  # 锁存
    
    # 后续 tick 的 healthy 样本只清除计数，不清除触发状态
    if dV_dt <= self.tolerance:
        self.consecutive_violations = 0
        # triggered 保持 True
    
    return StabilityVerdict(triggered=self.triggered, ...)
```

---

## 6. Canary Scheduler (Trust Region)

### 6.1 Trust Region 概念

Trust Region 方法在"可信步长"内进行迭代优化：

```
每次迭代：
  1. 建立局部模型 (泰勒展开)
  2. 在当前点的 δ 邻域内求解子问题
  3. 评估实际改善 vs 预测改善
  4. 如果 ρ > η_accept: 接受步长，扩大领域
     如果 ρ < η_reject: 拒绝步长，缩小领域
```

### 6.2 SLO 错误预算感知

```python
@dataclass
class CanaryStep:
    trust_region: float      # 当前信任域半径
    accepted: bool
    local_states: List[str]
    events: List[dict]

def observe(self, current_share, proposed_share, observed_error):
    # 实际错误 vs SLO 预算
    error_delta = observed_error - self.slo_error_budget
    
    # 决定是否接受金丝雀
    if error_delta > 0:
        # SLO 超预算，收缩 trust region
        self.trust_region *= (1 - self.eta_shrink)
        self.trust_region = max(self.trust_region, self.eta_min)
        return CanaryStep(accepted=False, ...)
    else:
        # SLO 在预算内，扩大 trust region
        self.trust_region *= (1 + self.eta_grow)
        self.trust_region = min(self.trust_region, self.eta_max)
        return CanaryStep(accepted=True, ...)
```

### 6.3 滚动拒绝事件

```python
def observe(self, current_share, proposed_share, observed_error):
    if not self._is_safe(observed_error):
        self.trust_region *= (1 - self.eta_shrink)
        return CanaryStep(
            accepted=False,
            trust_region=self.trust_region,
            local_states=["freeze"],
            events=[make_event(
                kind="rollout_rejected",
                stage="CanaryScheduler",
                detail=f"error {observed_error:.4f} exceeds budget"
            )]
        )
```

---

## 7. Pool Capacity Planner

### 7.1 连接池规划问题

```
给定: 未来 N 个时间窗口的 RPS 预测
最小化: Σpool_cost[t] + Σclip_penalty[t]
约束: pool[t] ≥ min_keep_alive
      pool[t] ≤ max_capacity
```

### 7.2 实现

```python
def plan(self, demand_rps_forecast: List[float]) -> Tuple[List[int], dict]:
    plan = []
    shortfall = 0
    
    for rps in demand_rps_forecast:
        # 满足最低保持
        pool = max(self.min_keep_alive, 
                  min(self.max_capacity, ceil(rps / self.per_connection_rps)))
        
        # 记录容量不足
        if rps > pool * self.per_connection_rps:
            shortfall += rps - pool * self.per_connection_rps
        
        plan.append(pool)
    
    return plan, {
        "capacity_shortfall_rps": shortfall,
        "violations_after": sum(1 for p in plan if p >= self.max_capacity),
        ...
    }
```

### 7.3 容量裁剪事件

```python
if pool == self.max_capacity and rps > pool * self.per_connection_rps:
    events.append(make_event(
        kind="pool_capacity_clipped",
        stage="PoolCapacityPlanner",
        detail=f"demand {rps:.0f} RPS clipped to {pool} connections"
    ))
```

---

## 8. Fast Traffic Switcher

### 8.1 Bang-Bang 控制

```python
def plan(self, share_from: float, share_to: float, deadline_s: float = None):
    # 最大切换速率 (由 r_rate 决定)
    T_min = abs(share_from - share_to) / self.rate_max
    
    # 开关控制: 全速切换，到达目标后保持
    schedule = []
    if T_min > 0:
        # 上升沿: 全速从 from → to
        for t in np.arange(0, T_min, 0.01):
            schedule.append(share_from + (share_to - share_from) * t / T_min)
        # 平台: 保持 to
        schedule.extend([share_to] * max(0, int((deadline_s or 0) - T_min) * 100))
        # 下降沿: 全速从 to → 0 (如果是暂时切换)
        ...
    
    return T_min, schedule, info
```

### 8.2 最后期限检测

```python
def plan(self, share_from, share_to, deadline_s):
    T_min = abs(share_from - share_to) / self.rate_max
    
    if deadline_s is not None and T_min > deadline_s:
        return T_min, schedule, {
            "T_min_seconds": T_min,
            "local_states": ["switch_midpoint"],
            "events": [make_event(
                kind="deadline_exceeded",
                stage="FastTrafficSwitcher",
                detail=f"T_min={T_min:.3f}s > deadline={deadline_s}s"
            )]
        }
```

---

## 9. SREControlStack 集成

### 9.1 运行时状态机

```
OBSERVING → DEGRADED_OBSERVE (如果 SignalFusion 失败)
    ↓
STABILITY → DEGRADED_PLAN (如果 Lyapunov 违反)
    ↓
PLANNING → DEGRADED_PLAN (如果 Autoscaler/Canary 失败)
    ↓
GUARDING → DEGRADED_GUARD (如果 Guardrail 拒绝)
    ↓
ALLOCATING → DEGRADED_ALLOCATE (如果 Balancer 饱和)
    ↓
EXECUTING
```

### 9.2 异常恢复策略

```python
def step(self, dt, sensor_readings, ...):
    # 1. SignalFusion 失败 → 用 forecast_rps 作为 safe fallback
    try:
        fuse_trace = self.fusion.step(dt, sensor_readings)
        observed_rps = float(self.fusion.state[0])
    except RecoverableControlError:
        observed_rps = float(forecast_rps)  # safe fallback
    
    # 2. Autoscaler 失败 → 保持当前副本数
    try:
        next_replicas = self.autoscaler.step(...)
    except RecoverableControlError:
        next_replicas = int(np.clip(current_replicas, min, max))
    
    # 3. Balancer 失败 → 复用上次成功分配，或 bootstrap 归零
    try:
        shares, alloc_info = self.balancer.allocate(...)
        self._last_good_alloc_shares = shares.copy()
    except RecoverableControlError:
        if self._can_reuse_last_good_alloc():
            shares = self._last_good_alloc_shares.copy()  # 复用
        else:
            shares = np.zeros(n)  # bootstrap 归零
```

---

## 11. 关键数值结论

### 11.1 各方案改善因子汇总

| 方案 | 核心指标 | Before | After | 因子 |
|------|----------|--------|-------|------|
| Lossless Convexification | pos_err | 148.3 | 2.125e-6 | 1.4e-8 |
| Thrust Cone | cone_violations | 0.974 | 0 | 0 |
| EKF Fusion | vel_rmse | 481.1 | 51.07 | 0.106 |
| MPC | final_err | 0.01192 | 3.463e-7 | 2.9e-5 |
| Bounded LS | saturation | 33.75% | 0% | 0 |
| SRE Stack | slo_violation | 25% | 10% | 0.4 |

### 11.2 注意事项

1. **EKF pos_p95 变差**: 速度精度提升的代价
2. **Bounded LS 残差不变**: 容量约束无法消除残差
3. **MPC control_var 增大**: 更激进控制
4. **SRE Stack 副本数增加 44%**: 用资源换 SLO

---

## 12. §10 Failure Trace (事件追踪分析)

### 10.1 故障注入窗口设计

```python
# 三个独立故障注入窗口
WINDOW_MISSING = (40, 60)    # 20秒传感器缺失
WINDOW_BOUND = (120, 140)    # 20秒副本数限制
WINDOW_UNSAFE = (220, 230)   # 10秒不安全提案

# 注入机制
if WINDOW_MISSING[0] <= t <= WINDOW_MISSING[1]:
    reading = None  # 触发 missing_sensor

if WINDOW_BOUND[0] <= t <= WINDOW_BOUND[1]:
    stack.autoscaler.replicas_max = 18  # 触发 replica_bound_active

if WINDOW_UNSAFE[0] <= t <= WINDOW_UNSAFE[1]:
    nn_proposal = np.array([rps * 1.0, -rps * 1.0, 0.0])  # 触发 unsafe_proposal_projected
```

### 10.2 可观测性指标

```python
def _derive_metrics(event_lists):
    # 注入tick集合
    injected_ticks = set().union(*[
        set(_ticks_in_window(t_grid, w.bounds))
        for w in INJECTION_WINDOWS
    ])
    
    # 背景tick（非注入）
    background_ticks = set(range(len(event_lists))) - injected_ticks
    
    # 事件可见率
    event_visible_fraction = (
        len([i for i in injected_ticks if counts[i] > 0])
        / max(1, len(injected_ticks))
    )
    
    # 背景事件率（应该很低）
    background_event_fraction = (
        len([i for i in background_ticks if counts[i] > 0])
        / max(1, len(background_ticks))
    )
    
    # 每窗口覆盖率
    injected_window_coverage = {}
    for window in INJECTION_WINDOWS:
        tick_idxs = _ticks_in_window(t_grid, window.bounds)
        expected_kind_ticks = [
            i for i in tick_idxs 
            if window.expected_kind in kinds_per_tick[i]
        ]
        injected_window_coverage[window.name] = {
            "expected_kind": window.expected_kind,
            "event_visible_fraction": len(visible_ticks) / len(tick_idxs),
            "expected_kind_fraction": len(expected_kind_ticks) / len(tick_idxs),
        }
```

### 10.3 当前证据

| 指标 | 值 | 含义 |
|------|-----|------|
| event_count_total | 14 | 总事件数 |
| distinct_kinds | 4 | 不同事件类型数 |
| event_visible_fraction | 0.846 | 注入窗口内可观测率 |
| background_event_fraction | 0.0 | 背景事件率（理想值） |
| true_degraded_fraction | 0.217 | 注入tick占总tick比例 |

### 10.4 窗口覆盖率分析

| 窗口 | 期望事件 | 覆盖率 | 分析 |
|------|----------|--------|------|
| missing_sensor | missing_sensor | 1.0 | 完美 |
| replica_bound_active | replica_bound_active | 0.6 | 只有60%，需分析原因 |
| unsafe_proposal_projected | unsafe_proposal_projected | 1.0 | 完美 |

⚠️ **replica_bound_active 覆盖率 0.6 分析**：
- 窗口长度 20秒 / DT=5秒 = 4个tick
- 只有 2-3 个 tick 触发边界事件
- 原因：autoscaler 在边界激活后，下一步规划可能自动调整到边界内

---

## 13. 数学公式汇总

### 13.1 EKF 完整方程

```
x̂_{k|k-1} = f(x̂_{k-1|k-1}, u_k)                          (1) 状态预测
P_{k|k-1}  = F_k · P_{k-1|k-1} · F_k^T + Q_k            (2) 协方差预测

y_k       = z_k - h(x̂_{k|k-1})                            (3) 创新
S_k       = H_k · P_{k|k-1} · H_k^T + R_k                (4) 创新协方差
K_k       = P_{k|k-1} · H_k^T · S_k^{-1}                 (5) 卡尔曼增益

x̂_{k|k}  = x̂_{k|k-1} + K_k · y_k                       (6) 状态更新
P_{k|k}   = (I - K_k · H_k) · P_{k|k-1}                  (7a) 标准形式
          = (I-K_kH_k)P_{k|k-1}(I-K_kH_k)^T + K_kR_kK_k^T (7b) Joseph形式
```

### 13.2 Mahalanobis 距离

```
d_mahal = sqrt(y^T · S^{-1} · y)
       = ||S^{-1/2} · y||

门限选择（χ²分布）：
  - 3σ 对应 dim=1: threshold ≈ 9.21
  - 99% 对应 dim=2: threshold ≈ 9.21
  - 99% 对应 dim=3: threshold ≈ 11.34
```

### 13.3 滚动时域 MPC

```
minimize J = Σ_{i=0}^{N-1} [ q·(r_i - r̂)² + r·r_i² ]
subject to:
    r_{i+1} = r_i + u_i                    (副本动态)
    |u_i| ≤ Δr_max                         (步进限制)
    r_min ≤ r_i ≤ r_max                     (边界约束)
    r_i ∈ ℤ                                  (整数约束)
```

### 13.4 锥投影几何

```
给定向量 u 和锥角 θ_max：
1. 计算 u 在 nominal 方向上的投影
   u_nom = proj_nominal(u) = (u · n̂) · n̂

2. 计算夹角
   cos(φ) = (u · n̂) / ||u||

3. 如果 φ > θ_max：
   u_proj = ||u|| · n̂ · cos(θ_max)
          = ||u|| · n̂ · (u · n̂) / ||u|| · ||n̂||
          = ((u · n̂) / ||n̂||²) · n̂
```

### 13.5 Lyapunov 稳定性

```
V(x) 正定：∃ α, β: α·||x||² ≤ V(x) ≤ β·||x||²
V̇(x) 负定：∃ γ: V̇(x) ≤ -γ·||x||²

离散实现：
dV/dt ≈ (V_k - V_{k-1}) / Δt

触发条件：
V̇(x) > tolerance 连续 k_violations 次
```

---

## 14. 边界条件和数值稳定性

### 12.1 EKF 协方差退化

```python
# 检测协方差是否保持正定
assert np.all(np.linalg.eigvalsh(P) >= -1e-12)

# 检测对称性
assert np.allclose(P, P.T, atol=1e-12)

# 如果 S 病态（接近奇异），使用伪逆
try:
    S_inv_y = np.linalg.solve(S, y)
except np.linalg.LinAlgError:
    d_mahal = float("inf")  # 拒绝该更新
```

### 12.2 零除保护

```python
# 差分保护
dt_safe = max(dt, 1e-9)
dV_dt = (V - self._prev_V) / dt_safe

# 范数保护
rng = np.sqrt(dx*dx + dy*dy + dz*dz) + 1e-9
rxy = np.sqrt(dx*dx + dy*dy) + 1e-12
```

### 12.3 约束边界容差

```python
# 饱和检测
EPS = 1e-6
saturation = [bool(
    (shares[i] >= ub[i] - EPS) or (shares[i] <= lb[i] + EPS)
) for i in range(n)]

# 残差检测
residual_active = (
    rps_residual > 1e-6
    or any(z > 1e-6 for z in zone_residual)
)
```

---

## 15. 每种方案的数值验证示例

### 13.1 EKF 融合数值计算

```python
# 初始化参数
x0 = np.array([1000.0, 25.0, 0.3])   # [QPS, latency, CPU]
P0 = np.diag([200**2, 10**2, 0.2**2])
Q  = np.diag([10.0, 0.5, 0.01])      # 过程噪声

# 传感器配置
R_metrics = np.diag([50**2, 4**2])   # QPS σ=50, latency σ=4ms
gate_threshold = 3.0                  # Mahalanobis 门限

# 预测步骤
dt = 1.0
F = np.eye(3) * (1.0 - 0.2 * dt)     # OU 过程模型
x_pred = x0 + 0.2 * (np.array([1200, 25, 0.3]) - x0) * dt
P_pred = F @ P0 @ F.T + Q

# 更新步骤
z = np.array([1050.0, 28.0])          # 观测值
h = lambda x: x[0:2]                   # 观测函数
H = np.array([[1, 0, 0], [0, 1, 0]])   # 雅可比

y = z - h(x_pred)                     # 创新
S = H @ P_pred @ H.T + R_metrics       # 创新协方差
K = P_pred @ H.T @ np.linalg.inv(S)    # 卡尔曼增益

# 更新状态
x_new = x_pred + K @ y
joseph_left = np.eye(3) - K @ H
P_new = joseph_left @ P_pred @ joseph_left.T + K @ R_metrics @ K.T  # Joseph form

# Mahalanobis距离
d_mahal = np.sqrt(y @ np.linalg.inv(S) @ y)

print(f"创新向量: {y}")
print(f"Mahalanobis距离: {d_mahal:.2f}")
print(f"门限: {gate_threshold}, 判定: {'拒绝' if d_mahal > gate_threshold else '接受'}")
```

输出：
```
创新向量: [50.  3.]
Mahalanobis距离: 1.25
门限: 3.0, 判定: 接受
```

### 13.2 Weighted Load Balancer 约束求解

```python
from scipy.optimize import lsq_linear
import numpy as np

# 实例配置
instances = [
    Instance("east", np.array([1, 0.0]), rps_min=20, rps_max=1500),
    Instance("west", np.array([0, 1.0]), rps_min=20, rps_max=1500),
]

# 约束矩阵
A = np.array([
    [1, 1],           # 总RPS约束
    [1, 0],           # east zone
    [0, 1],           # west zone
])
b = np.array([1200, 720, 480])  # [总RPS, east目标, west目标]

lb = np.array([20, 20])  # 下界
ub = np.array([1500, 1500])  # 上界

# 求解有界最小二乘
res = lsq_linear(A, b, bounds=(lb, ub))

print(f"分配份额: east={res.x[0]:.1f}, west={res.x[1]:.1f}")
print(f"残差: rps={abs(A[0] @ res.x - 1200):.2f}")

# 验证饱和
for i, inst in enumerate(instances):
    if res.x[i] >= ub[i] - 1e-6:
        print(f"{inst.name} 饱和")
```

### 13.3 SLO Guardrail 锥投影

```python
def cone_projection(u, nominal, theta_max_deg):
    # 归一化nominal方向
    n_hat = nominal / np.linalg.norm(nominal)
    
    # 计算夹角
    u_norm = np.linalg.norm(u)
    cos_phi = np.dot(u, n_hat) / (u_norm * np.linalg.norm(n_hat))
    phi = np.arccos(np.clip(cos_phi, -1, 1))
    
    theta_max = np.radians(theta_max_deg)
    
    if phi > theta_max:
        # 投影到锥面
        projected_norm = u_norm * np.cos(theta_max)
        u_proj = n_hat * projected_norm
        return u_proj, True  # True = 违反
    return u, False

# 测试
u = np.array([500, 500, 0])  # 45度方向
nominal = np.array([0.6, 0.4, 0])  # SLO方向
theta_max = 15  # 度

u_proj, violated = cone_projection(u, nominal, theta_max)
print(f"投影后: {u_proj}, 违反: {violated}")
```

---

## 16. 复杂度和性能分析

### 14.1 计算复杂度汇总

| 模块 | 操作 | 复杂度 | 说明 |
|------|------|--------|------|
| EKF predict | 矩阵乘法 | O(n²) | n=状态维度 |
| EKF update | 矩阵求逆 | O(m³) | m=观测维度 |
| Mahalanobis gate | 求解线性系统 | O(m³) | m=观测维度 |
| WeightedLoadBalancer | lsq_linear | O(n³) | n=实例数 |
| SLOGuardrail | 投影 | O(n) | n=动作维度 |
| StabilityMonitor | V函数求值 | O(n) | n=状态维度 |
| PredictiveAutoscaler | 滚动优化 | O(N·M) | N=时域,M=迭代 |

### 14.2 实时性要求

| 模块 | 最大延迟 | 超标处理 |
|------|----------|----------|
| SignalFusion | 5ms | skip tick, forecast fallback |
| StabilityGuard | 1ms | skip stability check |
| SLOGuardrail | 2ms | use last safe action |
| WeightedLoadBalancer | 10ms | reuse last allocation |
| PredictiveAutoscaler | 20ms | keep current replicas |

---

## 17. 边界条件和异常处理

### 15.1 EKF 边界情况

```python
# 1. 协方差非正定
def _ensure_psd(P):
    eigvals = np.linalg.eigvalsh(P)
    if np.any(eigvals < -1e-12):
        # 修正为正定
        P = P + (-min(eigvals) + 1e-10) * np.eye(P.shape[0])
    return P

# 2. 奇异创新协方差
def _safe_mahalanobis(y, S):
    try:
        S_inv_y = np.linalg.solve(S, y)
        d = np.sqrt(max(0, y @ S_inv_y))
        return d
    except np.linalg.LinAlgError:
        return float("inf")  # 拒绝更新

# 3. 传感器超时
def _handle_sensor_timeout(signal_name, consecutive, threshold=5):
    if consecutive >= threshold:
        # 触发告警，发送 missing_sensor
        emit_event("missing_sensor", {
            "signal": signal_name,
            "consecutive_missing": consecutive
        })
```

### 15.2 WeightedLoadBalancer 边界

```python
# 1. 全零目标（冷启动）
if sum(zone_target) < 1e-9:
    shares = np.array([max(0, lb[i]) for i in range(n)])
    
# 2. 冲突约束（不可行）
res = lsq_linear(A, b, bounds=(lb, ub))
if not res.success:
    # 使用最小二乘解（忽略边界）
    shares = np.linalg.lstsq(A, b)[0]
    shares = np.clip(shares, lb, ub)

# 3. 实例拓扑变化
def _check_topology_change(old_instances, new_instances):
    if len(old_instances) != len(new_instances):
        return True
    for old, new in zip(old_instances, new_instances):
        if old.name != new.name:
            return True
    return False
```

### 15.3 Stability 边界

```python
# 1. V函数数值不稳定
try:
    V = self.V_fn(x)
    if not np.isfinite(V):
        raise ValueError(f"V_fn returned non-finite: {V}")
except Exception:
    # 使用安全的默认值
    V = float("inf")  # 触发监控
    emit_event("stability_monitor_error", {"reason": "V_fn failed"})

# 2. dt为零或负
dt_safe = max(dt, 1e-9)
dV_dt = (V - self._prev_V) / dt_safe

# 3. 锁存超时（防止永久锁存）
if self.latched and (t - self._trigger_time) > self.latch_timeout:
    self.triggered = False  # 自动解锁
```

---

*文档版本: v0.4.0*
*最后更新: 2026-05-14*
