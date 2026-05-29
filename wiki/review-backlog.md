# Review Backlog

This page is the cross-session summary of the current review state. Source code,
tests, and generated analysis artifacts remain authoritative when they conflict
with older review packets.

## Current Verified Baseline

- Full test suite: `python -m pytest tests -q` passes with 605 tests in the
  current workspace.
- Analysis suite: `python -m analysis.run_all` completes all 12 studies and
  refreshes `analysis/artifacts/SUMMARY.txt`.
- The canonical current HTML entry is
  `docs/V2_Knowledge/knowledge-base.html`; `docs/knowledge-base.html` is a V1
  archive snapshot.
- Synthetic before/after evidence is scenario evidence only. Do not present it
  as production proof or as SpaceX internal implementation detail.

## Completed In Current Workspace

### PR-A: Refine Section 10 Failure-Trace Evidence

Status: implemented and verified.

Evidence:

- The scenario uses one continuous `SREControlStack` instance.
- `background_event_fraction` is bounded and currently reports `0.0`.
- `degraded_tick_fraction` is no longer saturated and is treated as a legacy
  coarse metric.
- `analysis/artifacts/s10_trace_full.jsonl` exists and its line count matches
  `event_count_total`.
- Each injected window has expected event-kind coverage.
- The `replica_bound_active` injection window now has full expected-kind
  coverage (`expected_kind_fraction = 1.0`) under a bounded-capacity demand surge
  forecast.

### PR-B: Add Stage-Specific Fallback Taxonomy

Status: implemented and verified.

Evidence:

- `ControlDomainError`, `RecoverableControlError`, and `AdapterInputError`
  separate control-domain failures from programmer errors.
- `SREControlStack.step()` catches recoverable control errors without swallowing
  programmer errors such as `AttributeError` or `TypeError`.
- `adapter_exception` events include machine-readable cause and fallback fields:
  `stage`, `exception_type`, `cause_type`, `adapter_family`, `fault_family`,
  `fallback_action`, `fallback_mode`, and `recoverable`.

### PR-C: Lock StabilityGuard Semantics

Status: implemented and verified.

Evidence:

- `StabilityMonitor.triggered` remains latched until explicit `reset()`.
- Docs avoid implying automatic recovery.
- Lyapunov red-line events are distinguishable from recoverable adapter
  exceptions.

### PR-D: Add Per-Sensor Innovation Gate Policy

Status: implemented and verified for the minimal P1 slice.

Evidence:

- `Signal.gate_threshold` supports per-sensor thresholds.
- `SignalFusion._resolve_threshold()` selects the sensor override or fusion
  default.
- Trace entries include `threshold_used` and `innovation_mahalanobis`.
- Tests cover mixed accept/reject behavior and rejected observations not
  contaminating the posterior.

### Allocator Fallback Semantics

Status: implemented and verified.

Evidence:

- `WeightedLoadBalancer` recoverable failure reuses last-good `alloc_shares`
  when the allocator signature remains valid.
- Bootstrap or no-valid-history cases fall back to zero shares.
- Topology-only changes are included in the allocator signature.

### EKF Joseph Covariance Hardening

Status: implemented and verified.

Evidence:

- `starship/ekf.py` uses Joseph form and covariance symmetrization.
- `starship.EKF` defaults `covariance_eigenvalue_floor` to `1e-12`, preventing
  repeated low-noise updates from silently collapsing the posterior covariance;
  callers can still pass `0.0` to opt out explicitly.
- `tests/test_ekf.py` covers covariance symmetry, PSD behavior, and gated no-op
  behavior, plus default-floor protection against posterior overconfidence.

### Docs / Schema Drift Control

Status: implemented and verified.

Evidence:

- `tests/test_event_schema.py` parses `docs/EVENT_SCHEMA.md` and
  `docs/RUNTIME_STATES.md` against the runtime registry/counterexamples.
- Current docs distinguish core adapter events from cross-cutting events.

### Catch/SRE Wrapper Boundary

Status: implemented and verified for feasible, total-overload, and
placement-infeasible synthetic slices.

Evidence:

- `sre_control.CatchLoadAdapter` wraps the bounded-LS allocation semantics in
  SRE vocabulary and tags traces with `sre_wrapper_for_catch_allocation`.
- The wrapper reuses existing `bounded_ls_residual` events rather than adding a
  new event kind or letting physical-layer `starship/` code import SRE schema.
- `analysis.s11_catch_sre_wrapper` compares a residual-hiding baseline against
  the wrapper across three regimes: feasible quiet solves, total-capacity
  overload, and placement-infeasible zone targets.
