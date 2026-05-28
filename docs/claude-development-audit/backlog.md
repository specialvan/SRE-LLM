# Audit Backlog

This is the live audit ledger for current-facing development follow-up. Older
reports under this directory are historical snapshots; when they conflict with
this file, `wiki/review-backlog.md`, source code, tests, or generated artifacts,
trust the current evidence and update the stale ledger.

Status values:

- `Active`: current risk or confirmed defect.
- `Resolved`: implemented in current code and covered by tests or generated
  evidence, but kept for review history.
- `Watch`: not broken now, but easy to regress or overstate in future prose.

## Active

| ID | Priority | Area | Issue | Next action |
|---|---|---|---|---|
| - | - | - | No active audit defects are recorded in the current workspace. | Continue review-ledger hygiene when new packets arrive. |

## Resolved

| ID | Area | Resolution evidence |
|---|---|---|
| RES-001 | Per-sensor innovation gates | `Signal.gate_threshold`, `SignalFusion._resolve_threshold()`, trace `threshold_used`, and mixed accept/reject tests are present. |
| RES-002 | Allocator fallback semantics | `SREControlStack` reuses last-good allocation shares only when the allocator signature remains valid and otherwise falls back to zero on bootstrap/no-history paths. |
| RES-003 | EKF Joseph covariance hardening | `starship/ekf.py` uses Joseph form, covariance symmetrization, singular-innovation gated no-op behavior, and a default covariance eigenvalue floor covered by `tests/test_ekf.py`. |
| RES-004 | Programmer-error propagation | Stack exception handling catches `RecoverableControlError` and related adapter-domain failures without swallowing programmer errors such as `AttributeError` or `TypeError`. |
| RES-005 | Allocator topology fingerprint | `_allocator_signature()` includes topology-sensitive `Instance.zone_vector` data, with contract tests for topology-only mutations. |
| RES-006 | Docs/schema sync | `tests/test_event_schema.py` parses `docs/EVENT_SCHEMA.md` and `docs/RUNTIME_STATES.md` against the runtime event registry and counterexamples. |
| RES-007 | Package discovery and smoke | `pyproject.toml` includes both `starship*` and `sre_control*`; `scripts/package_smoke.py` builds a wheel and imports both packages from the wheel path. |
| RES-008 | Review package structure | `docs/claude-development-audit/`, `docs/codex-review/`, `docs/opus-review/`, and `claude-review/docs/v2026-05-26/` preserve review packets while live status is summarized in wiki and Codex review ledgers. |
| RES-009 | Quality-gate count generation | `scripts.quality_gate_counts` derives current pytest counts from a real test run plus collection parity and installed-wheel smoke before updating current-facing docs. |
| RES-010 | Canonical HTML entry | README, wiki, and review docs identify `docs/V2_Knowledge/knowledge-base.html` as current and `docs/knowledge-base.html` as a V1 archive snapshot. |
| RES-011 | Control-center exposure policy | `scripts/control_center_server.py` serves fixed localhost HTML/API routes with Host checks; `tests/test_control_center.py` covers allow/deny behavior. |
| RES-012 | Adapter exception taxonomy | `adapter_exception` events include stage, exception type, cause type, adapter family, fault family, fallback action, and recoverable fields. |
| RES-013 | StabilityGuard latch semantics | `StabilityMonitor.triggered` remains latched until explicit reset, and runtime/docs distinguish Lyapunov red-line events from recoverable adapter exceptions. |
| RES-014 | Section 10 continuous-stack evidence | `analysis.s10_failure_trace` uses one continuous stack, exports full/sample JSONL traces, bounds background events, and checks injected-window expected-kind coverage. |
| RES-015 | Section 10 trace feedback and metrics | The scenario records stack-returned replica counts directly, uses vacuous visibility for empty injected sets, writes sorted JSONL keys, and validates tick-time drift with tolerance. |
| RES-016 | Section 11 Catch/SRE wrapper | `sre_control.CatchLoadAdapter` wraps catch-allocation residual visibility without making `starship/` import SRE schema, and tests cover feasible, total-overload, and placement-infeasible regimes. |
| RES-017 | Section 12 replay fixture | `analysis/fixtures/sre_replay.jsonl` and `analysis.s12_sre_replay` provide fixed synthetic replay evidence with event visibility, recovery, operator-action, and compound incident-window diagnostics. |
| RES-018 | Event evidence manifest | `analysis.evidence_manifest` exports repo-relative S10/S11/S12 and stack-contract evidence with artifact byte metadata; `analysis.evidence_report` validates shape, counts, parseability, runtime events, and byte identity. |
| RES-019 | Stack data contract | `sre_control.stack_data_contract()` exports non-production research-stage contracts with direct event kinds and runtime route prefixes; docs/tests/report checks guard drift. |
| RES-020 | Synthetic evidence boundaries | `scripts.evidence_boundary_lint.PUBLIC_EVIDENCE_BOUNDARY_DOCS` defines the public/review document surface linted for unqualified production-readiness wording, SpaceX-internals claims, and production-proof wording while allowing explicit negated boundary statements. |
| RES-021 | Signal-fusion numerics | `SignalFusion` uses exact OU discretization, validates positive gate thresholds, and caps consecutive rejection counters with regression coverage. |
| RES-022 | Canary rejected-step learning | `CanaryScheduler.observe()` refits the local slope after nonzero attempted rollout steps, including rejected trials, and traces `refit_rejected`. |
| RES-023 | Pool capacity sizing | `PoolCapacityPlanner` uses true `math.ceil(demanded)`, configurable `rps_per_conn`, and emits exact-saturation advisory evidence through `pool_capacity_clipped`. |
| RES-024 | Allocator input validation | `WeightedLoadBalancer` rejects empty instance lists and mismatched zone-vector dimensions at construction time. |
| RES-025 | Traffic-switcher input validation | `FastTrafficSwitcher` rejects non-positive `rate_max` before minimum-time calculations. |
| RES-026 | Variable-dt stability time | `SREControlStack.step()` feeds cumulative elapsed time to the stability monitor instead of deriving timestamps from tick index times current `dt`. |
| RES-027 | Strict JSON diagnostics | Replay recovery diagnostics use JSON `null` for unrecovered windows instead of non-standard `Infinity`. |
| RES-028 | Evidence report collect-all behavior | `analysis.evidence_report` accumulates multiple JSONL, trace-shape, fixture-shape, and event-schema row failures before returning. |
| RES-029 | Analysis runner failure reporting | `analysis.run_all.main()` records import/study failures in `SUMMARY.txt`, continues later studies, and exits nonzero after writing the summary. |
| RES-030 | Release hygiene | `tests/test_release_hygiene.py` keeps package-version consistency separate from spec/review-ledger versioning. |
| RES-060 | Opus v2.0 F50-F60 and G1 | F50-F60 are remediated in the current workspace with regression tests. G1 is resolved by quality-gate self-healing: `scripts.quality_gate_counts` runs `analysis.evidence_manifest` before `analysis.evidence_report` when collecting live counts. |
| RES-081 | Opus v2.1 F61-F81 | F61-F81 are remediated in the current workspace. Evidence includes refreshed browser manifest/report artifacts; non-finite input guards in SignalFusion, SLOGuardrail, and WeightedLoadBalancer; Canary rejected warm-start trust-region shrink tests; strict JSON writers; repo-relative browser manifest paths; `analysis.run_all(artifacts_dir=...)` forwarding; control-center share-state whitelist/escaping and loopback bind enforcement; current browser/package/integration gates in `scripts.quality_gate_counts`; read-only `python -m scripts.quality_gate_counts --check`; and manifest replay errors that include manifest, viewport, DOM path, and regeneration command. |

## Watch

| ID | Area | Watch condition |
|---|---|---|
| WATCH-001 | Synthetic evidence boundary | Before/after studies and replay fixtures are scenario-internal research evidence. Future reports, READMEs, wiki pages, V2 HTML, and review packets must keep them out of production-proof or SpaceX-internals claims. |

## Current Verification Gates

Before claiming a new implementation pass is complete, run:

```bash
python -m pytest tests -q
python -m analysis.s10_failure_trace
python -m analysis.run_all
python -m analysis.evidence_manifest
python -m analysis.evidence_report
python -m scripts.control_center_browser_smoke --report-manifests --report-json analysis/artifacts/control-center-browser-evidence-report.json
python -m scripts.package_smoke
python -m scripts.control_center_integration_audit
python -m examples.demo_sre_loop
python -m examples.demo_powered_descent
python -m examples.demo_catch_phase
python -m scripts.quality_gate_counts --check --skip-expensive
```

Current-facing count-bearing docs are maintained by:

```bash
python -m scripts.quality_gate_counts
```
