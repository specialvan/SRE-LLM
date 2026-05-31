# Claude Refined Spec for Next Codex Pass

> Current status (2026-05-24): this file is historical execution rationale; it
> is not the live backlog. PR-A through PR-D, allocator fallback semantics, EKF Joseph
> hardening, docs/schema sync, package smoke, control-center exposure policy,
> and release hygiene are implemented and covered by tests. Use
> `docs/opus-review/HANDOFF.md`, `wiki/review-backlog.md`,
> `docs/codex-review/OPEN_RISKS.md`, and `docs/codex-review/QUALITY_GATES.md`
> for current completed/open status, next-work candidates, and command
> authority. Use the handoff's `Git Review Scope Snapshot`, then refresh
> `git status --short --branch --untracked-files=all` and
> `git ls-files --others --exclude-standard` so dirty/untracked files remain in
> review scope.

> Scope: refine the `spacex-session` Codex review packet into executable engineering work. This spec is based on Claude's follow-up review of `docs/codex-review/*`, current code, and current tests.

> Historical status update (2026-05-14): PR-A, PR-B, PR-C, and the minimal
> PR-D slice were implemented in that workspace and reflected in tests/docs.
> Later passes also implemented allocator fallback semantics, EKF Joseph
> hardening, docs drift control, package smoke, and release hygiene. Historical
> sections below remain as rationale and acceptance history.

## Current verdict and source of truth

Quality gates pass, and the remaining P1 semantic risks are now narrower than this document's first draft.

This file is historical execution rationale for the pass that implemented the
listed PR-A through PR-D work. Earlier review packets remain evidence and
rationale; where priority wording differs, current source, tests,
`docs/opus-review/HANDOFF.md`, `wiki/review-backlog.md`,
`docs/codex-review/OPEN_RISKS.md`, and
`docs/codex-review/QUALITY_GATES.md` control implementation order and command
authority.

Do not describe the current branch as "production-ready control stack". PR-A through PR-D are materially complete in the current workspace. The follow-on hardening items below remain open.

## Non-goals

- Do not claim or imply any official SpaceX internal implementation detail.
- Do not convert synthetic before/after studies into production guarantees.
- Do not broaden the control stack beyond the current SRE abstraction work.
- Do not add large new frameworks or external services for this pass.

## PR-A: Refine §10 failure-trace evidence

Priority: P1

### Problem

`analysis/s10_failure_trace.py` currently allows every tick to emit `bounded_ls_residual`. This makes `degraded_tick_fraction = 100%` a saturated background signal rather than proof that injected failure windows are observable.

Key anchors:

- `analysis/s10_failure_trace.py:144` builds the nominal `nn_proposal`.
- `analysis/s10_failure_trace.py:156` passes `zone_target` in a different effective scale than allocator demand.
- `analysis/s10_failure_trace.py:171` derives `degraded_tick_fraction` only from whether a tick has any event.
- `tests/test_failure_trace.py:52` only asserts non-zero metrics.

### Required changes

1. Use one continuous `SREControlStack` instance for the whole scenario.
   - Inject faults by changing inputs or stage constraints inside windows, then restore them.
   - Do not switch between separate stack instances to manufacture event kinds.
   - Preserve EKF, autoscaler, stability, and trace history across all ticks.
2. Remove the always-on allocator residual from the nominal path.
   - Align `zone_target` with the same effective demand used by `WeightedLoadBalancer`.
   - If allocator residual is intentionally part of the study, make it an explicit injected window with its own label and coverage expectation.
3. Replace the overloaded metric set with explicit metrics:
   - `event_visible_fraction`: fraction of injected degraded ticks that emitted at least one event.
   - `true_degraded_fraction`: fraction of ticks that are part of a configured injection window.
   - `background_event_fraction`: fraction of non-injection ticks with any event.
   - `injected_window_coverage`: per-window event coverage keyed by window name.
4. Keep `degraded_tick_fraction` only if needed for backwards compatibility, but document it as a coarse legacy metric and do not use it as the primary proof.
5. Export full evidence:
   - `analysis/artifacts/s10_trace_full.jsonl`: every emitted event.
   - `analysis/artifacts/s10_trace_sample.jsonl`: small reviewer-friendly sample.
6. Update plots and docs to refer to the new metrics.

### Required tests

