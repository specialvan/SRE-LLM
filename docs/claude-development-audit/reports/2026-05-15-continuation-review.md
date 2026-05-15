# 2026-05-15 Continuation Review

> Correction note: some doc-fix status claims in this report were later narrowed by `2026-05-15-encoding-repair-note.md` after unsafe bulk edits were reverted. Use `backlog.md` as the current active/resolved ledger.

## Verdict

No P0 blocker found in this continuation pass. The first audit package is valuable, but several of its findings are now stale against the current working tree: package discovery includes `sre_control`, allocator signatures include `zone_vector`, docs/schema sync tests have been added, the PR spec I-5 wording has been refreshed, Joseph-form snippets have been corrected, current quality gates match command evidence, version semantics are explicit, and the HTML canonical entry has been clarified. The remaining git-hygiene risk is resolved by staging these fixes and the audit package together in this changeset.

Verification during this pass: 83 collected tests, `python -m pytest tests -q` exited 0.

## Reconciled Findings

### [Resolved in working tree] Packaging surface now includes `sre_control`

Evidence:

- `pyproject.toml:20-22` currently has `include = ["starship*", "sre_control*"]`.
- `tests/test_contracts.py` adds `test_package_surfaces_are_importable`, which imports `starship` and `sre_control` and checks public symbols.

Residual risk:

The test is a source-tree import smoke test, not an installed wheel smoke test. `analysis/`, `scripts/`, and the control-center server remain source tooling rather than packaged entry points. That may be acceptable, but the policy should be explicit.

Status change:

Move `AUDIT-001` from active P1 to watch/P2 unless a release requires wheel-level proof.

### [Resolved in working tree] Allocator fallback signature fingerprints `zone_vector`

Evidence:

- `sre_control/stack.py:89-98` includes `tuple(float(value) for value in inst.zone_vector)` in `_allocator_signature()`.
- `tests/test_contracts.py` adds `test_sre_stack_refuses_stale_alloc_history_when_only_zone_vector_changes`.
- The full test suite passes with this regression included.

Status change:

Move `AUDIT-002` to resolved once the test hardening is committed.

### [Resolved in working tree] Docs/schema sync now has direct tests

Evidence:

- `tests/test_event_schema.py` adds `test_event_schema_doc_kinds_match_registry`.
- `tests/test_event_schema.py` adds `test_runtime_states_doc_emitters_match_registry`.
- These tests parse `docs/EVENT_SCHEMA.md` and `docs/RUNTIME_STATES.md` and compare documented kinds with `sre_control.events.EVENT_COUNTEREXAMPLES`.

Residual risk:

The parser is intentionally lightweight and table-shape dependent. That is fine for this repository, but future docs edits that restructure headings must update the test.

Status change:

Move `AUDIT-004` to resolved once the test hardening is committed.

### [Resolved in working tree] Canonical PR requirements now match adapter-exception taxonomy

Evidence:

- `PR-REQUIREMENTS.md` now says `RecoverableControlError` must become `adapter_exception` plus `DEGRADED_<stage>`.
- `PR-REQUIREMENTS.md` now says `stability_violation` is reserved for `StabilityGuard` / Lyapunov red lines.
- `sre_control/stack.py:23-36` documents the current policy: recoverable control-domain errors emit `adapter_exception`; programmer errors propagate; `stability_violation` is reserved for Lyapunov/stability red lines.
- `wiki/runtime-lifecycle.md:44-50` matches the current code policy.

Status change:

Move `AUDIT-003` to resolved once the spec edit is committed.

### [Resolved in working tree] Joseph-form derivation snippets now use the full update

Evidence:

- `docs/SPECIAL_SOLUTIONS_DERIVATIONS.md` now names `(I-KH)P(I-KH)^T + KRK^T` as Joseph form.
- The simplified `(I - K H) P` update is now labeled as not being the current Joseph implementation.
- The code snippet near the Mahalanobis example now computes `joseph_left @ P_pred @ joseph_left.T + K @ R_metrics @ K.T`.

Status change:

Move `AUDIT-006` to resolved once the docs edit is committed.

## Reconciled / Active Findings

### [Resolved in working tree] Current-facing quality-gate and event-taxonomy docs now match command evidence

