# Evidence Report Orchestrator Cleanup Implementation Plan

> Historical planning artifact; it is not the current handoff.
> Opus review should start from `docs/opus-review/HANDOFF.md`, then verify
> live status in `wiki/review-backlog.md`,
> `docs/codex-review/OPEN_RISKS.md`, and
> `docs/codex-review/QUALITY_GATES.md`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce residual orchestration duplication in `analysis.evidence_report` after the report-path tests have been split.

**Architecture:** Keep `analysis.evidence_report` as the reviewer CLI and phase orchestrator. Do not move validation semantics or change CLI output strings. Remove compatibility imports that are no longer referenced by tests, and centralize repeated failure-summary printing in small local helpers.

**Tech Stack:** Python, pytest, existing evidence manifest/report modules.

---

### Task 1: Establish Baseline

**Files:**
- Read: `analysis/evidence_report.py`
- Read: `tests/test_evidence_*.py`

- [x] Run `python -m pytest --collect-only -q tests/test_evidence_manifest.py tests/test_evidence_report_manifest_shape.py tests/test_evidence_trace_report.py tests/test_evidence_wrapper_report.py tests/test_evidence_replay_report.py tests/test_evidence_artifacts.py tests/test_evidence_consistency.py tests/test_evidence_contract_report.py tests/test_evidence_contracts.py tests/test_evidence_manifest_checks.py tests/test_evidence_manifest_generation.py` and record the count: 80 tests across the listed files in the current workspace.
- [x] Search for imports of `_recovery_diagnostics` or `_multi_signal_window_diagnostics` from `analysis.evidence_report`. No active code or tests import those helpers from `analysis.evidence_report`; the direct tests now use `analysis.evidence_consistency`.

### Task 2: Refactor Failure Summary Printing

**Files:**
- Modify: `analysis/evidence_report.py`

- [x] Add `_fail(studies_count: int, **counts: int) -> bool` that prints `artifact_check failed studies=<n> key=value ...` and returns `False`.
- [x] Add `_print_errors(errors: list[str]) -> None` for the repeated `for error in errors: print(error)` loops.
- [x] Replace repeated failure-summary blocks in `main(...)` with `_print_errors(...)` plus `_fail(...)` without changing the emitted strings or phase order.
- [x] Keep artifact identity errors printed before later validation phases, preserving existing output ordering and late failure behavior.

### Task 3: Verify Behavior

**Files:**
- No production semantics expected.

- [x] Run `python -m pytest tests/test_evidence_manifest.py tests/test_evidence_report_manifest_shape.py tests/test_evidence_trace_report.py tests/test_evidence_wrapper_report.py tests/test_evidence_replay_report.py tests/test_evidence_contract_report.py -q`: 53 passed.
- [x] Run the extracted evidence group: 29 passed.
- [x] Run `python -m analysis.evidence_report` and confirm output includes `artifact_check ok studies=3 files=8`.
- [x] Run `python -m scripts.review_authority_lint`.
- [x] Run `python -m pytest tests/test_quality_gate_counts.py -q`: passed.

### Task 4: Ledger Check

**Files:**
- Modify if stale: `wiki/review-backlog.md`
- Modify if stale: `docs/opus-review/OPUS_REVIEW_PACKET.md`

- [x] If current ledgers still describe report-orchestrator cleanup as remaining, update them to say the small cleanup has landed and remaining work is future review-ledger hygiene. Current ledgers already record that state, including `docs/opus-review/OPUS_REVIEW_PACKET.md`.
