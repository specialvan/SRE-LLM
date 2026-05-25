# v1.0 Resolved 项 line-level 复核

> 本文档对应 `OPUS_REVIEW_PACKET.md` 第 3 节"Opus v1.0 Findings Resolved In
> This Packet"中宣称 resolved 的全部 findings 做源码级回读，给出 HOLDS /
> PARTIAL / BROKEN 判定。

---

## P0 / P1 高优切片

### F01 — `FastTrafficSwitcher.plan()` 终端 share 在 safety_margin 下不漂移

**VERDICT：HOLDS**

`sre_control/fast_switcher.py:73-90`：将 `T_min` 乘以 `safety_margin = s` 后，
加速度 `a = sign * mag / (mid*mid) = sign * r_max / s²`。因此在新的 `T_min` 处
解析 share 落在 `share_from + sign * mag`，几何上恒等于 `share_to`。

`tests/test_sre_control.py:469-474` 直接断言：
- `abs(share[-1] - 1.0) < 1e-6`
- 在 `safety_margin=1.2` 下 final_share 与 plan target 完全匹配

仅一处可吐槽：`safety_margin <= 0` 路径未显式拒绝（构造函数允许任意正数，但
`<= 0` 会让 `mid*mid` 在 `__post_init__` 阶段尚未参与计算的负数下退化为 NaN）。
影响较小，但可加 `safety_margin >= 1.0` 的范围保护。

### F02 — `WeightedLoadBalancer.allocate()` solver 失败包装

**VERDICT：PARTIAL**

`sre_control/weighted_balancer.py:80-90`：`lsq_linear` 的 `RuntimeError` / 
`ValueError` / 非收敛已经包装为 `RecoverableControlError`。`exceptions.py:6-15`
的 `ControlDomainError → RecoverableControlError → AdapterInputError` 三段
分层清晰。

**间隙**：

1. 第 75 行 `A = self._matrix()` 与第 76 行 `b = np.concatenate(...)` 都在
   try 块外。`_matrix()` 内部只是按 `zone_vector` 堆栈，构造时已经过
   `__post_init__` 校验，因此在构造后被 mutate 才会失败 —— 概率低但路径存在。
2. `lsq_linear` 在极端病态矩阵下可能抛出 `np.linalg.LinAlgError`（不是
   `RuntimeError`、`ValueError` 子类），当前 catch 不会兜住。
3. 第 97 行 `zone_residual = np.abs(realised[1:] - zone_target).tolist()`
   直接对 `Sequence[float]` 做减法，依赖 numpy 广播 —— 若上游传入 Python list
   长度不一致，会延迟到此处才抛。

**建议**：把 `try:` 提到 `A = self._matrix()` 之前，并把 `np.linalg.LinAlgError`
加入 catch；将 `zone_target` 在 allocate 顶端统一转 `np.asarray(..., dtype=float)`
并校验长度。这是本轮唯一对 v1.0 高优条目的负向修订。

### F03 — `starship.EKF.update()` 奇异 innovation 协方差 gated no-op

**VERDICT：HOLDS**

`starship/ekf.py:83-94`：`np.linalg.solve(S, y)` 在 `LinAlgError` 时返回
`{"gated": True, "innovation_mahalanobis": inf}`，在任何 state mutation 之前
return。`tests/test_ekf.py:146-173` 用 H=zeros / R=zeros 构造奇异 case，
用 `np.array_equal` 断言 state / covariance 字节级未变。

第 98 行 Kalman gain `solve` 也有同样的 fallback 路径，统一 `gated=True` 语义。
唯一小瑕疵：`gated=True` 既代表"singular innovation"也代表"singular K solve"，
下游消费者无法区分。可考虑用 `gated_reason: str` 字段细化。

### F04 / F25 — `adapter_exception.adapter_family` 单一真源

**VERDICT：HOLDS**

`sre_control/stack.py:117-140` 定义 `_adapter_exception_event` helper，唯一
调用 `stack_data_contract()["event_stage_routes"].get(stage_label, "unknown")`。
6 处 call site（line 177 / 209 / 237 / 257 / 284 / 324）全部经由该 helper，
没有任何 hardcoded literal。