- Current Section 11 metrics: `capacity_violation_pct 66.67 -> 0`,
  `event_visible_fraction = 1.0`, and `reported_residual_mean = 42.68`.
- `tests/test_catch_adapter.py` covers JSON trace shape, feasible quiet solves,
  and residual visibility.
- `tests/test_synthetic_evidence_boundaries.py` asserts case coverage and
  separate visibility/quietness fractions for the three regimes.

### Replay-Style SRE Fixture

Status: implemented and verified for a synthetic replay fixture with
event-kind, error-budget stability, recovery, operator-action, and compound
incident-window coverage.

Evidence:

- `analysis/fixtures/sre_replay.jsonl` is a fixed 19-tick replay input stream
  with nominal rows plus expected `missing_sensor`, `unsafe_proposal_projected`,
  `replica_bound_active`, `bounded_ls_residual`, and `stability_violation`
  rows. Each expected-event row includes an `operator_action` annotation, and
  the compound `compound_telemetry_policy_capacity` incident includes a
  window-level operator action.
- `analysis.s12_sre_replay` runs the fixture through one continuous
  `SREControlStack` and labels the result `synthetic_replay_fixture`.
- Current Section 12 metrics: `expected_event_visible_fraction = 1.0`,
  `background_event_fraction = 0.0`, `stability_event_visible_fraction = 1.0`,
  `recovered_window_fraction = 1.0`, `max_recovery_ticks = 1`, and
  `operator_action_coverage = 1.0`, with `event_count_total = 11`.
- The replay now includes one 3-tick multi-signal incident window with
  `multi_signal_window_coverage = 1.0`,
  `multi_signal_window_recovered_fraction = 1.0`, and
  `max_multi_signal_recovery_ticks = 1`.
- `tests/test_synthetic_evidence_boundaries.py` asserts the replay label,
  tick count, expected event kinds, expected-kind visibility, and clean nominal
  background.
- It also lints live review docs for unqualified production-readiness, official
  SpaceX implementation, and production-proof wording while allowing explicit
  negated boundary statements.

### Cross-Study Event Evidence Manifest

Status: implemented and verified for Section 10/11/12 review artifacts, including
F13's explicit artifact-directory handoff.

Evidence:

- `analysis.evidence_manifest` exports
  `analysis/artifacts/event_evidence_manifest.json` as the stable index for
  event/replay/contract evidence.
- F13: `analysis.evidence_manifest.main()` no longer monkey-patches
  `_common.ARTIFACTS` or `s10_failure_trace.ARTIFACTS`; it passes
  `artifacts_dir` explicitly into Section 10/11 generators, and
  `analysis._common.save_fig()` accepts an explicit artifact directory.
- `tests/test_evidence_manifest.py::test_event_evidence_manifest_does_not_patch_artifact_globals`
  stubs the study runners and asserts those module-level artifact paths remain
  unchanged while the manifest is generated.
- The manifest references portable repo-relative paths for Section 10
  full/sample JSONL traces, Section 11 wrapper diagnostics, and Section 12
  replay trace/diagnostics artifacts.
- Each manifest entry carries `artifact_metadata` byte-identity fields keyed to
  the artifact paths, with SHA-256 digests and byte size values for reviewer
  tamper/drift checks.
- `analysis/artifacts/s11_catch_sre_wrapper_diagnostics.json` records the
  feasible, total-overload, and placement-infeasible coverage fractions.
- `analysis/artifacts/s12_replay_trace.jsonl` records one replay row per input
  tick, and `analysis/artifacts/s12_replay_diagnostics.json` records the replay
  label, event counts, recovery metrics, and compound incident coverage.
- `analysis.evidence_report` reads the manifest, prints a compact reviewer
  summary, and fails if any referenced artifact is missing or internally
  inconsistent with manifest counts. It also parses JSON/JSONL evidence files
  so malformed machine-readable artifacts do not pass on line count alone, and
  validates runtime event payloads against `sre_control.events.validate_event`.
  It also rejects byte-identity mismatches when an artifact's actual SHA-256 or
  size no longer matches `artifact_metadata`.
- The manifest also references `sre_stack_data_contract.json`, and the report
  rejects contract payloads that claim production status or drift from the
  expected research stack stage ordering.
- `scripts.quality_gate_counts` now treats `analysis.evidence_manifest` and
  `analysis.evidence_report` as required current quality-gate commands, so the
  count updater fails if either drops out of the PR requirements or V2 HTML
  gate list.
- `tests/test_evidence_manifest.py` asserts the manifest shape, relative paths,
  Section 10/11/12 metrics, S12 trace line count, sync with
  `docs/EVENT_EVIDENCE_MANIFEST.md`, and report behavior for present/missing
  artifacts, malformed metadata, and stale artifact byte identity.

