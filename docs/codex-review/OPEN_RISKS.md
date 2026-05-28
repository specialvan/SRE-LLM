# Open Risks

This page tracks risks that are still useful for future review. It is not a bug
list. Items already resolved in code and tests are recorded in
`docs/claude-development-audit/backlog.md`.

## Current Risk Summary

| ID | Priority | Area | Risk | Suggested next step |
|---|---|---|---|---|
| R1 | P2 | Synthetic evidence boundary | Before/after studies are synthetic scenario evidence and can still be overgeneralized in new prose or external summaries. | Keep reports and summaries explicit that these are scenario-internal results; live review docs now have an overclaim wording lint. |

**说明**：F50-F60 来自 Opus v2.0 评审（2026-05-26），F61-F81 来自 Opus v2.1
继续评审（2026-05-28），均已在当前工作区修复或收敛为文档/台账边界说明；G1 也已通过
`scripts.quality_gate_counts` 自愈合顺序修复。原始评审详见
`claude-review/docs/v2026-05-26/` 与 `claude-review/docs/v2026-05-28/`。

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
- Opus F13 is resolved in `analysis.evidence_manifest`: artifact directories are
  now passed explicitly into the Section 10/11 generators instead of
  monkey-patching `_common.ARTIFACTS` or `s10_failure_trace.ARTIFACTS`.
- `docs/EVENT_EVIDENCE_MANIFEST.md` documents the manifest contract, and
  `tests/test_evidence_manifest.py` checks generated entries against that
  markdown table.
- `analysis.evidence_report` provides a reviewer CLI over the manifest and
  fails when a referenced artifact is missing, malformed, has invalid runtime
  events, has key counts that disagree, or has a stale byte-identity record
  where the artifact SHA-256 digest or size no longer matches the manifest.
- `scripts.quality_gate_counts` now fails if `analysis.evidence_manifest` or
  `analysis.evidence_report` drops out of the current PR/V2 quality-gate docs.
- Opus F15 is resolved in `scripts.quality_gate_counts`: current-facing pytest
  count replacements now come from `QUALITY_GATE_TARGETS`, and replacement
  failures include the affected target path.
- `analysis._common.summary_banner` now renders zero-baseline before/after
  ratios as `ratio=undefined; zero baseline` instead of an infinite multiplier.
- `starship.EKF` now defaults `covariance_eigenvalue_floor` to `1e-12` to
  prevent repeated low-noise updates from silently collapsing covariance; an
  explicit `0.0` remains the opt-out path, and `tests/test_ekf.py` covers the
  overconfidence regression.
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
- `scripts.evidence_boundary_lint.PUBLIC_EVIDENCE_BOUNDARY_DOCS` now defines the
  public/review document surface linted by
  `tests/test_synthetic_evidence_boundaries.py`, including README, PR spec, wiki,
  V2 HTML, Codex review, Opus review, and audit-ledger entry points. It rejects
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
- Opus F06 is resolved for Section 10 scenario feedback: `_run_scenario()` now
  records the stack-returned `replicas_next` directly instead of applying a
  hidden floor, while the post-bound recovery forecast floor is explicit and
  keeps injected-window evidence isolated.
- Opus F23 is resolved in the evidence report: S10 trace-time validation now
  allows tick-scaled floating-point drift while still rejecting whole-second
  mismatches.
- Opus F07 is resolved in `SignalFusion`: the default OU process model now uses
  exact exponential discretization for both state prediction and Jacobian, so
  large `theta * dt` values no longer flip the prediction sign.
- Opus F08 is resolved in `CanaryScheduler`: rejected rollout observations now
  refit the local slope and tag the trace with `refit_rejected`, so repeated
  SLO-burning trials no longer leave the SCP model at `_b_est=0`.
- Opus F09 is resolved in Section 10 evidence metrics: empty injected-window
  visibility now follows the same vacuous-truth convention as
  `analysis.evidence_report`, while empty background windows still report zero
  event leakage.
- Opus F10 is resolved in `PoolCapacityPlanner`: pool sizing now uses true
  `math.ceil(demanded)` so exact integer demand no longer over-allocates one
  connection slot.
- Opus F19 is resolved for `SignalFusion`: per-sensor and fusion-wide
  `gate_threshold` values must now be positive when set, with `None` preserved
  as the no-gating mode.
- Opus F20 is resolved for `SignalFusion`: per-sensor consecutive rejection
  counters are capped by `max_consecutive_rejections`, and saturated ticks are
  surfaced in the local trace state without minting a new event kind.
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
- Opus F17 is resolved in `SREControlStack`: stability monitoring now receives
  cumulative elapsed time rather than `_tick_index * dt`, so variable-duration
  ticks no longer distort the Lyapunov derivative timestamp.
- Opus F37 is resolved for recovery diagnostics: unrecovered windows are now
  represented as strict-JSON `null` values instead of non-standard `Infinity`
  in both generator-side and report-side diagnostics.
- Opus F42 is resolved for replay fixture test robustness: operator-action
  checks now require coverage and non-empty strings per expected event kind
  instead of hard-coding the exact action prose.
- Opus F39 is resolved in the evidence report: SHA-256 metadata shape checks now
  accept uppercase hexadecimal characters while byte-identity comparison remains
  exact.
