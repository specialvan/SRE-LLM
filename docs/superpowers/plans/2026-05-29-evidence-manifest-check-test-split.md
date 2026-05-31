# Evidence Manifest Check Test Split Implementation Plan

> Historical planning artifact; it is not the current handoff.
> Opus review should start from `docs/opus-review/HANDOFF.md`, then verify
> live status in `wiki/review-backlog.md`,
> `docs/codex-review/OPEN_RISKS.md`, and
> `docs/codex-review/QUALITY_GATES.md`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move direct manifest-check and consistency-helper unit tests out of the oversized evidence report-path test file.

**Architecture:** Keep CLI/report behavior tests in `tests/test_evidence_manifest.py`. Move direct `analysis.evidence_manifest_checks` helper coverage to `tests/test_evidence_manifest_checks.py` and direct `analysis.evidence_consistency` helper coverage to `tests/test_evidence_consistency.py`.

**Tech Stack:** Python, pytest, JSON helper assertions.

---

### Task 1: Establish Baseline

**Files:**
- Read: `tests/test_evidence_manifest.py`
- Read: `tests/test_evidence_manifest_checks.py`
- Read: `tests/test_evidence_consistency.py`

- [x] Run `python -m pytest --collect-only -q tests/test_evidence_manifest.py tests/test_evidence_manifest_checks.py tests/test_evidence_consistency.py` and record the per-file counts: `tests/test_evidence_manifest.py: 6`, `tests/test_evidence_manifest_checks.py: 4`, `tests/test_evidence_consistency.py: 5`.
- [x] Confirm `tests/test_evidence_manifest.py` no longer contains the direct helper tests targeted by this split; those checks now live in the focused helper test files.

### Task 2: Move Direct Helper Tests

**Files:**
- Modify: `tests/test_evidence_manifest.py`
- Modify: `tests/test_evidence_manifest_checks.py`
- Modify: `tests/test_evidence_consistency.py`

- [x] Move `test_evidence_report_accepts_uppercase_sha256_shape` to `tests/test_evidence_manifest_checks.py` and rename it to `test_is_sha256_accepts_uppercase_hex`.
- [x] Move `test_evidence_report_unrecovered_window_uses_strict_json_null` to `tests/test_evidence_consistency.py` and call `evidence_consistency._recovery_diagnostics` directly.
- [x] Move `test_evidence_report_unrecovered_multi_signal_window_uses_strict_json_null` to `tests/test_evidence_consistency.py` and call `evidence_consistency._multi_signal_window_diagnostics` directly.
- [x] Remove the stale `evidence_manifest_checks` import from `tests/test_evidence_manifest.py` if no longer used.

### Task 3: Verify Equivalence

**Files:**
- No production edits expected.

- [x] Run `python -m pytest --collect-only -q tests/test_evidence_manifest.py tests/test_evidence_manifest_checks.py tests/test_evidence_consistency.py` and confirm the current combined count is 15.
- [x] Run `python -m pytest tests/test_evidence_manifest.py tests/test_evidence_manifest_checks.py tests/test_evidence_consistency.py -q`: 15 passed.
- [x] Run `python -m analysis.evidence_report`: `artifact_check ok studies=3 files=8`.

### Task 4: Ledger Check

**Files:**
- Read/modify if stale: `wiki/review-backlog.md`
- Read/modify if stale: `docs/opus-review/OPUS_REVIEW_PACKET.md`

- [x] If the ledgers still describe all manifest-file splitting as future work, update them to say B2 also moved manifest-check and consistency-helper direct tests into focused files. Current ledgers already describe `tests/test_evidence_manifest_checks.py` and `tests/test_evidence_consistency.py` ownership.
