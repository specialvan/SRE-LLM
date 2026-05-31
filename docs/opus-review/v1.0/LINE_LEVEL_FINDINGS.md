# Opus 深度评审 · v1.0 · 行级隐患审计

> Historical subreport from a prior Opus review packet; it is not the current handoff.
> Opus review should start from `docs/opus-review/HANDOFF.md`, then verify
> live status in `wiki/review-backlog.md`,
> `docs/codex-review/OPEN_RISKS.md`, and
> `docs/codex-review/QUALITY_GATES.md`.

本文档把 v1.0 主报告里"P2/P3 风险"的颗粒度拉到行级别 — 每条都给出文件路径、行号、复现条件、影响和最小修复建议。
共 42 项发现，按"严重程度 × 触发概率"排序。

> **重要说明**：所有 H/M 级发现都是**当前测试覆盖不到的**潜在路径；并不意味着当前 249 个测试错，只意味着边缘情景需要补测。L 级是工程纪律建议。

---

## 严重程度分级

| 级别 | 触发条件 |
|---|---|
| **H** | 在合理边界输入下会产生错误结果或抛未捕获异常 |
| **M** | 在罕见但可达的输入下产生静默错误结果 |
| **L** | 工程纪律/可维护性/一致性问题，不直接影响正确性 |

---

## F01 [H] · `FastTrafficSwitcher.plan` 在 `safety_margin ≠ 1` 时终点溢出

- **位置**：`sre_control/fast_switcher.py:68-85`
- **代码**：
  ```python
  T_min = self.safety_margin * 2.0 * np.sqrt(mag / self.rate_max)  # L68
  ...
  share[i] = (share_from + 0.5*a*mid*mid + a*mid*s - 0.5*a*s*s)   # L84-85
  ```
- **数学推导**：终点（`s=mid=T_min/2`）的 share 是
  `share_from + a · mid² = share_from + sign · rate_max · (T_min/2)²
                          = share_from + sign · safety_margin² · mag`
  当 `safety_margin = 1.2`，终点 share = `share_from + 1.44 · dx` — **超调 44%**。
- **影响**：若任何调用方设置 `safety_margin > 1`（默认 1.0 暂时安全），bang-bang 终点会冲过目标。
- **测试覆盖**：未覆盖。`tests/` 全部使用默认 `safety_margin=1.0` 或不构造该对象。
- **修复**：把 `T_min` 拆成"完成时间 + 余量"，或把 `a` 缩放 `1/safety_margin²`，或拒绝 `safety_margin != 1`（更保守）。

---

## F02 [H] · `WeightedLoadBalancer.allocate` 未检查 `lsq_linear` 收敛 / 异常

- **位置**：`sre_control/weighted_balancer.py:67`
- **代码**：`res = lsq_linear(A, b, bounds=(lb, ub))` 直接消费 `res.x`/`res.cost`，**既不检查 `res.success`，也不捕获 solver 抛的异常**。
- **影响**：
  1. solver 不收敛时 `res.x` 可能为不可行解，作为 `shares` 返回，进入 `bounded_ls_residual` event 后用错误数字；
  2. solver 抛 `ValueError`（如 `lb > ub`）会直接冒泡到 `SREControlStack.step`，**绕开 `except RecoverableControlError`**，导致整个 tick 崩溃 — **违反 I-5 不变式**。
- **测试覆盖**：未覆盖任何 solver 失败/不收敛路径。
- **修复**：
  ```python
  try:
      res = lsq_linear(A, b, bounds=(lb, ub), method='trf')
  except (ValueError, RuntimeError) as exc:
      raise RecoverableControlError(f"bounded LS solver failed: {exc}") from exc
  if not res.success:
      raise RecoverableControlError(f"solver did not converge: {res.message}")
  ```

---

## F03 [H] · `starship.EKF.update` 第二次 `solve(S, ...)` 未保护 LinAlgError

- **位置**：`starship/ekf.py:82-94`
- **代码**：
  ```python
  try:
      S_inv_y = np.linalg.solve(S, y)         # L84  ← protected
      d_mahal = float(np.sqrt(max(0.0, y @ S_inv_y)))
  except np.linalg.LinAlgError:
      d_mahal = float("inf")                  # L87
  if gate_threshold is not None and d_mahal > gate_threshold:
      return {"gated": True, ...}
  ...
  K = np.linalg.solve(S.T, (P_prior @ H_mat.T).T).T   # L93  ← NOT protected
  ```