### SRE Stack Data Contract

Status: implemented and verified for current research stack boundaries.

Evidence:

- `sre_control.stack_data_contract()` exports `evidence_scope =
  research_stack_data_contract`, `production_claim = false`, the current
  `single_process_research_loop` model, and ordered stage contracts for
  observe, stability, plan, guard, allocate, and execute.
- Each stage contract lists the direct runtime `event_kinds` it may emit, and
  `event_stage_routes` maps runtime event `stage` prefixes back to those
  logical stages. `analysis.evidence_report` rejects stack-contract artifacts
  with event kinds outside the shared runtime registry, generated trace events
  that are not allowed by the routed contract stage, `adapter_exception`
  payloads not marked `recoverable=true`, payloads whose `adapter_family` does
  not match that stage, payloads whose exception type drifts from the documented `cause_type` mapping
  (`AdapterInputError -> adapter_input`, `RecoverableControlError -> control_domain`),
  payloads whose `fault_family` drifts from the documented `cause_type`,
  fallback actions/modes not declared for that stage, or fallback action/mode
  pairs that drift from the stage's contract map.
- `docs/STACK_DATA_CONTRACT.md` documents the contract shape and explicitly
  says it is research metadata, not a production distributed-control-plane
  contract.
- `tests/test_contracts.py` checks JSON serializability, stage ordering,
  representative inputs/outputs, event-kind registry membership, runtime-stage
  routing, and split-ready boundary names.

### Opus v1.0 P0/P1 Remediation

Status: implemented and verified for the blocking review slice.

Evidence:

- F02: `WeightedLoadBalancer.allocate()` wraps bounded-LS solver exceptions and
  unsuccessful solver results as `RecoverableControlError`, so the stack can use
  its validated allocator fallback path instead of crashing a tick.
- F03: `starship.EKF.update()` treats singular innovation covariance as a gated
  no-op and leaves state/covariance unchanged instead of letting the second
  linear solve raise.
- F01: `FastTrafficSwitcher.plan()` scales acceleration by the enlarged
  `safety_margin` duration, preserving the terminal share while reducing peak
  rate.
- F04: `adapter_exception.adapter_family` is derived from
  `stack_data_contract().event_stage_routes`, making runtime events and the
  exported stack contract share one routing source.
- F05: `safe_action` remains a guardrail direction vector whose L2 norm is the
  scalar RPS demand; `zone_target` remains the placement distribution contract.
  This is now documented in code/tests and the derivation notes.
- F11/F12: `validate_event()` enforces exact per-kind field sets for all 11
  runtime event kinds and rejects unknown extras.
- Fresh focused verification for this slice:
  `python -m pytest tests/test_sre_control.py tests/test_ekf.py tests/test_contracts.py tests/test_event_schema.py tests/test_failure_trace.py tests/test_evidence_manifest.py -q`,
  `python -m analysis.evidence_manifest`, and
  `python -m analysis.evidence_report`.

### Opus v1.0 P2 Evidence-Validator Remediation

Status: implemented and verified for F06, F09, F14, F15, and F23.

Evidence:

- F06: `analysis.s10_failure_trace._run_scenario()` now feeds back the
  stack-returned `replicas_next` directly instead of applying a hidden
  `max(..., 10)` scenario floor. The only remaining `10` is the named
  `INITIAL_REPLICAS` initial condition.
- The Section 10 scenario keeps fault-window isolation by explicitly flooring
  the post-capacity-window forecast at nominal load until the next injection
  window, preserving `background_event_fraction = 0.0` without overriding the
  autoscaler's replica output.
- `tests/test_failure_trace.py::test_s10_replicas_trace_uses_stack_output_without_hidden_floor`
  covers the former mismatch by forcing a fake stack output below 10 and
  asserting the returned replica trace records that output.
- F09: `analysis.s10_failure_trace._derive_metrics()` now uses the same
  empty-set semantics as `analysis.evidence_report`: no injected ticks means
  `event_visible_fraction = 1.0` by vacuous truth, while no background ticks
  means `background_event_fraction = 0.0` because there is no leakage.
- Empty per-window Section 10 coverage also defaults both visibility fractions
  to `1.0`, so a configured but tick-empty window does not report a false
  coverage failure.
- `tests/test_failure_trace.py::test_s10_empty_injection_set_uses_vacuous_visibility`
  covers the former mismatch by clearing `INJECTION_WINDOWS` and asserting
  `true_degraded_fraction = 0.0`, `event_visible_fraction = 1.0`,
  `background_event_fraction = 0.0`, and an empty `injected_window_coverage`.
