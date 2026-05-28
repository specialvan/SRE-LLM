# Evidence Ledger

This ledger describes what current evidence can and cannot prove. Source code,
tests, and generated artifacts remain authoritative.

## Current Quality Gates

Current local baseline from this continuation pass:

```bash
python -m pytest tests -q      # 504 passed
python -m analysis.run_all     # All 12 studies finished
python -m analysis.evidence_manifest  # S10/S11/S12 + stack-contract artifacts exported
python -m analysis.evidence_report    # Manifest artifact byte identity, parse/schema/count validated
```

This proves the current project is runnable and reproducible in the local
research environment. It does not prove production readiness.

## Study Evidence Boundaries

| Study | Current observation | Supports | Does not support |
|---|---|---|---|
| Section 1 Lossless | `pos_err 148.3 -> 2.125e-6` | Convexified path is effective in the synthetic PDG scenario | SpaceX official implementation or all landing scenarios |
| Section 4 Cone | `cone_violations 0.974 -> 0` | Hard guardrail removes infeasible thrust proposals | Business value is preserved after projection |
| Section 5 EKF | `vel_rmse 629.4 -> 9.374`; `fiducial_updates=31`; `multi_source_tick_fraction=0.3875`; `near_field_pos_rmse=2.52 m` | Radar + near-field fiducial fusion improves the synthetic descent estimate | Real sensor integrity or production-grade multi-source fusion |
| Section 8 Allocation | `saturation_violation_pct 33.75 -> 0` | Bounded solve removes capacity violations | Residual disappears or demand is fully satisfied |
| Section 9 SRE Stack | `slo_violation_pct 25 -> 10` | Control stack trades higher replica cost for fewer SLO violations | Globally optimal production capacity planning |
| Section 10 Failure Trace | `0 events / 0 kinds -> 16 events / 4 kinds` | Continuous stack scenario exposes observable event channels with bounded background events and full injected-window expected-kind coverage | Production incident observability or all possible fault windows |
| Section 11 Catch/SRE Wrapper | `capacity_violation_pct 66.67 -> 0`; `event_visible_fraction=1.0`; three regimes covered | SRE wrapper preserves residual visibility for total overload and placement infeasibility while staying quiet on feasible cases | General load-balancer optimality or SpaceX catch-controller implementation details |
| Section 12 SRE Replay | `expected_event_visible_fraction=1.0`; `stability_event_visible_fraction=1.0`; `operator_action_coverage=1.0`; `recovered_window_fraction=1.0`; `multi_signal_window_coverage=1.0`; 19 ticks | A fixed synthetic replay stream can exercise expected event channels, error-budget stability checks, event-clean recovery windows, operator-action annotations, and one compound multi-signal incident without nominal background noise | Production trace representativeness or incident coverage completeness |
| Event Evidence Manifest | `event_evidence_manifest.json` indexes S10/S11/S12 artifacts and `sre_stack_data_contract.json` with repo-relative paths and `artifact_metadata` byte-identity records; `docs/EVENT_EVIDENCE_MANIFEST.md` documents the contract; `analysis.evidence_report` validates top-level manifest shape, closed study/contract ID sets, required study/contract entry sets, required generic and entry-specific fields plus value types, documented fixed values, bounded numeric ranges, artifact key sets, artifact metadata key parity, SHA-256 digests, byte size values, expected artifact extensions, artifact path value types, portability, repo-root containment, referenced files, JSON/JSONL/PNG parseability, runtime event schema, stack-contract non-production scope, stage event-kind registry membership, observed trace-event routing, and count consistency; `scripts.quality_gate_counts` requires the manifest/report gate commands | Reviewers can inspect stable machine-readable event/replay/contract evidence without parsing console banners, and tests catch manifest/docs drift, unknown study/contract IDs, missing or duplicated study/contract entries, missing top-level manifest fields, missing generic or entry-specific fields, wrong study/contract field value types, fixed value drift in study labels or contract claims, out-of-range fractions or negative counts, missing or unexpected artifact keys, malformed or stale artifact metadata, byte-identity mismatches, wrong artifact extensions, artifact path non-string values, absolute local artifact paths, parent-directory artifact escapes, missing artifact files, malformed JSON/JSONL/PNG artifacts, invalid runtime events, unsafe stack-contract claims, unknown stage event kinds, trace events disallowed by the routed contract stage, inconsistent artifact counts, or quality-gate command drift | Completeness beyond the covered synthetic studies |

## Section 10 Evidence Shape

PR-A converged Section 10 to this audit shape:

- One continuous `SREControlStack` instance.
- Faults are injected through inputs or constraints, not by swapping stack
  instances.
- Always-on nominal allocator residual is removed from the background path.
- Current primary metrics:
  - `event_visible_fraction = 1.0`
  - `true_degraded_fraction = 0.2167`
  - `background_event_fraction = 0.0`
  - `injected_window_coverage`, including `replica_bound_active = 1.0`
- Full evidence is exported to `analysis/artifacts/s10_trace_full.jsonl` and a
  reviewer-friendly sample JSONL.
- Cross-study event evidence is indexed in
  `analysis/artifacts/event_evidence_manifest.json`.
- `degraded_tick_fraction = 21.67` remains only as a coarse legacy metric.

## Interpretation Rules

Acceptable wording:

- "Quality gates pass."
- "Synthetic before/after scenarios show mechanism-level benefit."
- "Runtime events have an observable channel."
- "Section 10 is now continuous-stack evidence with bounded background events."
- "Section 11 shows wrapper-layer residual visibility across feasible,
  total-overload, and placement-infeasible SRE scenarios."
- "Section 12 is synthetic replay-fixture evidence, not a production trace."

Avoid:

- "The event lifecycle is fully proven."
- "The control stack is production ready."
- "These algorithms are SpaceX internal implementation."
- "Synthetic evidence is equivalent to a production benchmark."