- **触发条件**：`S` 奇异，但用户未设置 `gate_threshold`（默认 `None`）。此时 L84 抛 LinAlgError 进入 except，`d_mahal=inf`；下面的 `if gate_threshold is not None and d_mahal > gate_threshold` 因 `gate_threshold is None` 为 False，**继续往下走** L93 — **第二次 solve 会再次抛 LinAlgError，无 except 接住**。
- **影响**：未启用 gate 的 EKF 用户在测量噪声协方差 `R` 退化时直接崩溃。
- **测试覆盖**：未覆盖（`test_ekf.py` 所有 `R` 都正定）。
- **修复**：在第二次 solve 前用同一个 try/except 包；或直接复用 L84 的 `S_inv_y` 计算 `K = P @ H^T @ S^-1`。

---

## F04 [H] · `SREControlStack._adapter_family` 与 `stack_data_contract().event_stage_routes` 矩阵冲突

- **位置**：
  - `sre_control/stack.py:122-129`
  - `sre_control/stack_contract.py:17-23`
- **冲突点**：

  | stage_label | `_adapter_family`（stack.py） | `event_stage_routes`（stack_contract.py） |
  |---|---|---|
  | `StabilityGuard` | `"plan"` | `"stability"` |
  | `CanaryScheduler` | `"rollout"` | `"plan"` |

- **影响**：同一个适配器在 trace 里以两种身份出现：
  - `adapter_exception` 事件的 `adapter_family` 写 `"plan"`；
  - `evidence_report._contract_event_errors` 走的 `event_stage_routes` 把它放到 `"stability"`；
  - 下游做 incident dashboards 时，按 `adapter_family` 分桶与按 `event_stage_routes` 分桶得到**完全不同结果**。
- **测试覆盖**：`tests/test_contracts.py:131-138` 只断言 routes，`test_event_schema.py:222-225` 只断言 `adapter_family`；**没有 cross-consistency 测试**。
- **修复建议**：把 `_adapter_family` 改写为 `event_stage_routes.get(stage_label, "unknown")`，让两边永远一致；或显式记录两个独立分类法的意义并加 cross-test。

---

## F05 [H] · `sre_control/stack.py:300` 用 L2 范数把"动作向量"折成 RPS demand

- **位置**：`sre_control/stack.py:300`
- **代码**：`rps_demand = float(np.linalg.norm(safe_action))`
- **隐含约定**：`safe_action` 是 (东向, 西向, ...) 维度的向量，其 **L2 范数**被当成 RPS 总量。
- **数学事实**：对正分量向量 `[600, 800]`，L2 = 1000，但实际 RPS 总量 = 1400。这两个值差 40%。
- **当前测试为什么没爆**：`tests/test_contracts.py` 里的 `nn_proposal=[500, 50, 10]` 接近主轴方向，被 cone filter 投回近似 [500, 0, 0]，L2 ≈ |x| ≈ sum。**主轴方向下 L2 ≈ sum 成立**，所以测试通过。
- **触发条件**：`nominal_direction` 非主轴 + `safe_action` 各维度都显著非零时，`rps_demand` 与实际 RPS 严重不符。
- **影响**：bounded LS 把"L2 范数"当成总量做分配，可能溢出或低于实际容量需求。
- **测试覆盖**：未覆盖（s10 用了 0.6/0.4 方向，向量长度仍接近主分量）。
- **修复**：要么明确文档说"动作向量的 L2 范数 = 总 RPS demand"是建模约定（并加注释），要么改成 `float(np.sum(np.abs(safe_action)))` 或显式提取 magnitude。

---

## F06 [M] · `_run_scenario` 中 `replicas = max(entry["replicas_next"], 10)` 与 autoscaler 的 `replicas_min=4` 不一致