- F14: `analysis.s10_failure_trace` writes both `s10_trace_full.jsonl` and
  `s10_trace_sample.jsonl` with `json.dumps(..., sort_keys=True)`, matching the
  manifest strategy for byte-stable generated evidence.
- `tests/test_failure_trace.py::test_s10_jsonl_artifacts_use_sorted_keys`
  parses the first JSONL row with `object_pairs_hook` and asserts the serialized
  key order is sorted.
- F15: `scripts.quality_gate_counts` now keeps pytest-count replacement targets
  in the `QUALITY_GATE_TARGETS` table, including path, regex, replacement
  template, and label. Replacement failures include the target path, while the
  command-presence guard still runs before reading all target docs.
- `tests/test_quality_gate_counts.py::test_quality_gate_targets_are_data_driven_with_unique_labels`
  covers the target table, and
  `test_update_quality_gate_docs_does_not_partially_write_on_replacement_failure`
  asserts missing replacement errors include the affected file path.
- F23: `analysis.evidence_report._s10_trace_shape_errors()` now uses a
  tick-scaled tolerance when comparing `t_seconds` to `tick * DT`, so future
  non-binary-exact `DT` values are not rejected for harmless floating-point
  accumulation drift.
- `tests/test_evidence_manifest.py::test_s10_trace_shape_allows_float_accumulation_drift`
  covers the accepted drift case, while
  `test_event_evidence_report_rejects_s10_trace_time_mismatch` keeps large
  trace-time mismatches red.
- Fresh focused verification for this slice:
  `python -m pytest tests/test_failure_trace.py -q`,
  `python -m pytest tests/test_failure_trace.py::test_s10_empty_injection_set_uses_vacuous_visibility tests/test_failure_trace.py::test_s10_each_injected_window_has_kind_coverage tests/test_failure_trace.py::test_s10_background_event_fraction_is_bounded tests/test_evidence_manifest.py::test_s10_trace_shape_allows_float_accumulation_drift -q`,
  `python -m pytest tests/test_failure_trace.py::test_s10_jsonl_artifacts_use_sorted_keys tests/test_failure_trace.py::test_s10_full_trace_jsonl_contains_all_events -q`,
  `python -m pytest tests/test_evidence_manifest.py::test_s10_trace_shape_allows_float_accumulation_drift tests/test_evidence_manifest.py::test_event_evidence_report_rejects_s10_trace_time_mismatch -q`,
  `python -m pytest tests/test_quality_gate_counts.py -q`,
  `python -m analysis.s10_failure_trace`, `python -m analysis.evidence_manifest`,
  and `python -m analysis.evidence_report`.

### Opus v1.0 P2 Signal-Fusion Numerics

Status: implemented and verified for F07, F19, and F20.

Evidence:

- F07: `SignalFusion` now uses exact OU discretization for both state prediction
  and the EKF Jacobian: `x_ref + exp(-theta * dt) * (x - x_ref)` and
  `F = exp(-theta * dt) * I`. This avoids Euler-step sign reversal when
  `theta * dt >= 1`.
- `tests/test_sre_control.py::test_signal_fusion_ou_prediction_uses_stable_exact_discretization`
  covers the former counterexample (`theta=0.5`, `dt=5.0`) and asserts the
  predicted state remains positive with exponential decay.
- `docs/SPECIAL_SOLUTIONS_DERIVATIONS.md` now shows the same exact OU
  discretization instead of the stale Euler snippet.
- F19: `Signal` and `SignalFusion` now reject non-positive `gate_threshold`
  values at construction time while preserving `None` as the explicit
  no-gating mode.
- `tests/test_sre_control.py::test_signal_rejects_nonpositive_gate_threshold`
  and `test_signal_fusion_rejects_nonpositive_default_gate_threshold` cover
  `0.0` and negative thresholds for both entry points.
- F20: `SignalFusion.max_consecutive_rejections` now caps per-sensor rejection
  counters, so a permanently gated sensor cannot grow unbounded trace integers.
  Saturated ticks add `rejection_counter_saturated` to the local states while
  preserving the existing `outlier_rejected` event kind.
- `tests/test_sre_control.py::test_signal_fusion_consecutive_rejections_are_capped`
  covers repeated gated observations beyond the cap, and
  `test_signal_fusion_rejects_invalid_rejection_counter_cap` rejects invalid
  cap values.