Add or refine tests in `tests/test_failure_trace.py`:

- `test_s10_uses_one_continuous_stack_instance`
  - Assert the scenario does not reset or swap `SREControlStack` instances across injection windows.
- `test_s10_background_event_fraction_is_bounded`
  - Assert `background_event_fraction < 0.20`, unless a stricter threshold is practical.
- `test_s10_degraded_tick_fraction_not_saturated`
  - If the legacy metric remains, assert `0.0 < degraded_tick_fraction < 100.0`.
- `test_s10_full_trace_jsonl_contains_all_events`
  - Run `s10.main()` and assert full JSONL exists and line count equals `event_count_total`.
- `test_s10_each_injected_window_has_kind_coverage`
  - Assert each injected window has the expected event kind and meaningful coverage.

### Acceptance commands

```bash
python -m pytest tests/test_failure_trace.py -q
python -m analysis.s10_failure_trace
python -m analysis.run_all
```

### Acceptance evidence

- `analysis/artifacts/SUMMARY.txt` reports the new metrics.
- `analysis/artifacts/s10_trace_full.jsonl` exists.
- Scenario evidence comes from one continuous stack history; injection windows do not reset EKF/autoscaler/trace state.
- `background_event_fraction` is bounded and does not saturate the scenario.
- The summary no longer uses `degraded_tick_fraction = 100%` as evidence of lifecycle observability.

## PR-B: Add stage-specific fallback taxonomy

Priority: P1

### Problem

`SREControlStack.step()` catches broad `Exception` across stages. This keeps traces alive, but it also turns programmer bugs into `stability_violation` events and continues execution.

Key anchors:

- `sre_control/stack.py:119`
- `sre_control/stack.py:146`
- `sre_control/stack.py:162`
- `sre_control/stack.py:199`
- `sre_control/stack.py:226`
- `tests/test_contracts.py:180`

### Required changes

1. Introduce an explicit exception taxonomy.
   - Recoverable control-domain failures should be catchable.
   - Programmer errors should fail fast.
2. Suggested types:
   - `ControlDomainError`
   - `RecoverableControlError`
   - `AdapterInputError`
3. Replace broad catch-all behavior with stage-specific policies.
4. Preserve root cause in machine-readable event fields:
   - `stage`
   - `exception_type`
   - `cause_type`
   - `recoverable`
5. Split event semantics if practical:
   - Prefer `adapter_exception` for recoverable adapter failures.
   - Prefer `lyapunov_violation` for Lyapunov red-line events.
   - If `stability_violation` remains, it must include `cause_type` to disambiguate.
6. Ensure fallback code cannot double-fault by reusing invalid inputs without validation.

### Required tests

Add tests around `SREControlStack.step()`:

- recoverable adapter error completes the tick and emits a recoverable event.
- programmer error, such as `AttributeError` or `TypeError`, is not swallowed.
- guard fallback cannot double-fault on malformed `nn_proposal`, or malformed input is rejected before fallback.
- event payload includes machine-readable root-cause fields.

### Acceptance commands

```bash
python -m pytest tests/test_contracts.py tests/test_event_schema.py -q
python -m pytest tests -q
```

### Acceptance evidence

- Tests distinguish recoverable control-domain exceptions from programmer errors.
- Event schema documents and validates the new cause fields or split event kinds.
- `RUNTIME_STATES.md` explains the exception taxonomy.

## PR-C: Lock StabilityGuard semantics

Priority: P1

This PR resolves the earlier P1 stability-recovery ambiguity by making an explicit product/engineering decision: this pass uses manual-reset latch semantics. It is not a deferral of the ambiguity; it closes it by contract and test. A future auto-recovery mode may be proposed separately.

### Problem

`StabilityMonitor` currently latches once triggered and only clears via `reset()`. This may be correct, but docs and tests must make the behavior explicit.

Key anchors:

- `starship/stability_monitor.py:113`
- `sre_control/stability_guard.py:92`
- `sre_control/stack.py:138`

### Required decision

Use latched red-line semantics for this pass.

Rationale: conservative operation is safer than silent auto-recovery. Auto-recovery can be introduced later behind an explicit `recovery_window` configuration.

### Required changes

1. Document that `triggered` stays true until `reset()`.
2. Ensure `StabilityGuard` docs do not imply automatic recovery.
3. If event kinds are split in PR-B, Lyapunov-triggered events should be distinguishable from adapter exceptions.