- **位置**：`analysis/s10_failure_trace.py:208`
- **代码**：`replicas = max(entry["replicas_next"], 10)`
- **冲突**：`_build_stack` 中 `replicas_min=4`（L129），但 s10 scenario 强制下限为 10。
- **影响**：若 autoscaler 在 `[4, 10)` 区间选了一个值，会被脚本 clamp 到 10，与 autoscaler 的真实输出不符。下一 tick 的 `current_replicas` 就被人为抬高。
- **可观察**：`replicas_trace` 的统计（如 `mean_replicas`、`peak_replicas`）受到该 clamp 影响，但 SUMMARY.txt 里报的"after"数字读上去像是 autoscaler 决策结果。
- **修复**：要么对齐 `replicas_min`，要么在 SUMMARY 注明这是 scenario floor。

---

## F07 [M] · `SignalFusion._F(x, u, dt)` 在 `theta·dt ≥ 1` 时退化或反号

- **位置**：`sre_control/signal_fusion.py:82-84`
- **代码**：`return np.eye(n) * (1.0 - self.theta * dt)`
- **数值**：
  - `theta=0.2, dt=5.0` ⇒ F = 0·I（s10/s12 接近此区）；
  - `theta=0.5, dt=5.0` ⇒ F = −1.5·I（反号，协方差预测 `F P F^T` 仍是正定但 K 增益方向被反转）。
- **影响**：与 OU 过程的真实雅可比脱节；当 `theta·dt > 2`，离散 OU 不稳定但 EKF 仍当作"准确雅可比"。
- **测试覆盖**：未覆盖。
- **修复**：要么 clamp `theta*dt ≤ 1` 并报警，要么把离散化改成 `F = exp(-theta·dt)·I`（精确 OU 离散化）。

---

## F08 [M] · `CanaryScheduler.observe` 拒绝步只更新 `_eta`，不更新 `_b_est`

- **位置**：`sre_control/canary_scheduler.py:101-106`
- **代码**：`if accepted and proposed_share - current_share > 1e-6: self._b_est = ...`
- **影响**：被拒绝的观察明明带新数据点，**模型不学习**。如果错误率快速上升把所有候选 step 都打成 rejected，调度器的线性模型就**永远卡在初始 `_b_est=0`**，trust region 永远缩。
- **测试覆盖**：未覆盖 rejected→rejected 序列。
- **修复**：把斜率拟合的接受条件改成 `proposed_share - current_share > 1e-6`（不要求 accepted），并在 detail 里标注"slope refit from rejected step"。

---

## F09 [M] · `analysis/s10_failure_trace._derive_metrics` 与 `analysis/evidence_report._visibility_diagnostics` 的"空集合"语义不一致

- **位置对照**：
  - `analysis/s10_failure_trace.py:268-269` — `len(visible_injected_ticks) / max(1, len(injected_ticks))` 在 `injected_ticks` 空集合时**返回 0**；
  - `analysis/evidence_report.py:1009-1012` — `_mean_bool(values, default=1.0)` 在空集合时**返回 1.0**。
- **影响**：同一概念（"在没有 injected ticks 时，event 可见度是多少"）两边给出相反答案。当前 fixture 永远非空，但任何把窗口删空的研究都会让两套数字打架。
- **测试覆盖**：未覆盖。
- **修复**：约定一个 vacuous-truth 答案（建议 1.0，遵循"empty ⇒ trivially satisfied"），两处统一。

---

## F10 [M] · `PoolCapacityPlanner.plan` 的 `int(demanded) + 1` 不是真正的 ceiling

- **位置**：`sre_control/pool_planner.py:75-76`
- **代码**：`sigma = max(self.min_keep_alive, min(self.max_capacity, int(demanded) + 1))`
- **行为对照**：
  - `demanded = 2.0` ⇒ `int(2.0) + 1 = 3`（多分配 1 个）；
  - `demanded = 2.001` ⇒ 3（正确 ceiling）；
  - `demanded = 3.0` ⇒ 4（多分配 1 个）；
- **真正 ceiling 应是** `math.ceil(demanded)`。当前实现在整数边界永远多分配 1。
- **影响**：成本计算 `total_cost = unit_cost * sigma` 会比真实 ceiling 高一点；`baseline_cost` 对比比率被略微低估。
- **测试覆盖**：`tests/test_sre_control.py:18-25` 仅断言 `s >= 4`，不区分 ceiling vs ceiling+1。
- **修复**：`int(math.ceil(demanded))` 或显式 `math.ceil(demanded)`。

---

## F11 [M] · `make_event` 接受任意 `**fields`，不做任何校验