- Fresh focused verification:
  `python -m pytest tests/test_sre_control.py::test_signal_fusion_ou_prediction_uses_stable_exact_discretization tests/test_sre_control.py::test_signal_fusion_converges_to_truth tests/test_sre_control.py::test_signal_fusion_gates_outlier_when_threshold_is_set -q`,
  `python -m pytest tests/test_sre_control.py::test_signal_rejects_nonpositive_gate_threshold tests/test_sre_control.py::test_signal_fusion_rejects_nonpositive_default_gate_threshold tests/test_sre_control.py::test_signal_fusion_inherits_fusion_default_when_signal_has_no_override -q`,
  `python -m pytest tests/test_sre_control.py::test_signal_fusion_consecutive_rejections_are_capped tests/test_sre_control.py::test_signal_fusion_rejects_invalid_rejection_counter_cap tests/test_sre_control.py::test_signal_fusion_consecutive_rejections_reset_on_acceptance -q`,
  plus S10/manifest evidence regeneration and report validation.

### Opus v1.0 P2 Canary Rejected-Step Learning

Status: implemented and verified for F08.

Evidence:

- F08: `CanaryScheduler.observe()` now refits the local error-rate slope after
  any nonzero attempted rollout step, including rejected trials. The rollout can
  still freeze on SLO burn, but the SCP model no longer stays at `_b_est=0`
  through repeated rejected observations.
- Rejected-step traces include `refit_rejected` in `local_states`, making this
  learning path visible without changing the `rollout_rejected` event kind.
- `tests/test_sre_control.py::test_canary_rejected_step_still_refits_slope_from_observation`
  covers the former reproduction path: `0.0 -> 0.05` with `observed_error_rate
  = 0.03` now produces `_b_est = 0.6`, records `_last_share = 0.05`, and keeps
  `accepted=False`.
- Fresh focused verification:
  `python -m pytest tests/test_sre_control.py::test_canary_rejected_step_still_refits_slope_from_observation tests/test_sre_control.py::test_canary_shrinks_trust_region_on_slo_burn tests/test_sre_control.py::test_canary_warm_start_does_not_poison_slope tests/test_sre_control.py::test_canary_grows_trust_region_when_safe -q`.

### Opus v1.0 P2 Pool Capacity Ceiling

Status: implemented and verified for F10.

Evidence:

- F10: `PoolCapacityPlanner.plan()` now uses `math.ceil(demanded)` for the
  scalar lossless-convex relaxation, so exact integer demand does not allocate
  one unnecessary extra connection.
- `tests/test_sre_control.py::test_pool_planner_uses_true_ceiling_at_integer_demand`
  covers integer and fractional boundaries: `200.0 -> 2`, `200.1 -> 3`, and
  `300.0 -> 3` when `rps_per_conn=100`.
- Fresh focused verification:
  `python -m pytest tests/test_sre_control.py::test_pool_planner_uses_true_ceiling_at_integer_demand tests/test_sre_control.py::test_pool_planner_respects_keep_alive_floor tests/test_sre_control.py::test_pool_planner_marks_capacity_clip_event -q`.

### Opus v1.0 P2 Allocator Input Validation

Status: implemented and verified for F18.

Evidence:

- F18: `WeightedLoadBalancer.__post_init__()` now rejects empty instance lists
  and mismatched `zone_vector` dimensions at construction time, before bounded
  least-squares matrix construction.
- The constructor normalizes each `zone_vector` to a float numpy array so the
  allocator uses one internal representation.
- `tests/test_sre_control.py::test_balancer_rejects_mismatched_zone_vector_dimensions`
  covers the previous delayed-failure path with a clear `ValueError`.
- Fresh focused verification:
  `python -m pytest tests/test_sre_control.py::test_balancer_rejects_mismatched_zone_vector_dimensions tests/test_sre_control.py::test_balancer_matches_demand_without_saturating tests/test_sre_control.py::test_balancer_quantifies_residual_so_safe_does_not_mean_sufficient -q`.

### Opus v1.0 P2 Traffic-Switcher Input Validation

Status: implemented and verified for F33.

Evidence:

- F33: `FastTrafficSwitcher.__post_init__()` now rejects non-positive
  `rate_max` values before `plan()` reaches the minimum-time square-root
  calculation.
- `tests/test_sre_control.py::test_switcher_rejects_nonpositive_rate_max`
  covers both zero and negative `rate_max` inputs with a clear `ValueError`.
- Fresh focused verification:
  `python -m pytest tests/test_sre_control.py::test_switcher_rejects_nonpositive_rate_max tests/test_sre_control.py::test_switcher_hits_target_with_zero_residual_rate tests/test_sre_control.py::test_switcher_safety_margin_preserves_terminal_share tests/test_sre_control.py::test_switcher_marks_deadline_exceeded_event -q`.