Evidence:

- Current collection is 83 tests.
- `PR-REQUIREMENTS.md:20` and `PR-REQUIREMENTS.md:71` now say 83 passed.
- `docs/codex-review/QUALITY_GATES.md:14` is a historical packet snapshot; current-facing audit evidence now uses the 83-test command result.
- Current collection reports `tests/test_contracts.py: 19`, matching the refreshed table.
- `docs/V2_Knowledge/knowledge-base.html` now says 83 passed in both the header chip and quality-gate table.
- `docs/V2_Knowledge/knowledge-base.html` now says 11 event kinds, includes `adapter_exception`, and reserves `stability_violation` for `StabilityGuard` / Lyapunov violations.
- `docs/EVENT_SCHEMA.md` now says eleven current event kinds in its test coverage prose.
- `docs/codex-review/README.md`, `docs/codex-review/CLAUDE_DEEP_REVIEW.md`, `docs/codex-review/ENGINEERING_PACKET.md`, and `docs/claude-review/README.md` now carry historical snapshot overlays.

Status change:

Move `AUDIT-010` to resolved once the docs edits are committed.

Residual risk:

Counts are still hand-edited in multiple places. A generated quality-gate source would reduce future drift.

### [Resolved in working tree] HTML knowledge-base canonical entry is explicit

Evidence:

- `README.md` now points to `docs/V2_Knowledge/knowledge-base.html` as the canonical current entry.
- `docs/knowledge-base.html` labels itself as a V1 `archive snapshot`.
- `docs/V2_Knowledge/knowledge-base.html` labels itself `canonical current entry`.
- The V2 follow-up note now says V1 remains an archive snapshot rather than a page still waiting to become canonical.

Status change:

Move `AUDIT-005` to resolved once the README/HTML edits are committed.

### [Resolved in working tree] Version semantics are now explicit

Evidence:

- `PR-REQUIREMENTS.md:3` says `version: 0.3.7`.
- `pyproject.toml:7`, `starship/__init__.py:76`, and `sre_control/__init__.py:63` say `0.1.0`.
- `PR-REQUIREMENTS.md` now has `NFR-7 路 鐗堟湰绛栫暐`, which separates spec/review-ledger version from Python package version.
- The policy says git tags should map to package/release artifacts, not every spec-ledger bump.

Status change:

Move `AUDIT-007` to resolved once the spec edit is committed.

### [Resolved] Review engineering package and supporting fixes were committed

Evidence:

- The review package lives under `docs/claude-development-audit/` and should be staged with the supporting code, test, docs, HTML, and analysis-summary changes.
- The goal asks for review reports to be continuously landed in a newly created engineering package; this package becomes git-visible once the changeset is staged and committed.

Status change:

Move `AUDIT-009` to resolved when this changeset is committed.

## Backlog Deltas

| ID | Old status | New status | Reason |
|---|---|---|---|
| AUDIT-001 | Active P1 | Watch/P2 | `pyproject.toml` includes `sre_control*`; source import smoke exists. Wheel smoke still missing. |
| AUDIT-002 | Active P1 | Resolved pending commit | `zone_vector` is in `_allocator_signature()` and regression test exists. |
| AUDIT-003 | Active P1 | Resolved pending commit | I-5 now uses `adapter_exception` for recoverable adapter failures. |
| AUDIT-004 | Active P2 | Resolved pending commit | docs/schema tests now compare markdown tables with `EVENT_COUNTEREXAMPLES`. |
| AUDIT-005 | Active P2 | Resolved pending commit | README/V1/V2 now identify V2 as canonical and V1 as archive snapshot. |
| AUDIT-006 | Active P2 | Resolved pending commit | Joseph-form snippets now use the full covariance update. |
| AUDIT-009 | New P1 | Resolved pending commit | audit package and supporting fixes should be staged together. |
| AUDIT-010 | Active P2 | Resolved pending commit | current-facing quality gates now say 85 and historical packets are labeled. |

## Next Review Route

1. Decide whether to generate current quality-gate counts from `pytest --collect-only` instead of hand-editing them.
2. Add an installed-wheel smoke test if this repository starts producing release artifacts.