- **位置**：`sre_control/events.py:61-78`
- **代码**：`def make_event(stage, kind, detail, safe_action, **fields): ... return {..., **fields}`
- **后果**：调用方可以注入任何键值对（包括拼写错的官方字段，例如 `recoverable=False`→`recoveravle=False`）。`validate_event` 只检查"必须有的字段"，不检查"不允许有什么字段"。
- **当前测试**：`test_event_schema.py` 覆盖了正向 schema，但没覆盖反向（拼写错误 / 未知字段 / 类型错误的 extras）。
- **修复**：要么在 `make_event` 用每个 kind 的字段白名单校验 `**fields`，要么在 `validate_event` 加 unknown-field 扫描。

---

## F12 [M] · `validate_event` 只对 `bounded_ls_residual` 与 `adapter_exception` 做 kind-specific 校验

- **位置**：`sre_control/events.py:81-113`
- **未覆盖 kind**：`missing_sensor` / `outlier_rejected` / `rollout_rejected` / `replica_bound_active` / `unsafe_proposal_projected` / `pool_capacity_clipped` / `topology_state_repaired` / `deadline_exceeded` / `stability_violation` — 这 9 个 kind 没有任何 kind-specific 字段断言。
- **后果**：例如 `outlier_rejected` 在生产里通常带 `innovation_mahalanobis`、`threshold_used`、`consecutive_rejections`，但 `validate_event` 不强制；如果 adapter 改了实现少传一个字段，下游 dashboard 才会发现。
- **修复**：把每个 kind 的"应有字段"列表写成 schema，validate_event 全 kind 校验。

---

## F13 [M] · `evidence_manifest.main` 通过 monkey-patch 模块全局变量替换 `ARTIFACTS`

- **位置**：`analysis/evidence_manifest.py:84-95`
- **代码**：
  ```python
  original_common_artifacts = _common.ARTIFACTS
  original_s10_artifacts = s10_failure_trace.ARTIFACTS
  try:
      _common.ARTIFACTS = artifacts
      s10_failure_trace.ARTIFACTS = artifacts
      ...
  finally:
      _common.ARTIFACTS = original_common_artifacts
      s10_failure_trace.ARTIFACTS = original_s10_artifacts
  ```
- **风险**：
  1. **非线程安全**：并行 pytest（`pytest -n auto`）下两个 worker 同时跑 `evidence_manifest` 会互相覆盖；
  2. **异常路径**：如果 `s10_failure_trace.main()` 抛错前已经修改了别处缓存（如 matplotlib 默认 DPI），恢复路径不完整；
  3. **测试可见的副作用**：`tests/test_evidence_manifest.py` 跑完之后 `_common.ARTIFACTS` 已被恢复，但模块状态混乱风险一直在。
- **修复**：把 `ARTIFACTS` 改成函数参数贯穿到底，不要用模块全局变量做隐式上下文。

---

## F14 [M] · `analysis/s10_failure_trace.py:340-341` 写 JSONL 不用 `sort_keys`

- **位置**：`analysis/s10_failure_trace.py:339-341`
- **对照**：`analysis/evidence_manifest.py:35-39` 写 JSON 用 `sort_keys=True`；写 JSONL 也用 `sort_keys=True`（`_write_jsonl`）。
- **但 s10 直接用 `json.dumps(row)`，无 sort_keys**。
- **风险**：CPython 3.7+ 保证 dict 插入序，所以**实际**字节稳定；**但**任何重构改变事件构造顺序（如 `make_event(**fields)` 中 `**fields` 顺序变化）就会改变 JSONL 字节，**byte-identity check 失败**。
- **修复**：`json.dumps(row, sort_keys=True)`，统一字节稳定性策略。

---

## F15 [M] · `quality_gate_counts.py` 的 7 处 `replace_once` 在文档 i18n 后必失败

- **位置**：`scripts/quality_gate_counts.py:152-211`
- **样例正则**：`r"\| 单元测试 \| `python -m pytest tests` \| \*\*\d+ passed\*\* \|"`
- **当前依赖**：中文 markdown 表格头"单元测试"必须存在且与 `python -m pytest tests` 列同行。**任何**列名、空格、bullet 调整都会让 regex 不匹配 → `RuntimeError: missing PR NFR pytest quality gate`。
- **现状**：`RuntimeError` 信息没带 file path，调试痛苦。
- **修复**：要么把 7 个目标的 (path, pattern, replacement) 抽成数据驱动配置，要么把 7 处独立测试用 fixture 覆盖（已有 `tests/test_quality_gate_counts.py`，需扩充）。