### Opus v1.0 P2 Section 11 Test Robustness

Status: implemented and verified for F21.

Evidence:

- F21: `tests/test_synthetic_evidence_boundaries.py::test_catch_sre_wrapper_covers_feasible_overload_and_placement_cases`
  now runs Section 11 with `n_cases=9` and asserts that feasible,
  total-overload, and placement-infeasible regimes are present, equal-sized,
  and non-empty instead of hard-coding the default 40 cases per regime.
- The test still preserves the behavioral checks that feasible cases are quiet
  and both infeasible regimes emit visible bounded-residual evidence.
- Fresh focused verification:
  `python -m pytest tests/test_synthetic_evidence_boundaries.py::test_catch_sre_wrapper_covers_feasible_overload_and_placement_cases -q`.

### Opus v1.0 P2 Evidence-Boundary Lint Window

Status: implemented and verified for F16.

Evidence:

- F16: `scripts.evidence_boundary_lint._is_negated_boundary_wording()` now
  includes a short suffix window after the matched overclaim phrase, so boundary
  wording such as `production-ready, but not ...` is recognized consistently
  with prefix negations.
- `tests/test_synthetic_evidence_boundaries.py::test_evidence_boundary_lint_allows_immediate_suffix_negation`
  covers the previously missed suffix-negation path while the existing unsafe
  production-claim test still catches unqualified wording.
- Fresh focused verification:
  `python -m pytest tests/test_synthetic_evidence_boundaries.py::test_evidence_boundary_lint_allows_immediate_suffix_negation tests/test_synthetic_evidence_boundaries.py::test_evidence_boundary_lint_flags_unsafe_production_claims -q`.

### Opus v1.0 P2 Variable-DT Stability Time

Status: implemented and verified for F17.

Evidence:

- F17: `SREControlStack.step()` now maintains explicit cumulative elapsed time
  for the stability monitor instead of deriving time as `_tick_index * dt`.
  Variable-duration ticks therefore feed the Lyapunov derivative with the true
  elapsed timestamp.
- `_tick_index` remains a tick counter, while `_elapsed_time` is advanced by the
  actual `dt` after each trace entry is appended.
- `tests/test_contracts.py::test_stability_monitor_uses_cumulative_elapsed_time_for_variable_dt`
  covers the former counterexample: two stack ticks with `dt = [2.0, 5.0]`
  pass stability timestamps `[0.0, 2.0]`, not `[0.0, 5.0]`.
- Fresh focused verification:
  `python -m pytest tests/test_contracts.py::test_stability_monitor_uses_cumulative_elapsed_time_for_variable_dt tests/test_contracts.py::test_stability_guard_triggers_degraded_plan_on_sustained_violation tests/test_contracts.py::test_stack_clamps_autoscaler_when_stability_triggered tests/test_contracts.py::test_stability_guard_reports_sustained_trigger_without_new_event -q`.

### Opus v1.0 P3 Strict JSON Recovery Diagnostics

Status: implemented and verified for F37.

Evidence:

- F37: `analysis.s12_sre_replay` and `analysis.evidence_report` now represent
  unrecovered recovery windows as JSON `null` (`None`) in public diagnostics
  instead of emitting `Infinity`.
- The same strict-JSON contract is applied to both `max_recovery_ticks` and
  `max_multi_signal_recovery_ticks`.
- Tests cover generator-side and report-side unrecovered windows with
  `json.dumps(..., allow_nan=False)`.
- Fresh focused verification:
  `python -m pytest tests/test_synthetic_evidence_boundaries.py::test_sre_replay_unrecovered_window_uses_strict_json_null tests/test_synthetic_evidence_boundaries.py::test_sre_replay_unrecovered_multi_signal_window_uses_strict_json_null tests/test_evidence_manifest.py::test_evidence_report_unrecovered_window_uses_strict_json_null tests/test_evidence_manifest.py::test_evidence_report_unrecovered_multi_signal_window_uses_strict_json_null -q`.

### Opus v1.0 P3 Replay Operator-Action Test Robustness

Status: implemented and verified for F42.

Evidence:

- F42: `tests/test_synthetic_evidence_boundaries.py::test_sre_replay_fixture_is_labeled_and_covers_expected_event_kinds`
  no longer pins the exact operator-action prose for the five expected replay
  event kinds.
- The test now verifies the stable contract instead: all five expected kinds
  have at least one non-empty operator-action string, while the existing replay
  visibility, recovery, and observed-kind assertions remain unchanged.
