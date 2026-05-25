# Open Risks

This page tracks risks that are still useful for future review. It is not a bug
list. Items already resolved in code and tests are recorded in
`docs/claude-development-audit/backlog.md`.

## Current Risk Summary

| ID | Priority | Area | Risk | Suggested next step |
|---|---|---|---|---|
| R1 | P2 | Synthetic evidence boundary | Before/after studies are synthetic scenario evidence and can still be overgeneralized in new prose or external summaries. | Keep reports and summaries explicit that these are scenario-internal results; live review docs now have an overclaim wording lint. |
| F50 | **P1** | PredictiveAutoscaler MPC | ZOH 后 `Bd = B · dt` 让 MPC 内部"u=1"等于 5 个 replica，但 executor 直接 `+u`；MPC 系统性欠下达 5× | 二选一：executor 改 `+u*dt`，或 B 缩放为 `B/dt`；新增 plant/executor 一步演化一致性测试。详见 `claude-review/docs/v2026-05-26/03-new-findings.md#f50` |
| F51 | **P1** | StabilityMonitor | 反向差分用窗口最旧样本作为 anchor，单个 V 尖峰污染后续 `window-1` 个 tick，恢复期仍报 violating | 改 recent-pair 差分，或在单调下降时驱逐 anchor；新增 spike→recovery 回归测试 |
| F52 | P2 | CanaryScheduler | `_last_share=0.0` 默认值在 warm-start 时引入幻影斜率，污染 trust-region | 增加 `_initialised` flag，首次 observe 仅记录初值不 refit |
| F53 | **P1** | SREControlStack × StabilityGuard | `stability_violation` 触发后 autoscaler/canary 仍按常规参数执行；红线只是装饰，与文档不一致 | 三选一：文档收敛声明 observe-only；部分接入 clamp autoscaler.max_step；或全面接入 stability state 作为 step 输入 |
| F54 | **P1** | SLOGuardrail | NaN proposal 透传不 raise、不 emit event；下游 NaN 污染 balancer 后才崩，fault localisation 失效 | `audit` 顶部 `np.isfinite(proposal).all()` 校验：要么 raise `AdapterInputError`，要么发出 `unsafe_proposal_projected(reason=non_finite_input)` |
| F55 | P2 | SREControlStack | autoscaler `last_trace` 在 recoverable fallback 路径滞留旧值，遥测与实际执行不一致 | fallback 分支显式覆盖 `last_trace = {fallback: True, ...}` |
| F56 | P2 | SignalFusion | `_rejections` 按 `Signal.name` 索引；同名重复 Signal 计数器互覆 | 改用 `id(signal)` 索引，或构造期校验 name 唯一性 |
| F57 | P3 | SREControlStack | `_can_reuse_last_good_alloc` 对 NaN 不敏感（NaN 比较恒 False） | 循环里加 `not np.isfinite(share)` 拒绝条件 |
| F58 | P3 | PoolCapacityPlanner | 精确饱和（`sigma == max_capacity` 且 `shortfall == 0`）跳过 `pool_capacity_clipped` 事件 | 新增 `pool_at_capacity` advisory，或扩展现有事件在 `clipped_slots=0` 时也发出 |
| F59 | P3 | TopologyState | `ring_angle_rad` 实际区间 `[-2π, 2π]` 与 docstring `[-π, π]` 不一致 | 增加 mod-wrap 或更正 docstring；加参数化测试覆盖 ±0.5 / ±1.5 / ±2.5 / ±3.5 |
| F60 | P3 | tests | OU sanity 测试用相同解析公式回算 expected_state，是同义反复式自验证 | 用 `scipy.linalg.expm` 或精细 Euler 多步积分作为独立 oracle |
| G1 | P2 | Evidence manifest process | matplotlib PNG 跨机器 byte-identity 易漂移；reviewer 漏跑 `evidence_manifest` 会复现 `artifact_identity_mismatch` 假阴性 | `scripts/quality_gate_counts.py` 自愈合或 PNG 写入端 strip 非确定 chunk；packet "review commands" 强调先 manifest 再 report |

**说明**：F50–F60 与 G1 来自 Opus v2.0 评审（2026-05-26），详见
`claude-review/docs/v2026-05-26/03-new-findings.md` 与 `04-evidence-manifest-audit.md`。

## Resolved Since Earlier Packets

These used to appear as active risks in older review material, but current code
and tests now cover them:

- Per-sensor innovation gate policy.
- Allocator recoverable fallback reusing last-good shares.
- EKF Joseph covariance update and covariance symmetrization.
- Docs/schema sync between runtime event registry and markdown docs.
- Package discovery and installed-wheel smoke.
- Control-center localhost exposure policy.
- Release/spec version hygiene.
- Canonical HTML entry: V2 is current, V1 is an archive snapshot.
- Section 10 `replica_bound_active` expected-kind coverage is tightened to
  full-window coverage in the bounded-capacity demand surge window.
