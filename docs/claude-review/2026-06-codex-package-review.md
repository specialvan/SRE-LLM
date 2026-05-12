# 2026-06 Codex Review Package 深度评审

Date: 2026-05-12

Review round: 2026-06 C+A2

Reviewed package: [`docs/codex-review/`](../codex-review/)

Branch at review time: `gan-session-fix-07`

HEAD at review time: `bb891a1 docs: 新增 Codex 汇总评审包`

## Current Verdict

Current verdict: **merge-ready**

No P1/P2 merge blockers were found in the Codex review package or the
current code state. The package's central claim, that F-001 through F-010
are resolved, matches the sampled source, tests, and completion records.

The main remaining risk is not a code blocker. Some historical tracker
documents still read like pre-resolution work queues. They should be
treated as archived context unless updated with a clear "superseded"
banner.

## Scope

Inputs reviewed:

- [`docs/codex-review/README.md`](../codex-review/README.md)
- [`docs/codex-review/2026-06-codex-summary.md`](../codex-review/2026-06-codex-summary.md)
- [`docs/claude-review/2026-06-spec-completion.md`](2026-06-spec-completion.md)
- [`docs/claude-review/findings.md`](findings.md)
- [`docs/codex-handoff.md`](../codex-handoff.md)
- [`docs/implementation-roadmap.md`](../implementation-roadmap.md)
- Source and tests for F-001 through F-010 contracts

## Finding Audit

| Finding | Review result | Evidence checked |
|---|---|---|
| F-001 lease refresh visibility | Resolved | `LeaseRefreshLoop._run` invokes `on_failure`; `DecisionApp.mark_lease_unhealthy` flips `/readyz`, increments `gan_lease_refresh_failures_total`, and emits `lease.refresh.failed`; `tests/test_leases.py` covers metric/log/readiness paths. |
| F-002 shadow observability | Resolved | `_finalize_decision` applies `_shadow_wrap` before `_publish_decision`; metrics and `decide.finished` use final kind; `decide.shadow_rewritten` carries original/final kind; shadow tests cover metric, diff counter, log, advisory, and trace fields. |
| F-003 trace config privacy | Resolved | `AppConfig.to_trace_dict()` is allowlist-backed; `trace.input.config` uses it; `log_sink` is excluded; `tests/test_trace_privacy.py` locks snapshot and purity behavior. |
| F-004 service mutation | Resolved | Search found no runtime `_deps` mutation; dependency observation flows through explicit `dependencies=`; `test_decide_does_not_mutate_service_object` covers repeated calls. |
| F-005 rating scaling contract | Resolved | `_RATING_*` constants, `_rating_scaling_version()`, training metadata write, runtime mismatch downgrade, and mismatch logging are present; `tests/test_rating_scaling.py` covers snapshot/version/hydrate behavior. |
| F-006 artifacts package split | Resolved | `sre/artifacts/` is split into `bundle.py`, `cox.py`, `metadata.py`, `retention.py`, and `__init__.py`; each file is under the documented 180-line ceiling. |
| F-007 public context serde | Resolved | `ReleaseContext.from_dict` is the public construction API; `_ctx_from_dict` remains only inside `cli.py` as a compatibility alias; tests prevent public modules from importing the private helper. |
| F-008 SQLite migration shape | Resolved | `_idempotent_statement_skip` is generic for `ALTER TABLE ... ADD COLUMN`; no production `if version == 5` branch remains; SQLite tests cover legacy column adoption and source check. |
| F-009 handoff/roadmap dedupe | Resolved | `codex-handoff.md` now points to roadmap for phase details; roadmap points back to handoff for narrative next-step view. |
| F-010 replay naming | Resolved | Replay fixtures follow `{scenario}_{expected_kind}.json`; README documents the convention; `test_fixture_naming_matches_convention` enforces it. |

## Findings

### [P3] Historical review trackers still look current

File / line: [`action-items.md`](action-items.md) and
[`test-coverage-gaps.md`](test-coverage-gaps.md)

Why it matters: both files still contain pre-resolution language such as
"合入前必做" and "现有 105 个测试未覆盖", while the current state is 138
collected tests and F-001 through F-010 resolved. A new reviewer who enters
through these files can incorrectly reopen closed blocker work.

Suggested fix: add a short banner to both files saying they are historical
trackers superseded by `2026-06-spec-completion.md` and this review, or
move them under an archive subdirectory after extracting still-relevant
future work into the 2026-07 plan.

### [P3] Quick benchmark is smoke-only in CI

File / line: [`bench/latency.py`](../../bench/latency.py) and
[`ci.yml`](../../.github/workflows/ci.yml)

Why it matters: `python -m bench.latency --quick` reports p99 but does not
fail the process on p99 regressions. CI currently runs the quick mode, so
latency regressions are visible only if a reviewer reads the log.

Suggested fix: either make `--quick --p99-ms <budget>` enforce the budget,
or add a separate non-quick CI step with a relaxed threshold. Keep the
threshold high enough to avoid flaky failures on shared runners.

## Verification

Commands run during this review:

```powershell
python -m pytest -q
python -m pytest --collect-only -q
python -m bench.latency --quick
rg -n "if version == 5" gan_matchmaking tests
rg -n "from \.\.?cli import _ctx_from_dict|_ctx_from_dict" gan_matchmaking
```

Observed results:

- Full test suite passed.
- Collection count is 138 tests.
- Quick benchmark p99 was about `2.323ms`; this remains under the
  documented non-quick default budget, but quick mode does not assert.
- `if version == 5` appears only in the SQLite regression test.
- `_ctx_from_dict` appears only in `gan_matchmaking/cli.py`.

## Residual Risks

- `FileLease` is still a local filesystem lease. It is a useful single
  writer guard on one host, not a distributed coordination primitive.
- Cox and retention thresholds remain calibration candidates until real
  observation data is available.
- Replay coverage is good for contract regression, but the next useful
  step is incident narrative expansion around artifact failure, breaker
  short-circuit, and shadow/advisory transitions.
- Historical docs need stronger status banners so "review trail" and
  "current work queue" do not blur together.

## Recommended 2026-07 Scope

1. Add status banners or archive markers for superseded trackers, then
   open a clean `2026-07-session-review.md`.
2. Expand incident-style replay for artifact validation failure, breaker
   short-circuit, and shadow/advisory rollout transitions.
3. Prototype one distributed lease backend only if the target deployment
   truly needs multiple writable replicas.
4. Define artifact bundle storage policy across local corpus, object
   storage, and CI cache hydration.
5. Add a real latency budget gate, either in quick mode or as a dedicated
   CI benchmark step.
6. Calibrate Cox and retention thresholds against production observation
   data.