`sre_control/stack_contract.py:16-23` 是 mapping 的真源；`events.py:136-143`
的 `EVENT_FIELD_SCHEMA` 在 `adapter_exception` kind 上把 `adapter_family` 列为
required 字段，构成 schema-level 强约束。

`cause_type` 通过 `isinstance(exc, AdapterInputError)` 派生 `fault_family`，
也来自机器可读源。完整意义上的"single source of truth"已经达成。

### F05 — `safe_action` 是 L2 范数 RPS，`zone_target` 是分布

**VERDICT：HOLDS**

`sre_control/stack.py:296-300` 有 docstring 明确写出契约：
> Guardrail actions are direction vectors whose L2 norm encodes total demand.
> Zone placement is supplied separately through zone_target.

`rps_demand = float(np.linalg.norm(safe_action))` —— 标量；`zone_target` 直接
透传给 `balancer.allocate(rps_demand, zone_target)`。

`weighted_balancer.py:72-77` 签名 `allocate(rps_demand: float, zone_target:
Sequence[float])`，把 rps_demand 当作行 0 RHS，`zone_target` 当作其余行。
`slo_guardrail.py` 输出向量经 `np.array(audit["approved"])` 包装，语义一致。

**唯一隐含假设**：`rps_demand` 因为 norm 永远 ≥ 0，理论上能表达"减少需求"的
负向 action 会被吃掉绝对值。属于设计契约，已在评审中作为隐含约束记录到
`docs/codex-review/OPEN_RISKS.md` 的"action vector contract"项。

---

## P2 数值 / 评审者切片

### F07 — `SignalFusion` exact OU 离散化

**VERDICT：HOLDS**

`sre_control/signal_fusion.py:87-88` 状态预测 `x_ref + decay * (x - x_ref)`，
:90-93 Jacobian `np.eye(n) * decay`，二者用同一 `decay = exp(-theta*dt)`。Euler
sign reversal 已彻底消除；`docs/SPECIAL_SOLUTIONS_DERIVATIONS.md` 已同步。

### F10 — `PoolCapacityPlanner.plan()` 真 ceil

**VERDICT：HOLDS**

`sre_control/pool_planner.py:21` import math；:77 `sigma = max(min_keep_alive,
min(max_capacity, math.ceil(demanded)))`。`200.0 → 2`、`200.1 → 3`、`300.0 → 3`
全部正确。

### F14 — S10 JSONL 排序键

**VERDICT：HOLDS**

`analysis/s10_failure_trace.py:341` 与 :346 两个 sink 都用 `json.dumps(row,
sort_keys=True)`。`tests/test_failure_trace.py:152-163` 用 `object_pairs_hook`
重解析首行断言键序。

### F16 — evidence-boundary lint 后缀窗口

**VERDICT：HOLDS**

`scripts/evidence_boundary_lint.py:67-73` 把 prefix context 和 suffix（match
后 100 字符）都参与 negation cue 检查。
`tests/test_synthetic_evidence_boundaries.py:260-263` 覆盖后缀 negation case。

### F18 — balancer 空 / 维度不匹配 zone_vector 拒绝

**VERDICT：HOLDS**

`sre_control/weighted_balancer.py:51-61` `__post_init__` 提前 raise
`ValueError("instances must not be empty")` 与
`ValueError("all instance zone_vector dimensions must match")`。

### F19 — gate_threshold 正数校验

**VERDICT：HOLDS**

