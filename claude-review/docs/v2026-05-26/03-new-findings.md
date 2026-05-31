# 本轮独立审计新发现（F50–F60）

> Historical subreport from a prior Opus review packet; it is not the current handoff.
> Opus review should start from `docs/opus-review/HANDOFF.md`, then verify
> live status in `wiki/review-backlog.md`,
> `docs/codex-review/OPEN_RISKS.md`, and
> `docs/codex-review/QUALITY_GATES.md`.

> 编号自 F50 起，避免与 v1.0 的 F01–F42 编号冲突。所有 finding 都在 v2.0 评审
> 期间由 line-level 源码审计 + 行为重现得出，与 v1.0 packet 中既有条目无重叠。

---

## F50 — PredictiveAutoscaler MPC plant 与 executor 单位错配【P1】

**位置**：`sre_control/predictive_autoscaler.py:54-67` + `:85-86`

**问题**：

MPC 构造时 `A = 0`、`B = [[1], [per_replica_rps]]`，ZOH 离散化（`dt=5.0`）后：
```
Ad = exp(A·dt) = I
Bd = ∫₀ᵈᵗ exp(A·s) · B ds = B · dt = [[5], [500]]
```
即 MPC 内部 plant 认为"u=1"在一个 control step 内会让 replica error 减少 5、
RPS error 减少 500。但 executor 只做：
```python
raw_next = int(round(current_replicas + u))   # 直接 +u，不乘 dt
```
执行结果只 +1 replica。两者对"u 的物理意义"不一致，MPC 会系统性低估自己的
执行权重，导致 5× 欠下达。当前测试通过的原因是 horizon 短 + `q_slo` 大，
往往会让 MPC 撞 `max_step` 饱和，掩盖了内部低估。

**严重度**：P1（在生产风格仿真上是错的，但 scenario 测试因饱和路径而过）。

**建议修复**：

二选一：

1. （首选）在执行器侧乘 dt：`raw_next = int(round(current_replicas + u * self.dt))`。
2. 在 MPC 侧把 B 缩小到 `[[1/dt], [per_replica_rps/dt]]`，使 `Bd = B * dt`
   重回 `[[1], [per_replica_rps]]`。

**附加测试**：写一个 open-loop 1-step 一致性测试，断言"MPC 内部模型一步演化
结果"等于"executor 实际一步演化结果"，覆盖 u ∈ {-1, 0, 1, max_step}。

---

## F51 — StabilityMonitor 反向差分滞后导致恢复期假阳性【P1】

**位置**：`starship/stability_monitor.py:110-145`

**问题**：

`dV/dt` 使用 `(V_new - V_history[0]) / (t_new - t_history[0])` —— 窗口最旧
样本作为 anchor。`window=4` 默认下，一次 V 尖峰 anchor 在 `_history[0]` 后
会污染随后 3 个 tick 的反向差分。

可重现序列：`V_series = [5, 10, 9, 8, 7, 6]`、tick 1 处尖峰。手算：
- tick 2: dV/dt = (9-5)/2 = +2.0  → violating
- tick 3: dV/dt = (8-5)/3 = +1.0  → violating
- tick 4: dV/dt = (7-5)/4 = +0.5  → 可能仍 violating（取决于 tolerance）

而真实 V 从 tick 1 起单调下降。`_consecutive` 在每一次 violating 上累加，
搭配现有 "latch until reset" 语义，会把"早已恢复"的运行状态长时间锁在
`triggered=True`，对应的 `stability_violation` 事件持续发出。

**严重度**：P1（产品级语义错误：长时间假阳性会让操作员失去对监控的信任）。

**建议修复**：

二选一：

1. 改成 recent-pair 差分：`dV_dt = (V_new - V_history[-1]) / (t_new - t_history[-1])`，
   这是 numeric 上更常见的反向差分定义。
2. 保留窗口策略但在"单调递减"时主动弹出旧 anchor：当 `V_new < V_history[-1]`
   且 `_history` 全 `V_new < V_history[i]` 时清窗口。

**附加测试**：`test_stability_monitor_does_not_latch_after_recovery` —— 输入
`[5, 10, 9, 8, 7, 6]`，断言 tick 4 之后 `consecutive_violations == 0` 且
`triggered` 不超过 1 tick。

---

## F52 — CanaryScheduler `_last_share=0.0` 默认值在 warm-start 时引入幻影斜率【P2】

**位置**：`sre_control/canary_scheduler.py:48-109`

**问题**：

`_last_share`、`_last_err`、`_b_est` 都默认 `0.0`。若操作员把 scheduler 接到
已存在的 50% canary，首次 `observe(current_share=0.50, proposed_share=0.55,
observed_error_rate=0.002)`：
- `predicted_err = _b_est * (proposed - _last_share) = 0.0 * (0.55 - 0.0) = 0`
- `_b_est_new = (0.002 - 0.0) / (0.55 - 0.50) = 0.04`

但事实上 `0.04` 完全是"以 share=0 为 anchor 拟合出来的"假斜率，污染随后几
tick 的 trust-region。