---

## F16 [M] · `_is_negated_boundary_wording` 只看 match 之前的上下文，看不到之后

- **位置**：`scripts/evidence_boundary_lint.py:65-70`
- **代码**：`prefix = line[:match_start].lower()` + 前 8 行 context_prefix。
- **盲区**：句子 `"This is production-ready, but not in a production-grade sense."` 触发 `production-ready` 匹配，匹配点之前的 prefix 是 `This is `，无否定提示；之后才有 `but not`，**lint 错误放过**。
- **影响**：评审 wording lint 可能放过部分"先肯定后否定"的句式。
- **测试覆盖**：未覆盖（`test_evidence_boundary_lint_flags_unsafe_production_claims` 只测正向）。
- **修复**：把否定窗口扩展到 match 之后 100 字符内，或要求紧邻 否定标记。

---

## F17 [M] · `SREControlStack._tick_index * dt` 假设 dt 不变

- **位置**：`sre_control/stack.py:198-200`
- **代码**：`tick_time = self._tick_index * dt` — 用当前 tick 的 dt 乘累计 tick 数。
- **问题**：若 dt 在不同 tick 间变化（如自适应 dt），`tick_time` 与实际累计时间不一致。
- **后果**：`StabilityMonitor` 用错误时间戳做 dV/dt 估计，monitor 可能误报或漏报。
- **测试覆盖**：`tests/` 全部用恒定 dt=5.0。
- **修复**：维护 `_accum_time += dt`，把 `_tick_index` 单纯当计数用。

---

## F18 [M] · `WeightedLoadBalancer._matrix()` 假设 `zone_vector` 维度都相同但不校验

- **位置**：`sre_control/weighted_balancer.py:50-57`
- **代码**：`for dim in range(len(self.instances[0].zone_vector))` — 用第 0 个 instance 的维度作为基准。
- **风险**：若用户传入 instances 时不同实例的 `zone_vector` 长度不同（编程错误），代码不会立即报错，而是在矩阵构造时数组维度不匹配抛 `ValueError`，错误信息晦涩。
- **修复**：在 `__post_init__` 中校验所有 instances 的 `zone_vector` 同维。

---

## F19 [M] · `Signal.gate_threshold` 没有上下限校验

- **位置**：`sre_control/signal_fusion.py:34-54`
- **风险**：`gate_threshold=0` 或 `negative` 不会被拒绝；前者会拒绝所有更新（任何 Mahalanobis ≥ 0），后者会接受所有更新。
- **修复**：`__post_init__` 校验 `gate_threshold is None or gate_threshold > 0`。

---

## F20 [M] · `SignalFusion._rejections` 计数器无 TTL，长跑无上界

- **位置**：`sre_control/signal_fusion.py:135-160`
- **行为**：连续被 gate 拒绝的 sensor，`_rejections[name]` 单调递增；只有一次成功更新才会清零（L164）。
- **风险**：长跑场景下一个被永久 gate 的 sensor 让计数器无限增长，detail 字符串变长占内存。Python 内 int 无溢出，但 JSON 序列化大数字会让 trace 文件膨胀。
- **修复**：增加 `max_consecutive_rejections` 上限，超限触发 `outlier_rejected` 之外的"sensor 故障"语义。

---

## F21 [M] · `s11_catch_sre_wrapper` 的 baseline 在 `placement_infeasible` 类下不暴露问题

- **位置**：`analysis/s11_catch_sre_wrapper.py:120-128`
- **设计**：baseline 在 placement_infeasible 走 `[0.5*placement[0], 0.5*placement[0], placement[1]]` — 简单平均拆 east 双实例，west 全压一个。
- **观察**：baseline `rps_residual=0`，但 west_a 容量被打爆（`_capacity_violation > 0`）。这是教育性反例。
- **但是**：测试 `test_catch_sre_wrapper_covers_feasible_overload_and_placement_cases` 写死了 `case_counts == {feasible:40, total_overload:40, placement_infeasible:40}`。**如果 `n_cases` 默认值变化或 `cases_per_regime = max(1, n_cases // 3)` 出现整除问题**，硬编码 40 立刻断。耦合脆。
- **修复**：测试断言改成 `case_counts['feasible'] == case_counts['total_overload'] == case_counts['placement_infeasible'] >= 1`。