- Opus F31 is resolved in `analysis.evidence_report`: JSONL parsing,
  Section 10 trace-shape checks, Section 12 fixture-shape checks, and event
  schema validation now collect multiple row-level errors in one report pass
  instead of stopping at the first bad row.
- Opus F32 is resolved in `PoolCapacityPlanner`: `rps_per_conn` is now a
  configurable dataclass field used consistently by sizing and shortfall
  calculations.
- Opus F41 is resolved in `analysis.run_all`: import or study execution
  failures are recorded in `analysis/artifacts/SUMMARY.txt`, later studies
  continue running, and the command exits nonzero after the summary is written.
- Opus v2.0 F50 is resolved in `PredictiveAutoscaler`: the continuous plant
  input matrix is scaled by `1/dt`, so ZOH produces a one-step `Bd` matching
  executor units (`u=1` means one replica per control step). The regression test
  checks plant/executor one-step agreement.
- Opus v2.0 F51 is resolved in `StabilityMonitor`: `dV/dt` now uses the recent
  pair rather than the oldest window anchor, preventing spike recovery from
  continuing to count stale violations.
- Opus v2.0 F52 is resolved in `CanaryScheduler`: warm-start from a nonzero
  share initialises baseline state without fitting a phantom slope from share 0.
- Opus v2.0 F53 is resolved in `SREControlStack`: a triggered stability guard
  clamps autoscaler control to `±1` for that tick and skips canary advancement.
- Opus v2.0 F54 is resolved in `SLOGuardrail`: non-finite proposals raise
  `AdapterInputError` before projection, preserving fault localisation.
- Opus v2.0 F55 is resolved in `SREControlStack`: autoscaler recoverable
  fallback now overwrites `last_trace` with a fallback sentinel and reason.
- Opus v2.0 F56 is resolved in `SignalFusion`: duplicate signal names within
  one tick are rejected before prediction, avoiding rejection-counter collision.
- Opus v2.0 F57 is resolved in `SREControlStack`: last-good allocation reuse now
  rejects non-finite cached shares.
- Opus v2.0 F58 is resolved in `PoolCapacityPlanner`: exact saturation emits a
  `pool_capacity_clipped` advisory with `clipped_slots=0` and zero shortfall.
- Opus v2.0 F59 is resolved in `TopologyState`: `ring_angle_rad` is wrapped to
  the documented `[-pi, pi]` interval with parameterized coverage.
- Opus v2.0 F60 is resolved in tests: the OU exact-discretization test now uses
  `scipy.linalg.expm` as an independent oracle.
- Opus v2.0 G1 is resolved in `scripts.quality_gate_counts`: the quality-gate
  updater now runs `analysis.evidence_manifest` before `analysis.evidence_report`
  when collecting the live pytest count, so reviewer command order is
  self-healing for the manifest byte-identity check.
- Opus v2.1 F61-F81 are resolved in the current workspace. The main closures are:
  refreshed browser evidence manifests and replay report; non-finite guards for
  `SignalFusion`, `SLOGuardrail.approve()/audit()`, and `WeightedLoadBalancer`;
  rejected Canary warm-start trust-region shrink behavior; strict JSON writers
  with `allow_nan=False`; repo-relative browser manifest artifact paths; proper
  `analysis.run_all(artifacts_dir=...)` forwarding; control-center share-state
  whitelisting and dynamic text escaping; loopback-only bind enforcement;
  browser/package/integration gates in `scripts.quality_gate_counts`; a read-only
  `python -m scripts.quality_gate_counts --check` mode; and manifest replay error
  messages that include manifest, viewport, DOM path, and regeneration command.

## Numerical Risks

| Risk | Concrete behavior | Impact |
|---|---|---|
| 当前无开放数值风险记录。 | v1.0 与 v2.0 已知数值 findings 已迁入 resolved ledger，并绑定回归测试。 | 新数值断言仍需保持 scenario-specific，不得升级为 production proof。 |

## Modeling Risks

| Risk | Concrete behavior | Impact |
|---|---|---|
| SRE analogy overreach | Convexification, MPC, and EKF are migrated abstractions, not proof that rocket controllers directly map to production systems. | Docs must avoid implying official SpaceX implementation or production equivalence. |
| Single-stack orchestration | `SREControlStack` still chains adapters in one process, but its stage inputs/outputs, direct event kinds, and runtime-stage routes are now exported as a non-production data contract. | Future work can split along the exported boundaries if this becomes more than a research stack. |
| Event-kind evolution | `adapter_exception` now carries stage-family, fault-family, and fallback-action fields, and the stack data contract binds stage event kinds plus observed trace events to the shared runtime registry. Future additions should keep this as a stable payload extension rather than minting new event kinds for every adapter failure. | Future review may need finer remediation playbooks, but the event payload is now routeable by adapter family and contract drift is report-checked. |
| Action magnitude contract | `SREControlStack.step()` treats `safe_action` as a guardrail direction vector whose L2 norm is scalar RPS demand; `zone_target` is the separate placement distribution. | Future work that changes `safe_action` semantics must update the stack contract, Section 10 evidence expectations, and allocator tests together instead of switching to component sums locally. |

## Suggested Next PR

Prefer one of these research-landing slices：

1. Add release-pipeline automation only if this repository starts publishing
   versioned artifacts.
2. Continue review-ledger hygiene when new packets are added, keeping old
   packets labeled as historical when their findings are already resolved.