**严重度**：P2（生产 / warm-start 场景常见；scenario 测试都从 share=0 起步未触发）。

**建议修复**：增加 `_initialised: bool` flag；首次 `observe` 仅记录初始
share / error，不做 refit / ρ 计算。

**附加测试**：`test_canary_warm_start_does_not_poison_slope` —— 从 share=0.50
warm-start，断言首次 `_b_est` 保持默认值而非派生自 share=0 anchor。

---

## F53 — `stability_violation` 仅作 DEGRADED_PLAN 装饰，autoscaler/canary 未变保守【P1】

**位置**：`sre_control/stack.py:186-261`

**问题**：

`stability_trace["events"]` 触发后，stack 仅 append `DEGRADED_PLAN` 到
`runtime_states`，然后立刻进入 `autoscaler.step(...)` 与 `canary.propose(...)`，
两者均按常规参数执行：
- 没有 clamp `max_step → 1`
- 没有冻结 canary share
- 没有替换为保守 fallback

而 docstring（`:186-189`、`stability_guard.py` 与 wiki）反复声称"downstream
controllers should stay in conservative mode until reset"。文档与行为不一致，
Lyapunov 红线在当前实现中**没有任何 closed-loop 效应**。

**严重度**：P1（控制语义级错误；评审者很容易误以为已经接入）。

**建议修复**：

三选一（按工作量从轻到重）：

1. 仅文档收敛：在 `stability_guard.py` docstring 与 wiki 明确"observe-only，
   不会反压 downstream"，并把 `safe_action` 字段改名 `notice_action` 避免误导。
2. 部分接入：当 `stability_trace["triggered"]`，在 stack 内 clamp
   `autoscaler.max_step = 1` 并 skip `canary.propose`。
3. 全面接入：把 stability 状态作为 explicit input 注入 autoscaler / canary
   step 签名。

**附加测试**：`test_stack_clamps_autoscaler_when_stability_triggered` —— 注入
人为 V 序列触发监控，断言 autoscaler 内部 `raw_control` 受 clamp 影响。

---

## F54 — SLOGuardrail 对 NaN proposal 静默放过、无事件【P1】

**位置**：`sre_control/slo_guardrail.py:69-106`

**问题**：

`audit([NaN, 0, 0])` 返回：
- `approved = [NaN, NaN, NaN]`
- `cone_violated_before = False`
- `magnitude_violated_before = False`
- `projection_distance = NaN`
- `events = []`

NaN 与任何数比较都 False，因此既不触发 cone 违例也不触发 magnitude 违例。NaN
随 `safe_action` 传到 `stack.py:299`，`np.linalg.norm` 返回 NaN，`rps_demand
= NaN` 进入 `lsq_linear` —— 大概率被 scipy 抛 ValueError，最终触发
`adapter_exception` fallback 路径。原始的"programmer 给了 NaN"信号丢失，
日志只能看到 balancer 失败。

**严重度**：P1（fault localisation 失效；下游噪声会被错误归因到 allocator）。

**建议修复**：

`audit` 顶部加 `if not np.isfinite(proposal).all(): raise
AdapterInputError("non-finite proposal")` 或发出新的
`unsafe_proposal_projected(reason="non_finite_input")` 事件并 clamp 到
nominal direction × magnitude_floor。

**附加测试**：`test_guardrail_rejects_non_finite_proposal` —— 输入含 NaN 与
±inf 的 proposal，断言要么 raise，要么发出明确事件、不会污染下游。

---

## F55 — 自动扩缩 `last_trace` 在 fallback 路径滞留旧值【P2】

**位置**：`sre_control/stack.py:216-240` × `sre_control/predictive_autoscaler.py:105-112`

**问题**：

`PredictiveAutoscaler.step()` 抛 `RecoverableControlError` 时，stack 走
fallback（clip 当前 replicas）并 emit `adapter_exception`，但
`self.autoscaler.last_trace` 仍是上一次 successful tick 的字典。读
`stack.autoscaler.last_trace` 做事后分析的工具会看到：
- `next_replicas` 指向旧 tick 的值
- 没有任何 "fallback" 标记
- `events` 为空

与本 tick 实际执行结果不一致。

**严重度**：P2（不是 crash，但是 telemetry 一致性问题）。

**建议修复**：在 stack 的 fallback 分支里手动覆盖：

```python
self.autoscaler.last_trace = {
    "next_replicas": next_replicas,
    "local_states": ["error"],
    "events": [],
    "fallback": True,
    "fallback_reason": f"{type(exc).__name__}: {exc}",
}
```

或在 `PredictiveAutoscaler.step` 内捕获自家异常前把 `last_trace` 置为 sentinel。

---

## F56 — SignalFusion `_rejections` 同名 Signal 计数器互覆【P2】

**位置**：`sre_control/signal_fusion.py:80-187`

**问题**：

`self._rejections[signal.name] = consecutive_count`。同一 tick 的 `readings`
列表允许出现两个 `Signal` 实例 name 相同（不同 R、不同 override），二者共享
counter：[reject_signal_a, accept_signal_b]（两者同名）会让 b 把 a 的
`consecutive_rejections` 清零。也没有"name 唯一性"构造期校验。

