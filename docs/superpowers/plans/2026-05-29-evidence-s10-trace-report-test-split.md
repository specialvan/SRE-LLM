# Evidence S10 Trace Report Test Split Implementation Plan

> Historical planning artifact; it is not the current handoff.
> Opus review should start from `docs/opus-review/HANDOFF.md`, then verify
> live status in `wiki/review-backlog.md`,
> `docs/codex-review/OPEN_RISKS.md`, and
> `docs/codex-review/QUALITY_GATES.md`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move S10 trace artifact report-path tests out of the generic evidence manifest report test file.

**Architecture:** Keep manifest-shape, artifact path/metadata/extension, contract-shape, and generic report smoke tests in `tests/test_evidence_manifest.py`. Create `tests/test_evidence_trace_report.py` for reviewer-facing S10 full/sample trace consistency and schema rejection paths. Production modules remain unchanged.

**Tech Stack:** Python, pytest, JSON/JSONL temporary artifacts, `analysis.evidence_manifest`, `analysis.evidence_report`.

---

### Task 1: Establish Boundary

**Files:**
- Read: `tests/test_evidence_manifest.py`

- [x] Run `python -m pytest --collect-only -q tests/test_evidence_manifest.py` and record the current residual count: 6 report-path tests.
- [x] Move the S10 trace report-path tests from `test_event_evidence_report_rejects_s10_background_fraction_mismatch` through `test_event_evidence_report_rejects_s10_trace_time_mismatch`.
- [x] Also move `test_event_evidence_report_rejects_schema_invalid_event_artifact` because it validates S10 trace runtime-event schema rejection through the report path.
- [x] Keep manifest-field tests that happen to mutate the S10 study entry in `tests/test_evidence_manifest.py` because they validate manifest shape, not S10 trace artifacts.

### Task 2: Move S10 Trace Report Tests

**Files:**
- Create: `tests/test_evidence_trace_report.py`
- Modify: `tests/test_evidence_manifest.py`

- [x] Copy the S10 trace report-path tests into `tests/test_evidence_trace_report.py` with only the needed imports: `json`, `pytest`, `evidence_manifest`, and `evidence_report`.
- [x] Remove the moved tests from `tests/test_evidence_manifest.py`.
- [x] Leave `pytest` imported in `tests/test_evidence_manifest.py` because malformed/missing manifest rejection tests still use `pytest.fail`.

### Task 3: Update Current Ledgers

**Files:**
- Modify: `docs/codex-review/QUALITY_GATES.md`
- Modify: `wiki/review-backlog.md`
- Modify: `docs/opus-review/OPUS_REVIEW_PACKET.md`

- [x] Add `tests/test_evidence_trace_report.py` to the targeted gate ownership list.
- [x] Update `tests/test_evidence_manifest.py` wording so it no longer claims S10 trace artifact/schema report paths.

### Task 4: Verify Equivalence

**Files:**
- No production edits expected.

- [x] Run `python -m pytest --collect-only -q tests/test_evidence_manifest.py tests/test_evidence_trace_report.py` and confirm the current combined count is 13.
- [x] Run `python -m pytest tests/test_evidence_trace_report.py -q`: 7 passed.
- [x] Run the extracted evidence group including `tests/test_evidence_trace_report.py`: 43 passed.
- [x] Run `python -m analysis.evidence_report` and confirm output includes `artifact_check ok studies=3 files=8`.
- [x] Run `python -m scripts.review_authority_lint` and confirm output includes `review authority order ok`.
