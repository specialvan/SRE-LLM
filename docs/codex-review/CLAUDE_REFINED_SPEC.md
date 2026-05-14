# Claude Refined Spec — Implemented Follow-up Pass

> Scope: refine the `gan-session-fix-07` Codex review packet into executable and auditable follow-up work. This document supersedes its earlier "next pass" wording: PR-A through PR-D have now been implemented in this branch.

## Current verdict

Merge-ready.

F-001 through F-010 remain resolved in the runtime path. This pass did not reopen historical findings; it added replay/artifact hardening and documentation cleanup discovered during Claude's review of `docs/codex-review/2026-06-codex-summary.md`.

`docs/claude-review/spec-v3/README.md` remains the broader D+A2 execution spec for tracker cleanup, latency gate hardening, public API snapshots, and HTTP readiness integration. This document records the artifact/replay refinement work completed from that review.

## Non-goals preserved

- Do not reopen already resolved F-001 through F-010 without a new failing test or reproducible regression.
- Do not rewrite the artifact package split.
- Do not remove legacy replay support unless explicitly scoped.
- Do not introduce a distributed lease backend in this pass; keep that as the next review scope.

## Implemented changes at a glance

| PR | Status | What changed | Evidence |
|---|---:|---|---|
| PR-A | Done | Runtime hydration and replay validation now share retention rating-scaling compatibility semantics. | `tests/test_rating_scaling.py`, `tests/test_replay_export.py` |
| PR-B | Done | Modern fitted replay fixtures carry and assert current `rating_scaling_version`. | `tests/fixtures/replay/artifact_canary.json`, `tests/test_replay_corpus.py` |
| PR-C | Done | Replay corpus now includes artifact scaling mismatch fallback and open breaker short-circuit narratives. | `tests/fixtures/replay/artifact_scaling_mismatch_go.json`, `tests/fixtures/replay/breaker_open_escalate.json` |
| PR-D | Done | Lease readiness boundary is documented as readiness/drain, not direct request blocking. | `docs/architecture/06-concurrency-and-leases.md`, `docs/codex-review/2026-06-codex-summary.md` |

## PR-A: Share artifact compatibility between runtime hydration and replay validation

Priority: P2 replay-hardening follow-up; complete.

### Problem addressed

Runtime hydration refused retention artifacts whose `rating_scaling_version` did not match current rating-scaling constants, but replay bundle validation did not enforce the same rule. That allowed fitted-artifact replay export to accept a bundle that runtime later downgraded or partially ignored.

### Implemented behavior

- Shared helper lives in the artifact layer:
  - `retention_scaling_compatibility(retention)`
  - returns machine-readable status: `match`, `mismatch`, `unknown`, `absent`
  - exposes expected version, actual version, and artifact version
- Runtime hydration uses the helper:
  - `match`: hydrate retention
  - `unknown`: preserve legacy runtime hydration and mark trace status `unknown`
  - `mismatch`: log warning, mark trace status `mismatch`, drop retention and fall back
  - `absent`: mark trace status `absent`; do not falsely report `match`
- Replay validation uses the helper:
  - `match`: accept
  - `mismatch`: reject with `DataError`
  - `unknown`: reject by default
  - `unknown`: accept only with explicit `allow_legacy_unknown=True`
  - `absent`: allowed by scaling validation; existing fitted/empty-bundle rules still apply
- Replay validation error details include:
  - artifact directory
  - artifact version
  - expected rating-scaling version
  - actual rating-scaling version
  - rating-scaling status

### Additional hardening from review

During review, the replay/artifact boundary also gained:

- artifact filename basename validation in `ArtifactsConfig`
- replay-side filename validation using both POSIX and Windows path semantics
- rejection of `../...`, `..\\...`, absolute POSIX paths, Windows drive paths, and UNC paths
- CLI opt-in flag `--allow-legacy-unknown` for explicitly exporting legacy unknown fitted artifacts

### Tests

Covered by:

- `tests/test_rating_scaling.py::test_replay_validation_rejects_rating_scaling_mismatch`
- `tests/test_rating_scaling.py::test_replay_validation_accepts_rating_scaling_match`
- `tests/test_rating_scaling.py::test_replay_validation_requires_explicit_legacy_unknown`
- `tests/test_rating_scaling.py::test_runtime_and_replay_classify_scaling_status_consistently`
- `tests/test_rating_scaling.py::test_absent_retention_scaling_is_explicit`
- `tests/test_replay_export.py::test_validate_artifact_bundle_rejects_path_traversal_filename`
- `tests/test_core_config.py::test_invalid_artifact_filename_rejected`

## PR-B: Make modern fitted replay fixtures carry rating-scaling metadata

Priority: P3, complete.

### Problem addressed

