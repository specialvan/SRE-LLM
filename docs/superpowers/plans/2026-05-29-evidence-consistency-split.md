# Evidence Consistency Split Implementation Plan

> Historical planning artifact; it is not the current handoff.
> Opus review should start from `docs/opus-review/HANDOFF.md`, then verify
> live status in `wiki/review-backlog.md`,
> `docs/codex-review/OPEN_RISKS.md`, and
> `docs/codex-review/QUALITY_GATES.md`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract S10/S11/S12 study consistency checks from `analysis.evidence_report` into a focused module with direct tests.

**Architecture:** `analysis.evidence_report` remains the CLI and orchestration surface. New `analysis.evidence_consistency` owns study artifact consistency checks and selected diagnostic helpers. Existing artifact, manifest-shape, and contract modules remain unchanged.

**Tech Stack:** Python 3, pytest, JSON/JSONL file artifacts, existing `analysis.evidence_manifest` fixture generation.

---

### Task 1: Add Direct Consistency Module Tests

**Files:**
- Create: `tests/test_evidence_consistency.py`

- [x] **Step 1: Write failing tests**

Add tests that import `analysis.evidence_consistency`, generate a temporary manifest with `analysis.evidence_manifest.main(artifacts_dir=tmp_path)`, and assert generated study entries are clean plus representative S10/S12 drift errors are reported directly.

- [x] **Step 2: Verify red**

Run: `python -m pytest tests/test_evidence_consistency.py -q`

Expected: fail with `ImportError` because `analysis.evidence_consistency` does not exist yet. Historical red state is no longer reproducible in the current workspace because the module now exists; current evidence is the passing direct test file.

### Task 2: Extract Study Consistency Implementation

**Files:**
- Create: `analysis/evidence_consistency.py`
- Modify: `analysis/evidence_report.py`

- [x] **Step 1: Move implementation**

Move the study consistency helpers from `analysis.evidence_report` into `analysis.evidence_consistency`, exposing `study_consistency_errors(entry, root)`.

- [x] **Step 2: Wire report orchestrator**

In `analysis.evidence_report`, import `study_consistency_errors` and call it where `_consistency_errors` was used. Keep compatibility aliases for `_recovery_diagnostics` and `_multi_signal_window_diagnostics` if existing tests still import them from `evidence_report`.

- [x] **Step 3: Verify green**

Run: `python -m pytest tests/test_evidence_consistency.py -q`

Expected: pass. Current verification: `tests/test_evidence_consistency.py` is part of the 25-test focused consistency group that passed.

### Task 3: Regression Verification

**Files:**
- No production edits expected.

- [x] **Step 1: Run focused evidence tests**

Run: `python -m pytest tests/test_evidence_consistency.py tests/test_evidence_manifest.py tests/test_evidence_artifacts.py tests/test_evidence_contracts.py tests/test_evidence_manifest_checks.py -q`

Expected: pass. Current verification: 25 passed for `tests/test_evidence_consistency.py tests/test_evidence_manifest.py tests/test_evidence_artifacts.py tests/test_evidence_contracts.py tests/test_evidence_manifest_checks.py`.

- [x] **Step 2: Run report command**

Run: `python -m analysis.evidence_report`

Expected: output includes `artifact_check ok studies=3 files=8`. Current verification produced that output.

### Task 4: Ledger Update If Needed

**Files:**
- Modify: `wiki/review-backlog.md`
- Modify: `docs/codex-review/OPEN_RISKS.md` only if the live risk/follow-up wording changes.

- [x] **Step 1: Update only current ledgers that mention the split**

Record that study consistency checks now live in `analysis.evidence_consistency` with direct tests, if current-facing ledgers still describe this as pending. Current ledgers already record `analysis.evidence_consistency` and `tests/test_evidence_consistency.py` as owners.

- [x] **Step 2: Verify docs/lint surface**

Run: `python -m scripts.review_authority_lint`

Expected: pass. Current verification: `python -m scripts.review_authority_lint` reported `review authority order ok`.