---

## F22 [M] · `EKF.covariance_eigenvalue_floor` 默认 0 导致沉默失败可能性

- **位置**：`starship/ekf.py:43`
- **观察**：`covariance_eigenvalue_floor: float = 0.0` 默认关闭。`tests/test_ekf.py:88-113` 的 `test_covariance_eigenvalue_floor_limits_posterior_overconfidence` 显式设置 1e-3 才能保护。
- **未覆盖路径**：用户用默认值跑长时间低噪声更新会让 P 缓慢塌缩，没有任何报警。
- **修复**：把默认改成机器精度量级（如 1e-12），或在 `__post_init__` 检测到 `Q = 0` 且 `R` 极小时打 warning。

---

## F23 [M] · `s10_trace_shape_errors` 用 `t_seconds == tick * DT` 严格 1e-9 比较

- **位置**：`analysis/evidence_report.py:576-581`
- **代码**：`if abs(float(t_seconds) - tick * s10_failure_trace.DT) > 1e-9`
- **风险**：DT 改为非有限二进制小数（如 0.1）时，浮点累积误差超过 1e-9，**evidence_report 红线**。当前 DT=5.0 浮点精确，所以 OK。
- **修复**：`abs(...) > 1e-6 * max(1.0, tick)` 或换成 `math.isclose(rel_tol=1e-9)`。

---

## F24 [L] · 多处 tolerance 常量散落，无统一

- **位置**：以下文件各自定义自己的 1e-6/1e-9/1e-12：
  - `sre_control/stack.py:110`：`1e-6` reuse-shares 容差
  - `sre_control/weighted_balancer.py:71,76,79`：`1e-6` 与 `1e-9` 混用
  - `sre_control/canary_scheduler.py:76,102`：`1e-9` 与 `1e-6`
  - `sre_control/topology_state.py:65,80`：`1e-12` 与 `1e-6`
  - `sre_control/slo_guardrail.py:52,79,100`：`1e-12` 与 `1e-4` 与 `1e-9`
- **风险**：等价语义在不同模块用不同容差，跨模块组合时可能出现"上游认为 0，下游认为非 0"的不一致判断。
- **修复**：在 `sre_control/_tolerances.py` 或 `sre_control/constants.py` 集中定义命名常量（`EPS_ALLOCATION_SHARE`、`EPS_TRUST_REGION`、`EPS_NUMERIC_NORM` 等），各处 import。

---

## F25 [L] · `_adapter_family` 硬编码字典与 `event_stage_routes` 重复

- **位置**：`sre_control/stack.py:122-129` 与 `sre_control/stack_contract.py:17-23`
- 同一份知识写两遍 — 见 F04 已说明对齐冲突；单纯纪律建议是**单一信息源**。
- **修复**：把 `_adapter_family` 改为查 `stack_data_contract()['event_stage_routes']`（同 F04 修复）。

---

## F26 [L] · `analysis/s05_ekf.py:104` 局部变量 `z` 遮蔽参数 `z`

- **位置**：`analysis/s05_ekf.py:100-105`
- **代码**：
  ```python
  def radar_to_xyz(z: np.ndarray) -> np.ndarray:
      rng_, az, el = z
      x = rng_ * np.cos(el) * np.cos(az)
      y = rng_ * np.cos(el) * np.sin(az)
      z = rng_ * np.sin(el)         # shadows the parameter
      return np.array([x, y, z])
  ```
- **影响**：可读性差；类型检查器可能报 warning。`x,y,z` 是输出坐标三元组的 `z` 与输入 numpy `z` 同名，纯遮蔽。
- **修复**：把局部变量改名 `z_out` 或 `z_coord`。

---

## F27 [L] · `_run_scenario` finally 不能保护 `entry` 未定义场景

- **位置**：`analysis/s10_failure_trace.py:196-208`
- **代码**：`try: entry = stack.step(...); finally: stack.autoscaler.replicas_max = original`
- **观察**：若 `stack.step()` 抛 programmer error（按 I-5 透传），`entry` 未定义，L208 的 `entry["replicas_next"]` 抛 `UnboundLocalError`。但 try/finally 的 finally 已经恢复了 `replicas_max`，正确。
- **小问题**：捕获 + finally 把"分析报告"挂掉的体验从一个 stack trace 变成两个；可考虑 `entry = None`/早返。
- **修复**：可选。