The inline fitted replay fixture writer built retention metadata without `rating_scaling_version`. Runtime marked that as `unknown` and still hydrated retention, which preserved legacy behavior but meant the golden fitted-artifact replay corpus did not exercise the modern scaling contract.

### Implemented behavior

- Modern fitted replay fixture metadata includes `rating_scaling_version`.
- `artifact_canary.json` asserts `trace.artifacts.rating_scaling_status == "match"`.
- Legacy unknown replay behavior remains possible but must be explicit:
  - validation requires `allow_legacy_unknown=True`
  - corpus tests require any fixture that expects `unknown` to be visibly legacy-named
- Modern fixture checks exclude bootstrap fallback fixtures that intentionally use mismatched artifacts to test downgrade behavior.

### Tests

Covered by:

- `tests/test_replay_corpus.py::test_modern_artifact_fixture_has_scaling_version`
- `tests/test_replay_corpus.py::test_modern_artifact_replay_reports_scaling_match`
- `tests/test_replay_corpus.py::test_inline_artifact_writer_persists_scaling_version`
- `tests/test_replay_corpus.py::test_legacy_artifact_fixture_is_explicitly_named`

## PR-C: Expand replay corpus for artifact failure narratives

Priority: P3, complete.

### Problem addressed

The replay corpus validated happy-path fitted artifacts and decision naming, but it lacked incident-style guardrail/failure narratives.

### Implemented additions

- `tests/fixtures/replay/artifact_scaling_mismatch_go.json`
  - stale retention rating-scaling version is rejected
  - runtime falls back to bootstrap/fallback scoring
  - asserts `artifacts.rating_scaling_status == "mismatch"`
  - asserts artifact retention is absent in trace after downgrade
- `tests/fixtures/replay/breaker_open_escalate.json`
  - open circuit breaker short-circuits scoring
  - decision kind is `escalate`
  - asserts `circuit_breaker.state == "open"`
- Replay harness now supports fixture-level `"circuit_breaker": "open"` setup.
- `tests/fixtures/replay/README.md` catalog includes the new narratives.

### Remaining replay growth

This pass intentionally covers two PR-C narratives. Useful future corpus additions:

- invalid artifact metadata-shape fixture with `artifacts.validation_errors`
- advisory-mode rollout fixture with `trace.shadow_mode == "advisory"`
- broader lease-loss HTTP/readiness fixture variants if deployment harness grows

## PR-D: Clarify lease readiness boundary

Priority: P3, complete.

### Problem addressed

F-001 resolved readiness semantics, but deployment docs still needed to clarify that local `FileLease` is not a distributed lock and lease loss flips readiness rather than directly blocking `/v1/decide` or `/v1/observe`.

### Implemented documentation contract

Documented in `docs/architecture/06-concurrency-and-leases.md` and linked from `docs/codex-review/2026-06-codex-summary.md`:

- `/healthz`: process health only
- `/readyz`: includes lease health
- lease refresh failure makes the pod not ready
- traffic drain is delegated to the orchestrator
- `FileLease` is local-filesystem coordination only, not a multi-writer distributed lease
- `/v1/decide` and `/v1/observe` are not directly blocked by lease loss; the boundary is readiness/drain

### Related documentation cleanup

This pass also updated stale architecture docs that still described F-001/F-002 as open:

- `docs/architecture/07-observability-contract.md`
- `docs/architecture/04-state-and-failure-domains.md`
- `docs/architecture/02-decision-flow.md`
- `docs/architecture/08-rollout-and-governance.md`
- `docs/implementation-roadmap.md`
- `docs/codex-review/README.md`

## Final merge gate evidence

Commands run after implementation and documentation cleanup:

```bash
python -m pytest tests/test_rating_scaling.py tests/test_replay_corpus.py tests/test_replay_export.py tests/test_core_config.py tests/test_http_service.py tests/test_artifacts_public_api.py -q
python -m pytest -q
python -m bench.latency --quick --p99-ms 50
```

Observed result:

```text
focused tests: passed
full pytest suite: passed
latency quick gate: passed, p99_ms = 3.0467 (< 50 ms)
final code review: no blocking findings
final security review: no blocking findings
```

Required final status:

```text
F-001..F-010 remain resolved
runtime and replay artifact compatibility are aligned
modern fitted replay fixtures exercise rating_scaling_status=match
legacy artifact behavior is explicit
artifact filename traversal is rejected at config and replay validation boundaries
no new P1/P2 blockers
```

## Recommended 2026-07 scope after this pass

1. Add artifact metadata-shape replay fixture coverage for `artifacts.validation_errors`.
2. Add advisory-mode replay fixture coverage for `trace.shadow_mode == "advisory"`.
3. Prototype one distributed lease backend if deployment needs multiple writable replicas.
4. Add Cox artifact semantic compatibility/version contract.
5. Calibrate Cox and retention thresholds against real observation data.
6. Expand trace privacy tests for newly added config fields and path-like values.