### Required tests

- `test_stability_monitor_latches_until_reset`
- `test_stability_guard_reports_sustained_trigger_without_new_event`

### Acceptance commands

```bash
python -m pytest tests/test_stability_monitor.py tests/test_contracts.py -q
```

## Historical PR-D: Add per-sensor innovation gate policy

Priority: P1

This originated from the earlier SignalFusion open risk. The minimal P1 slice is now implemented in the current workspace: per-sensor thresholds and threshold tracing are in code and tests. Cooldown/re-admission and broader EKF hardening remain explicitly deferred.

### Problem

`SignalFusion.gate_threshold` is global. A single threshold is too coarse for sensors with different dimensions, noise, and false-reject tolerance.

Key anchors:

- `sre_control/signal_fusion.py:63`
- `sre_control/signal_fusion.py:109`
- `starship/ekf.py:81`
- `tests/test_sre_control.py:163`

### Required changes

1. Allow per-sensor gate configuration.
2. Trace the threshold actually used for each sensor.
3. Avoid describing multi-dimensional Mahalanobis thresholds as universal one-dimensional `3σ` rules.
4. Add a minimal cooldown or re-admission policy only if it can be implemented without broadening scope.

### Required tests

- one sensor is rejected while another is accepted in the same tick.
- rejected observations do not contaminate the posterior.
- trace includes `threshold_used` and `innovation_mahalanobis`.

### Acceptance commands

```bash
python -m pytest tests/test_sre_control.py -q
```

## Deferred from this pass

These items remain useful but are not part of the P1 execution gate for this pass:

- EKF Joseph covariance update / PSD regression hardening.
- allocator fallback semantics for all-zero shares beyond the exception taxonomy in PR-B.
- canonicalizing the main knowledge base versus V2 knowledge base.
- richer SRE energy-function examples beyond locking latch/manual-reset semantics.

If any deferred item receives a failing test or contradicts PR-A through PR-D, promote it in the next spec revision.

## PR-E: Prevent docs/schema drift

Priority: P3

### Problem

Docs and runtime event registry can drift. `RUNTIME_STATES.md` previously read like only 8 local event emitters existed, while the review packet and schema now describe 11 event kinds.

Key anchors:

- `docs/RUNTIME_STATES.md:251`
- `docs/EVENT_SCHEMA.md`
- `tests/test_event_schema.py`

### Required changes

1. Update docs to list 11 event kinds, or explicitly separate:
   - 8 core adapter events
   - 2 cross-cutting events
2. Add a docs/schema sync check.
3. Keep counterexamples mandatory for every event kind.

### Required tests

- `test_docs_event_kinds_match_registry`
- existing counterexample test remains mandatory.

### Acceptance commands

```bash
python -m pytest tests/test_event_schema.py -q
```

## PR-F: Strengthen import graph boundaries

Priority: P3

### Problem

Current import graph checks only prevent `starship/` from importing `sre_control/`. They do not enforce a fuller layering contract.

Key anchors:

- `tests/test_import_graph.py:25`

### Required changes

1. Add a whitelist for imports allowed from `starship/`.
2. Forbid lower layers from importing:
   - `sre_control` from `starship`
   - `analysis`
   - `examples`
   - `docs`
3. Keep `sre_control` allowed to depend on `starship`, but not vice versa.

### Required tests

- `test_starship_only_imports_allowed_layers`
- `test_lower_layers_do_not_import_analysis_or_examples`

### Acceptance commands

```bash
python -m pytest tests/test_import_graph.py -q
```

## Final merge gate after this refined pass

Run:

```bash
python -m pytest tests -q
python -m analysis.s10_failure_trace
python -m analysis.run_all
python -m examples.demo_sre_loop
```

Required final status:

```text
quality gates pass
analysis/artifacts/SUMMARY.txt contains event_visible_fraction, true_degraded_fraction, background_event_fraction, and injected_window_coverage
analysis/artifacts/s10_trace_full.jsonl line count equals event_count_total
tests cover one continuous SREControlStack scenario history
tests cover programmer errors are not swallowed
tests cover StabilityMonitor latch-until-reset semantics
tests cover per-sensor SignalFusion gate thresholds and threshold tracing
docs state synthetic evidence boundaries and do not claim production proof
```