---

## F28 [L] · `s10_failure_trace._derive_metrics` 把内部数据藏在 `_counts`/`_kinds_per_tick`/`_all_kinds` 下划线键

- **位置**：`analysis/s10_failure_trace.py:264-280`
- **观察**：用 `_counts` 这种"私有"键混在公共 metrics dict 里，再在 main() 中 `{k: v for k, v in before.items() if not k.startswith("_")}` 过滤。这是反模式 — 应该用 dataclass 或 NamedTuple 分离 public/private 字段。
- **修复**：拆成 `MetricsResult(metrics: dict, internal: dict)`。

---

## F29 [L] · `_RecoverableBalancer` / `_RecoverableFusion` 测试用 monkey-patch

- **位置**：`tests/test_contracts.py:256-260, 261-269, 等`
- **观察**：通过 inline subclass 替换实例方法。功能正常；但读者要在 4+ 处看到同样模式。
- **修复**：在 `tests/conftest.py` 提供 `make_recoverable_<adapter>(message)` 工厂函数。

---

## F30 [L] · `tests/test_evidence_manifest.py` 90 KB 单文件

- **位置**：`tests/test_evidence_manifest.py`
- **已在 v1.0 主报告 §5.2 提到**，本文档不重复。

---

## F31 [L] · `analysis/evidence_report.py` 把"first error wins"做成 break

- **位置**：例 `_s12_trace_shape_errors:597-612` 等多处 `break` 在循环里。
- **设计**：一旦发现第一个错误就停，避免噪音。对单次复查有效，但**多人合并时**只能修一个错再跑、再修一个错再跑，效率低。
- **修复**：把所有错误改成 collect-all 模式（`continue` 而非 `break`），main() 决定要不要早返。

---

## F32 [L] · `PoolCapacityPlanner.plan` 的 `rps_per_conn = 100.0` 硬编码

- **位置**：`sre_control/pool_planner.py:56`
- **观察**：硬编码常量 `rps_per_conn = 100.0`，与 `PredictiveAutoscaler.per_replica_rps=100.0` 默认值相关但**没有交叉引用**。
- **修复**：把 `rps_per_conn` 提到 dataclass 字段，让两个 adapter 共享。

---

## F33 [L] · `FastTrafficSwitcher.plan` 不校验 `rate_max > 0`

- **位置**：`sre_control/fast_switcher.py:68`
- **代码**：`np.sqrt(mag / self.rate_max)` — `rate_max <= 0` 时 ZeroDivision 或 sqrt(neg)。
- **修复**：`__post_init__` 校验。

---

## F34 [L] · `PredictiveAutoscaler.replica_bound_active` 不区分"刚触底"vs"一直贴底"

- **位置**：`sre_control/predictive_autoscaler.py:95-101`
- **观察**：只要 `next_replicas in (min, max)` 就发 event，包括上次也在 min/max 且 u=0 的稳态情况。下游做 incident dashboard 看到一长串"持续 active"的事件。
- **修复**：加内部状态记录上次 next_replicas，仅在新进入/离开边界时发 event；或在 event detail 加 `transitioned: bool`。

---

## F35 [L] · `TopologyState.distance_to` 把位移用 Euclidean 加在角度上

- **位置**：`sre_control/topology_state.py:127-137`
- **代码**：`return dr + dtheta` — 位移 (m) 与角度 (rad) 直接相加无单位转换。
- **观察**：作为研究 helper 写法可接受，但缺少单位匹配 doc。
- **修复**：把 `dr` 改成无单位（除以 reference length）或在 docstring 标注"useful only when dr/dtheta are pre-normalised by domain"。

---

## F36 [L] · `analysis/evidence_report._iter_entry_events` 每次 i/o，未缓存

- **位置**：`analysis/evidence_report.py:1443-1457`
- **观察**：generator，每次调用 `read_text` + `json.loads`。当前只调用一次，但若加更多检查需要复用。
- **修复**：把 events 列表实际化或对路径加 LRU 缓存。

---

## F37 [L] · `_recovery_diagnostics` 把"未恢复"用 `float("inf")` 标记，JSON 不可序列化