- Section 5 includes radar + near-field fiducial updates, source-use metrics,
  and near-field position improvement over radar-only EKF.
- StabilityGuard now includes a documented SRE error-budget energy helper
  (`sre_error_budget_V`) and stack-level tests that emit
  `StabilityGuard/error_budget` events.
- Catch/SRE wrapper boundary is now implemented as `sre_control.CatchLoadAdapter`.
  It emits existing `bounded_ls_residual` evidence through the SRE layer while
  `starship/` remains import-clean under `tests/test_import_graph.py`. Section
  11 now covers feasible, total-overload, and placement-infeasible synthetic
  regimes.
- Section 12 adds a fixed synthetic replay fixture for SRE stack inputs. It is
  explicitly labeled as replay evidence and currently reports full expected-kind
  visibility, error-budget stability visibility, and zero nominal background
  events. It also reports event-clean recovery windows with max recovery of one
  replay tick, each expected event row has an operator-action annotation, and
  one 3-tick compound incident has full multi-signal coverage plus a
  window-level operator action.
- `analysis.evidence_manifest` now exports a repo-relative
  `event_evidence_manifest.json` index plus Section 11 diagnostics and Section
  12 replay trace/diagnostics artifacts for reviewer inspection.
- `docs/EVENT_EVIDENCE_MANIFEST.md` documents the manifest contract, and
  `tests/test_evidence_manifest.py` checks generated entries against that
  markdown table.
- `analysis.evidence_report` provides a reviewer CLI over the manifest and
  fails when a referenced artifact is missing, malformed, has invalid runtime
  events, has key counts that disagree, or has a stale byte-identity record
  where the artifact SHA-256 digest or size no longer matches the manifest.
- `scripts.quality_gate_counts` now fails if `analysis.evidence_manifest` or
  `analysis.evidence_report` drops out of the current PR/V2 quality-gate docs.
- `analysis._common.summary_banner` now renders zero-baseline before/after
  ratios as `ratio=undefined; zero baseline` instead of an infinite multiplier.
- `starship.EKF` now has an opt-in `covariance_eigenvalue_floor` to prevent
  repeated low-noise updates from collapsing the covariance below a configured
  floor; `tests/test_ekf.py` covers the overconfidence regression.
- `starship.StabilityMonitor` now has an opt-in `min_derivative_dt` so tiny
  timestamp deltas can be ignored instead of turning scheduler jitter into
  large finite-difference derivatives.
- `WeightedLoadBalancer` and `CatchLoadAdapter` now expose
  `demand_satisfied` and `rps_residual_fraction`, and propagate those fields in
  `bounded_ls_residual` events so safe projection cannot be mistaken for fully
  satisfied demand.
- `adapter_exception` events now include `adapter_family`, `fault_family`, and
  `fallback_action`, so recoverable failures can be routed by stage family and
  concrete fallback path rather than by exception class alone.
- `tests/test_synthetic_evidence_boundaries.py` now lints live review docs for
  unqualified production-readiness, official SpaceX implementation, and
  production-proof wording while allowing explicit negated boundary statements.
- `sre_control.stack_data_contract()` now exports the current
  `SREControlStack.step()` stage boundaries as research metadata with
  `production_claim=false`, including each stage's direct runtime event kinds
  and runtime-stage routing prefixes. `docs/STACK_DATA_CONTRACT.md` documents
  the contract shape, and `analysis.evidence_report` rejects contract artifacts
  that drift from the runtime event registry or disallow events observed in the
  generated traces.
- Opus v1.0 P0/P1 remediation is reflected in code, tests, and docs: bounded-LS
  solver failures are recoverable, singular EKF innovation covariance gates the
  update, traffic-switch safety margin no longer overshoots the endpoint,
  adapter-family routing uses the stack data contract, strict per-kind event
  schemas cover all 11 runtime kinds, and the F05 action-vector ambiguity is
  recorded as an explicit L2-magnitude contract paired with separate
  `zone_target` placement.
- Opus F14 is resolved for Section 10 evidence artifacts: S10 full/sample JSONL
  traces now use sorted JSON keys, and the failure-trace tests assert serialized
  key order so manifest byte identity is not sensitive to dict construction
  order.
- Opus F23 is resolved in the evidence report: S10 trace-time validation now
  allows tick-scaled floating-point drift while still rejecting whole-second
  mismatches.
- Opus F07 is resolved in `SignalFusion`: the default OU process model now uses
  exact exponential discretization for both state prediction and Jacobian, so
  large `theta * dt` values no longer flip the prediction sign.
- Opus F10 is resolved in `PoolCapacityPlanner`: pool sizing now uses true
  `math.ceil(demanded)` so exact integer demand no longer over-allocates one
  connection slot.
- Opus F19 is resolved for `SignalFusion`: per-sensor and fusion-wide
  `gate_threshold` values must now be positive when set, with `None` preserved
  as the no-gating mode.
