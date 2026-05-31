# Evidence Artifact Test Split Design

> Historical planning artifact; it is not the current handoff.
> Opus review should start from `docs/opus-review/HANDOFF.md`, then verify
> live status in `wiki/review-backlog.md`,
> `docs/codex-review/OPEN_RISKS.md`, and
> `docs/codex-review/QUALITY_GATES.md`.

## Context

`tests/test_evidence_manifest.py` remains the largest test file and still contains direct tests for helper functions that now live in `analysis.evidence_artifacts`. The current code already has `tests/test_evidence_artifacts.py`, so the next B2 slice can reduce the giant file without changing production behavior.

## Goal

Move direct artifact-validator unit tests out of `tests/test_evidence_manifest.py` into `tests/test_evidence_artifacts.py` while preserving report-path coverage and the total test count.

## Design

Relocate the tests that call `evidence_artifacts._s10_trace_shape_errors`, `_invalid_jsonl_errors`, `_s12_fixture_shape_errors`, and `schema_invalid_event_errors` directly. Keep end-to-end `evidence_report.main(...)` tests in `tests/test_evidence_manifest.py` because they verify CLI behavior and error summaries.

This is a test-only refactor. No runtime modules should change.

## Acceptance

- `tests/test_evidence_artifacts.py` owns the direct artifact-validator unit tests.
- `tests/test_evidence_manifest.py` no longer contains those direct helper tests.
- Collect-only count for the affected files remains unchanged.
- Focused artifact and manifest tests pass.