- **位置**：`analysis/evidence_report.py:911-943` 与 `analysis/s12_sre_replay.py:107-140`
- **观察**：`max_recovery_ticks` 可能是 `inf`。在 `s12` 里 `summary_banner` 把它格式化为 `inf` 字符串，但 JSON 序列化 `json.dumps(float("inf"))` 会**抛 `ValueError: Out of range float values are not JSON compliant`**（CPython 默认 `allow_nan=True` 会输出 `Infinity`，但 strict mode 拒绝）。
- **当前测试**：fixture 设计永远 finite，所以不触发，但**架构上不健壮**。
- **修复**：把 `float("inf")` 替换为 `None` 或 `-1`/字符串 `"unrecovered"`，所有下游一致处理。

---

## F38 [L] · `evidence_report._matches_manifest_type` 对 `tuple[int, float]` 的处理

- **位置**：`analysis/evidence_report.py:124-136`
- **代码**：当 `expected_type` 是 `(int, float)` 元组时，先把它当作"接受 int 或 float"处理；并显式排除 bool。但是**布尔在 Python 里是 int 的子类**，处理对，但读起来需要心算。
- **修复**：添加 docstring 说明 `_matches_manifest_type((int, float), True) is False`。

---

## F39 [L] · `_is_sha256` 只接受小写十六进制

- **位置**：`analysis/evidence_report.py:57-62`
- **代码**：`all(char in "0123456789abcdef" for char in value)` — 不接受大写。
- **观察**：`hashlib.sha256().hexdigest()` 永远小写，所以当前 OK；但若手写 manifest 测试，大写哈希会被拒绝。
- **修复**：`value.lower()` 或显式 doc。

---

## F40 [L] · `EVENT_COUNTEREXAMPLES` 11 个 kind 没机器可读分组

- **位置**：`sre_control/events.py:11-58`
- **观察**：counterexample 是字符串，但**没有元数据**说明该 kind 属于哪个 stage、是否 transient 等。导致 `_adapter_family` 与 `event_stage_routes` 都要重新枚举。
- **修复**：把 EVENT_COUNTEREXAMPLES 改成
  ```python
  EVENT_KINDS = {
      "missing_sensor": {
          "stages": ["SignalFusion"],
          "transient": True,
          "counterexample": "Do not ..."
      },
      ...
  }
  ```
  让单一数据源驱动所有路由表。

---

## F41 [L] · `analysis/run_all.py` import 时不 catch ImportError

- **位置**：`analysis/run_all.py:35-37`
- **代码**：`mod = importlib.import_module(name); result = mod.main()`
- **观察**：任何一个 study 失败会导致后续 study 不跑，但 SUMMARY.txt 只写已成功的 banner。下次运行不知道是哪个 study 失败。
- **修复**：包装 try/except per study，把失败记录写入 SUMMARY，最后 sys.exit(1)。

---

## F42 [L] · `tests/test_synthetic_evidence_boundaries.py::test_sre_replay_fixture_is_labeled_and_covers_expected_event_kinds` 写死 5 个 operator_actions

- **位置**：`tests/test_synthetic_evidence_boundaries.py:100-114`
- **观察**：硬编码完整 dict 与字符串，任何 fixture 文案优化都会让测试改一遍。
- **修复**：测试改成"key set 覆盖 5 类" + "每类至少一个非空字符串"，把语义而非字面值钉死。

---

## 综合修复优先级

| 优先级 | 涉及 finding | 改动面 | 建议处理时机 |
|---|---|---|---|
| **P0 立即** | F02, F03 | 包 try/except + 校验 res.success | 下一轮 PR 内必修，避免在生产场景下 SREControlStack 崩溃 |
| **P1 下一 PR** | F01, F04, F05, F11, F12 | 修 bang-bang 终点 + 对齐两套 family 表 + L2/sum 约定 + event schema 字段白名单 | 与文档同步 |
| **P2 后续 PR** | F06–F23 | 数值一致性 / 边界校验 / 全局变量隔离 / 字节稳定性 | 按优先级排队 |
| **P3 长期纪律** | F24–F42 | 重构/可维护性 | 与 v1.0 主报告 §6 重构窗口合并 |

---

**Opus 4.7 / 2026-05-25 / spacex-session @ 8d8e064**