`sre_control/signal_fusion.py:56-58` 与 :82-84` 对 `Signal` / `SignalFusion`
两个入口都校验非正即 raise；`None` 保留为 no-gating。

### F21 — S11 regime 测试去除硬编码 40/40/40

**VERDICT：HOLDS**

`tests/test_synthetic_evidence_boundaries.py:92-107` 用 `n_cases=9`，断言三类
regime 计数 pairwise 相等且 ≥ 1。

### F23 — S10 trace-time tick-scaled 容差

**VERDICT：HOLDS**

`analysis/evidence_report.py:576-577`：`time_tolerance = 1e-6 * max(1.0, float(tick))`，
比较 `abs(float(t_seconds) - tick * DT)`。floating accumulation drift 被允许；
整秒级偏差仍被拒。

### F32 — `rps_per_conn` 可配置

**VERDICT：HOLDS**

`sre_control/pool_planner.py:42` dataclass field `rps_per_conn: float = 100.0`。
:67 `demanded = rps / self.rps_per_conn`，:81 `shortfall = max(0.0, rps -
self.max_capacity * self.rps_per_conn)`，sizing 与 shortfall 路径一致。

### F33 — `FastTrafficSwitcher` 非正 `rate_max` 拒绝

**VERDICT：HOLDS**

`sre_control/fast_switcher.py:46-48` `__post_init__` raise
`ValueError("rate_max must be positive")`。

### F37 — 未恢复 replay diagnostics 用严格 JSON null

**VERDICT：HOLDS**

`analysis/s12_sre_replay.py:139` 与 :234-236 用 `float(max(finite)) if finite
else None`；测试用 `json.dumps(..., allow_nan=False)` 验证不会泄漏 `math.inf`。

### F39 — SHA-256 shape 接受大写

**VERDICT：HOLDS（描述失真）**

`analysis/evidence_report.py:57-62` `_is_sha256` 用 `value.lower()` + 字符
membership check，不是正则。行为正确（大写 hex 通过）但 OPUS_REVIEW_PACKET 中
"regex allows [a-fA-F0-9]" 措辞不准确，建议下版更正。

### F42 — replay operator-action 测试看 coverage 不看字面文本

**VERDICT：HOLDS**

`tests/test_synthetic_evidence_boundaries.py:26-32` `_assert_operator_actions_
cover_expected_kinds` 只断言 set 相等 + 字符串非空；:155-164 显式验证用
placeholder 文本"wording can evolve"仍能通过。

### F11 / F12 — 全部 11 个 runtime kinds 严格 schema

**VERDICT：HOLDS**

`sre_control/events.py:11-58` `EVENT_COUNTEREXAMPLES` 恰 11 项；:84-144
`EVENT_FIELD_SCHEMA` 全部覆盖；:180-187 `validate_event` 用 `set(event) ==
allowed_fields` 拒绝多余字段；`test_event_schema.py:271-281` 用 typo
`siganl` 覆盖。

---

## 旁路观察（不计入 findings）

1. `weighted_balancer.py:80-85` catch 只覆盖 `RuntimeError` / `ValueError`，
   建议增加 `np.linalg.LinAlgError`。
2. `weighted_balancer.py:61` `__post_init__` 内对 `inst.zone_vector` 做
   in-place 重赋值，违反 `rules/common/coding-style.md` 的 immutability 原则；
   配合 F56 旁路（同名 Signal 计数器互覆）作为一类整体可考虑列入下次
   refactor 计划。
3. `stack.py:267` `safe_action = np.array(audit["approved"])` —— `audit["approved"]`
   原本是 `np.ndarray.tolist()` 的 list，再次 `np.array(...)` 二次转换，
   性能小坑。
4. `ekf.py:98` 的 `gated=True` 复用 innovation singular 与 K solve singular
   两种语义，建议加 `gated_reason` 字段细化。
5. `analysis/evidence_report.py:1092-1130` 多处用 `!=` 做浮点等值比较；今天
   确定可通过是因为两侧来自同一数据，refactor 风险高，建议改 `abs(a-b) < eps`。

---

## 小结

- 14/14 P2/P3 项实际 holds；F39 行为正确但 packet 描述需更正。
- 5/5 P0/P1 项实际 holds，仅 F02 的 try 块边界存在窄缝隙（PARTIAL）。
- 旁路观察 5 条，不构成 blocker，建议合入 OPEN_RISKS。
- v1.0 修复整体质量较高，无回归性问题。