- Fresh focused verification:
  `python -m pytest tests/test_synthetic_evidence_boundaries.py::test_sre_replay_operator_actions_are_checked_by_coverage_not_literal_text tests/test_synthetic_evidence_boundaries.py::test_sre_replay_fixture_is_labeled_and_covers_expected_event_kinds -q`.

### Opus v1.0 P3 SHA-256 Shape Tolerance

Status: implemented and verified for F39.

Evidence:

- F39: `analysis.evidence_report._is_sha256()` now accepts uppercase
  hexadecimal characters in manual manifest metadata shape checks.
- Byte-identity comparison remains strict because actual metadata still comes
  from `hashlib.sha256(...).hexdigest()` and stale metadata is compared by exact
  digest string later in the report.
- `tests/test_evidence_manifest.py::test_evidence_report_accepts_uppercase_sha256_shape`
  covers uppercase `A` and `F` digests.
- Fresh focused verification:
  `python -m pytest tests/test_evidence_manifest.py::test_evidence_report_accepts_uppercase_sha256_shape -q`.

### Opus v1.0 P3 Pool Capacity Unit Parameter

Status: implemented and verified for F32.

Evidence:

- F32: `PoolCapacityPlanner` now exposes `rps_per_conn` as a dataclass field
  instead of hard-coding `100.0` inside `plan()`.
- Pool sizing and capacity-shortfall calculations both use the same configured
  field, so custom connection throughput stays consistent across the planner.
- `tests/test_sre_control.py::test_pool_planner_uses_configured_rps_per_connection`
  covers a `50.0` RPS/connection planner while the existing integer-ceiling and
  clipping tests preserve the default `100.0` behavior.
- Fresh focused verification:
  `python -m pytest tests/test_sre_control.py::test_pool_planner_uses_configured_rps_per_connection tests/test_sre_control.py::test_pool_planner_uses_true_ceiling_at_integer_demand tests/test_sre_control.py::test_pool_planner_marks_capacity_clip_event -q`.

### Opus v1.0 P3 Evidence Report Collect-All Errors

Status: implemented and verified for F31.

Evidence:

- F31: `analysis.evidence_report` now keeps scanning after row-level failures
  in JSONL parsing, Section 10 trace-shape validation, Section 12 fixture-shape
  validation, and S10/S12 runtime-event schema validation.
- This preserves the existing error strings while returning multiple actionable
  failures from one report run.
- `tests/test_evidence_manifest.py` covers collect-all behavior for malformed
  JSONL rows, invalid S10 trace rows, invalid S12 fixture rows, and invalid S10
  event-schema rows.
- Fresh focused verification:
  `python -m pytest tests/test_evidence_manifest.py -q`.

### Opus v1.0 P3 Analysis Runner Failure Reporting

Status: implemented and verified for F41.

Evidence:

- F41: `analysis.run_all.main()` now records import and study execution
  failures in `SUMMARY.txt`, continues running later studies, and exits with
  `SystemExit(1)` after writing the summary if any study failed.
- `main()` accepts optional `studies` and `artifacts_dir` parameters so tests
  can exercise failure handling without mutating the canonical artifacts.
- `tests/test_analysis_run_all.py::test_run_all_records_import_failures_and_continues`
  covers the former first-failure stop by injecting an import failure between
  two successful studies and asserting both successful studies still run.
- Fresh focused verification:
  `python -m pytest tests/test_analysis_run_all.py -q`.

### Opus v2.1 Continuation Review F61-F81

Status: implemented and verified in the current workspace.

Evidence:

- Browser evidence manifests were regenerated, report replay is a required gate,
  and manifest records now use repo-relative paths.
- `SignalFusion`, `SLOGuardrail.approve()/audit()`, and `WeightedLoadBalancer`
  reject non-finite inputs at adapter boundaries.
- Rejected Canary warm-start attempts shrink the trust region instead of
  expanding while reporting a shrink event.
- Evidence JSON/JSONL writers use strict JSON (`allow_nan=False`).
- `analysis.run_all(artifacts_dir=...)` forwards artifact directories to studies
  that support the parameter.
- Control-center share-state parsing is whitelisted, dynamic text rendering is
  escaped, and control-center servers reject non-loopback bind hosts unless the
  caller explicitly opts in.
- `scripts.quality_gate_counts` executes browser evidence, package smoke,
  integration audit, and demo gates; it also has a read-only `--check` mode.
- Browser manifest replay failures now include manifest, viewport, DOM artifact
  path, and the regeneration command.

### Opus Handoff / Gate Hardening

Status: implemented and verified for the current handoff slice.

Evidence:

- `docs/opus-review/HANDOFF.md` is the current Opus first-read entry and now
  lists the post-v2.1 hardening commits, review focus, expected replay outputs,
  and evidence assets without pinning HEAD to a single commit SHA.
- `docs/opus-review/HANDOFF.md` now puts `docs/codex-review/OPEN_RISKS.md` and
  `wiki/review-backlog.md` before `docs/opus-review/OPUS_REVIEW_PACKET.md` and
  older Claude/Opus packets in its reviewer flow, and the order is covered by a
  regression test so historical packets do not become the first authority again.
- `wiki/README.md` now lists `docs/codex-review/OPEN_RISKS.md` and
  `wiki/review-backlog.md` before historical Claude/Opus review packets in the
  current recommended entries table, with a regression test covering that wiki
  entry order.
- `scripts.review_authority_lint` centralizes the current-ledger-before-history
  ordering rule for Opus handoff and wiki entrypoints, so future review packet
  additions can extend one lint surface instead of duplicating one-off string
  assertions.
- `scripts.evidence_boundary_lint.PUBLIC_EVIDENCE_BOUNDARY_DOCS` includes
  `docs/opus-review/README.md` and `docs/opus-review/HANDOFF.md`, so the Opus
  first-read surface is linted for unqualified production-readiness, production
  proof, and SpaceX-internals claims.
- The evidence-boundary lint now also recognizes Chinese review-prose
  overclaims around synthetic evidence, production readiness, and SpaceX
  implementation provenance, while preserving explicit Chinese boundary
  negations in review statements.
- `scripts.quality_gate_counts.QUALITY_GATE_TARGETS` includes
  `docs/opus-review/HANDOFF.md`, so its `quality gate pytest count` line is
  updated with the same real pytest count as PR, V2 HTML, Codex review, Opus
  packet, and wiki ledgers.
- Section 11 analysis tests write wrapper plots to pytest `tmp_path` and assert
  the canonical `analysis/artifacts/s11_catch_sre_wrapper.png` hash is not
  changed, so a full pytest run no longer dirties committed evidence art.
- `scripts.quality_gate_counts` now gives full-suite pytest and collect-only
  parity checks a 300 s timeout budget. The current local full suite takes about
  174 s, so Opus has practical headroom for review-machine jitter.
- Fresh verification for this slice:
  `python -u -m scripts.quality_gate_counts` reports
  `quality gate pytest count: 477`; `python -m pytest tests -q` passes and
  leaves the worktree clean; `python -m scripts.quality_gate_counts --check
  --skip-expensive` reports `quality gate docs check passed`; and
  `python -m analysis.evidence_report` reports
  `artifact_check ok studies=3 files=8`.

## Active Research Landing Candidates

Opus v2.0 review on 2026-05-26 added F50-F60 and G1. Opus v2.1 continuation
review on 2026-05-28 added F61-F81. These are resolved in the current workspace
with regression tests, evidence gates, or current-doc boundary updates. The full
review packets are `claude-review/docs/v2026-05-26/` and
`claude-review/docs/v2026-05-28/`; the live risk register is
`docs/codex-review/OPEN_RISKS.md`.

Priority order for the next engineering pass:

1. Continue review-ledger hygiene when new packets are added, keeping old
   packets labeled as historical when their findings are already resolved.

## Final Gate For A New Implementation Pass

Run the following before claiming a new pass is complete:

```bash
python -m pytest tests -q
python -m analysis.s10_failure_trace
python -m analysis.run_all
python -m analysis.evidence_manifest
python -m analysis.evidence_report
python -m scripts.control_center_browser_smoke --report-manifests --report-json analysis/artifacts/control-center-browser-evidence-report.json
python -m scripts.package_smoke
python -m scripts.control_center_integration_audit
python -m scripts.review_authority_lint
python -m examples.demo_sre_loop
python -m examples.demo_powered_descent
python -m examples.demo_catch_phase
python -m scripts.quality_gate_counts --check --skip-expensive
```

Required evidence:

- `analysis/artifacts/SUMMARY.txt` contains Section 10 metrics:
  `event_visible_fraction`, `true_degraded_fraction`,
  `background_event_fraction`, and `injected_window_coverage`.
- `analysis/artifacts/s10_trace_full.jsonl` line count equals
  `event_count_total`.
- `analysis/artifacts/event_evidence_manifest.json` references Section 10/11/12
  evidence artifacts and the SRE stack data-contract artifact with
  repo-relative paths.
- Tests continue to cover continuous stack history, programmer-error
  propagation, StabilityMonitor latch semantics, per-sensor gate threshold
  tracing, docs/schema sync, package smoke, and release hygiene.
