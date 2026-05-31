# Evidence Artifact Test Split Implementation Plan

> Historical planning artifact; it is not the current handoff.
> Opus review should start from `docs/opus-review/HANDOFF.md`, then verify
> live status in `wiki/review-backlog.md`,
> `docs/codex-review/OPEN_RISKS.md`, and
> `docs/codex-review/QUALITY_GATES.md`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move direct `analysis.evidence_artifacts` unit tests out of the oversized evidence manifest test file.

**Architecture:** Keep report-path tests in `tests/test_evidence_manifest.py`; put direct artifact validator tests in `tests/test_evidence_artifacts.py`. Production modules remain unchanged.

**Tech Stack:** Python, pytest, JSON/JSONL temporary files.

---

### Task 1: Establish Baseline

**Files:**
- Read: `tests/test_evidence_manifest.py`
- Read: `tests/test_evidence_artifacts.py`

- [x] Run `python -m pytest --collect-only -q tests/test_evidence_manifest.py tests/test_evidence_artifacts.py` and record the combined count: 14 tests in the current workspace (`6 + 8`).

### Task 2: Move Direct Artifact Validator Tests

**Files:**
- Modify: `tests/test_evidence_manifest.py`
- Modify: `tests/test_evidence_artifacts.py`

- [x] Move direct tests for `_s10_trace_shape_errors`, `_invalid_jsonl_errors`, `_s12_fixture_shape_errors`, and `schema_invalid_event_errors` into `tests/test_evidence_artifacts.py`.
- [x] Leave report CLI tests that call `evidence_report.main(...)` in `tests/test_evidence_manifest.py`.

### Task 3: Verify Equivalence

**Files:**
- No production edits expected.

- [x] Run `python -m pytest --collect-only -q tests/test_evidence_manifest.py tests/test_evidence_artifacts.py` and confirm the current count is 14.
- [x] Run `python -m pytest tests/test_evidence_artifacts.py tests/test_evidence_manifest.py -q`: 14 passed.
- [x] Run `python -m analysis.evidence_report`: `artifact_check ok studies=3 files=8`.

### Task 4: Update Ledgers If Needed

**Files:**
- Modify: `wiki/review-backlog.md`
- Modify: `docs/opus-review/OPUS_REVIEW_PACKET.md`

- [x] Record this B2 progress if the current ledgers still describe all of `tests/test_evidence_manifest.py` splitting as future work. Current ledgers already describe `tests/test_evidence_artifacts.py` as the direct artifact-validator owner.