trace 输出的 `consecutive_rejections` 字段在这种场景下错位。

**严重度**：P2（要触发需要操作员显式构造重名 Signal，但 fixture 上没有
拦截）。

**建议修复**：

1. 在 `SignalFusion.__post_init__` 检测 name 重复并 raise。
2. 或把 `_rejections` 改为按 `id(signal)` 索引，name 仅用于 trace 标签。

---

## F57 — `_can_reuse_last_good_alloc` 对 NaN 不敏感【P3】

**位置**：`sre_control/stack.py:102-113`

**问题**：

判断 last-good cache 是否可复用的逻辑遍历 `_last_good_alloc_shares` 比较是否
落在 `[rps_min, rps_max]`。但 NumPy 下 `NaN < x` 与 `NaN > x` 都为 False，
因此一个被污染过的缓存（含 NaN）会通过校验。今天 `lsq_linear` 不输出 NaN，
所以暂未触发，但作为防御层应当显式排除。

**建议修复**：在循环里加 `if not np.isfinite(share): return False`。

---

## F58 — PoolCapacityPlanner 精确饱和漏发 `pool_capacity_clipped` 事件【P3】

**位置**：`sre_control/pool_planner.py:75-108`

**问题**：

事件触发条件为 `shortfall = max(0, rps - max_capacity*rps_per_conn) > 0`。当
`rps == max_capacity * rps_per_conn`（如 `max=5, rps_per_conn=100, rps=500`），
`sigma = 5` 即饱和但 `shortfall = 0`，事件不发，`local_states` 不含 `clip`。
等于站在悬崖边上不报警，必须等下一 tick 真正越界才能感知。

**建议修复**：

1. 在 `sigma == max_capacity` 时 emit `pool_at_capacity`（新事件 kind，需要
   同步 `EVENT_COUNTEREXAMPLES` 与 `EVENT_FIELD_SCHEMA`）。
2. 或扩展现有 `pool_capacity_clipped` 在 `clipped_slots = 0` 时发出 advisory
   级别事件。

---

## F59 — `TopologyState.ring_angle_rad` 实际区间不是 docstring 声明的 [-π, π]【P3】

**位置**：`sre_control/topology_state.py:115-125`

**问题**：

`2 * acos(q[0])` 落在 `[0, 2π]`，乘以 `±1`（由 `q[3] >= 0` 决定）后结果在
`[-2π, 2π]`。例如对 `3.5 rad / z-axis` 的 quaternion，返回 3.5，未做
mod-wrap。docstring 声称 `[-π, π]`，下游若按此假设做 hash-ring index 会
出错。

**建议修复**：

加入 wrap：`((angle + math.pi) % (2 * math.pi)) - math.pi`。或更正 docstring
为 `[-2π, 2π]` 并显式说明不 wrap。配上参数化测试覆盖 ±0.5、±1.5、±2.5、±3.5。

---

## F60 — `test_signal_fusion_ou_prediction_uses_stable_exact_discretization` 同义反复【P3】

**位置**：`tests/test_sre_control.py:189-202`

**问题**：

测试用 `expected_state = 10.0 * np.exp(-0.5 * 5.0)` —— 这就是 `SignalFusion._f`
内部公式。一旦实现里写错（例如换成 Euler 或换成 `exp(+theta*dt)`），但测试
若也复制了"和实现一样的"公式，就退化为同义反复。

**建议修复**：

1. 用 `scipy.linalg.expm(-theta * np.eye(n) * dt) @ (x - x_ref) + x_ref`
   作为独立 oracle。
2. 或用 `dt=0.01` 的精细 Euler 多步积分到 `t=5.0` 端点，断言一步预测在
   tolerance 内匹配 fine-grid 终点。
3. 同时保留 counterexample 测试：构造 `theta * dt = 1.0`，断言不会出现
   Euler 步法的反号问题。

---

## 已审阅 / 暂无新隐患的模块

| 模块 | 评审深度 | 结论 |
|---|---|---|
| `starship/ekf.py` | Joseph form / PSD 地板 / gated no-op 三条路径都跟读 | 通过 |
| `sre_control/catch_adapter.py` | 整体是对 `WeightedLoadBalancer` 的薄包装 | 无双重簿记风险 |
| `sre_control/weighted_balancer.py` | residual fraction 防 div-by-zero、`rps_min > rps_max` 校验 | 与 F02 旁路并列，已记 |
| `sre_control/events.py` | `validate_event` 拒绝缺字段 / 多字段 | 通过 |
| `sre_control/fast_switcher.py` | `mag == 0` 短路避免 `mid*mid` div-by-zero | 通过 |

---

## 严重度汇总

| 严重度 | findings |
|---|---|
| P1 | F50 / F51 / F53 / F54 |
| P2 | F52 / F55 / F56 |
| P3 | F57 / F58 / F59 / F60 |

合计 11 项，其中 P1 占 4 项。建议：合入前至少修复 P1 中两项；其余 7 项进入
`docs/codex-review/OPEN_RISKS.md` 作 risk register 记录。
