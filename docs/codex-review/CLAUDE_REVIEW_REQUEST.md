# Claude Review Request

This is the current review request template for the project. It supersedes older
requests that asked reviewers to re-check work now covered by tests.

## Expected Output

Return findings first, not a feature summary.

| Priority | File / Area | Finding | Why it matters | Suggested fix |
|---|---|---|---|---|
| P0/P1/P2 | path or module | concrete issue | impact on control stack or SRE migration | executable fix |

If there is no P0 blocker, say so explicitly.

## P0 Review Items

| Topic | Review focus | Related files |
|---|---|---|
| Dependency boundary | `starship/` must remain independent from `sre_control/`; wrappers belong in `sre_control/`. | `tests/test_import_graph.py`, `starship/`, `sre_control/` |
| Event schema closure | Every runtime event kind must have registry docs, counterexamples, and tests. | `sre_control/events.py`, `tests/test_event_schema.py`, `docs/EVENT_SCHEMA.md` |
| Exception taxonomy | Recoverable control-domain failures must not swallow programmer errors. | `sre_control/stack.py`, `sre_control/exceptions.py`, `tests/test_contracts.py` |
| Failure-trace evidence | Section 10 should preserve one continuous stack history and bounded background events. | `analysis/s10_failure_trace.py`, `tests/test_failure_trace.py`, `analysis/artifacts/SUMMARY.txt` |

## P1 Review Items

| Topic | Review focus | Related files |
|---|---|---|
| Section 10 coverage | Does `replica_bound_active` still maintain full expected-kind coverage without background-event leakage? | `analysis/s10_failure_trace.py`, `tests/test_failure_trace.py` |
| Section 5 EKF evidence | Does current radar + near-field fiducial evidence stay clearly scoped to synthetic sensor fusion rather than production sensor proof? | `analysis/s05_ekf.py`, `starship/ekf.py`, `sre_control/signal_fusion.py` |
| StabilityGuard SRE semantics | Does `sre_error_budget_V` remain a clear synthetic SRE example without implying automatic recovery or production alerting completeness? | `starship/stability_monitor.py`, `sre_control/stability_guard.py` |
| Synthetic evidence boundary | Are before/after studies clearly labeled as scenario evidence rather than production proof? | `analysis/`, `wiki/evidence-ledger.md`, `docs/codex-review/OPEN_RISKS.md` |

## P2 Review Items

| Topic | Review focus | Related files |
|---|---|---|
| Naming and UX | Are event names and metric names precise enough for operators and reviewers? | `sre_control/events.py`, `analysis/s10_failure_trace.py` |
| Visual entry points | Does V2 remain the only current HTML entry, with V1 clearly archived? | `docs/V2_Knowledge/knowledge-base.html`, `docs/knowledge-base.html` |
| Scale limits | Do tests and analysis make small synthetic scale explicit? | `tests/`, `analysis/` |
| Backlog granularity | Are next steps split into PR-sized research slices? | `wiki/review-backlog.md`, `docs/codex-review/OPEN_RISKS.md` |

## Reproduction Path

```bash
python -m pytest tests -q
python -m analysis.run_all
python -m analysis.s10_failure_trace
python -m examples.demo_sre_loop
```

Optional:

```bash
python -m pytest tests --collect-only -q
python -m examples.demo_powered_descent
python -m examples.demo_catch_phase
```