- Opus F18 is resolved in `WeightedLoadBalancer`: empty instance lists and
  mismatched `zone_vector` dimensions are rejected at construction time instead
  of failing later during bounded-LS matrix assembly.
- Opus F33 is resolved in `FastTrafficSwitcher`: non-positive `rate_max` values
  are rejected at construction time instead of flowing into the minimum-time
  square-root calculation.
- Opus F21 is resolved for Section 11 test robustness: the catch/SRE wrapper
  regime-coverage test no longer hard-codes the default 40 cases per regime and
  instead checks equal, non-empty coverage across all three regimes.
- Opus F16 is resolved in the evidence-boundary lint: negated boundary wording
  now checks a short suffix window after the matched overclaim phrase, not only
  the prefix context.
- Opus F37 is resolved for recovery diagnostics: unrecovered windows are now
  represented as strict-JSON `null` values instead of non-standard `Infinity`
  in both generator-side and report-side diagnostics.
- Opus F42 is resolved for replay fixture test robustness: operator-action
  checks now require coverage and non-empty strings per expected event kind
  instead of hard-coding the exact action prose.
- Opus F39 is resolved in the evidence report: SHA-256 metadata shape checks now
  accept uppercase hexadecimal characters while byte-identity comparison remains
  exact.
- Opus F32 is resolved in `PoolCapacityPlanner`: `rps_per_conn` is now a
  configurable dataclass field used consistently by sizing and shortfall
  calculations.

## Numerical Risks

| Risk | Concrete behavior | Impact |
|---|---|---|
| **F50 — PredictiveAutoscaler MPC 单位错配** | ZOH 后 plant 模型与 executor 对 `u` 物理意义不一致：MPC 认为 1 单位 = `per_replica_rps * dt`，executor 当作 1 replica/step | 控制指令系统性欠下达；scenario 测试因 `max_step` 饱和路径而通过，对抗路径会暴露 |
| **F51 — StabilityMonitor 反向差分滞后** | `dV/dt = (V_new - V_oldest_in_window)/(t_new - t_oldest)`；窗口内任一尖峰会污染后续 `window-1` 个 tick | 恢复期持续假阳性 `stability_violation`；与 latch-until-reset 叠加可能长时间挂红 |
| **F54 — SLOGuardrail NaN 静默放过** | NaN 比较恒 False，所有 violation flag 不触发；NaN proposal 透传到 balancer 才崩 | fault localisation 错位、原始 programmer-error 信号丢失 |
| 历史无其他数值风险记录（v1.0 评审遗留项已闭合）。 | 保持新数值断言绑定 scenario-specific 测试与制品。 | 把新数值证据视为未验证，直到有回归测试或生成制品。 |

## Modeling Risks

| Risk | Concrete behavior | Impact |
|---|---|---|
| SRE analogy overreach | Convexification, MPC, and EKF are migrated abstractions, not proof that rocket controllers directly map to production systems. | Docs must avoid implying official SpaceX implementation or production equivalence. |
| Single-stack orchestration | `SREControlStack` still chains adapters in one process, but its stage inputs/outputs, direct event kinds, and runtime-stage routes are now exported as a non-production data contract. | Future work can split along the exported boundaries if this becomes more than a research stack. |
| Event-kind evolution | `adapter_exception` now carries stage-family, fault-family, and fallback-action fields, and the stack data contract binds stage event kinds plus observed trace events to the shared runtime registry. Future additions should keep this as a stable payload extension rather than minting new event kinds for every adapter failure. | Future review may need finer remediation playbooks, but the event payload is now routeable by adapter family and contract drift is report-checked. |
| Action magnitude contract | `SREControlStack.step()` treats `safe_action` as a guardrail direction vector whose L2 norm is scalar RPS demand; `zone_target` is the separate placement distribution. | Future work that changes `safe_action` semantics must update the stack contract, Section 10 evidence expectations, and allocator tests together instead of switching to component sums locally. |

## Suggested Next PR

Prefer one of these research-landing slices（按 Opus v2.0 评审优先级排序）：

1. **修 F50 / F53 / F54 任一项**（推荐 F53：仅需文档收敛 + 1 行 stack 改动
   即可让"stability 红线"真实接入闭环）。
2. **修 F51**：把 stability_monitor 反向差分换成 recent-pair，加恢复期回归
   测试。改动局限，回归风险低。
3. **修 F50**：autoscaler MPC 单位错配；改 executor 侧或 B 矩阵都可。需要
   配套 plant/executor 一致性测试。
4. **修 G1**：让 `scripts/quality_gate_counts.py` 在校验前自愈合执行
   `manifest → report` 序列，或在 PNG 写入侧 strip 非确定 chunk。
5. Add release-pipeline automation only if this repository starts publishing
   versioned artifacts.
6. Continue review-ledger hygiene when new packets are added, keeping old
   packets labeled as historical when their findings are already resolved.
