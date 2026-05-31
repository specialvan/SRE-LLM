# Evidence Report Manifest Shape Test Split Implementation Plan

> Historical planning artifact; it is not the current handoff.
> Opus review should start from `docs/opus-review/HANDOFF.md`, then verify
> live status in `wiki/review-backlog.md`,
> `docs/codex-review/OPEN_RISKS.md`, and
> `docs/codex-review/QUALITY_GATES.md`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move generic invalid-manifest reviewer report tests out of the residual evidence manifest report test file.

**Architecture:** Keep `tests/test_evidence_manifest.py` as a small report smoke and artifact presence/metadata/byte-identity surface. Create `tests/test_evidence_report_manifest_shape.py` for top-level manifest JSON failures, study/contract field shape failures, artifact path portability/key/extension validation, and manifest field range/type/value rejection. Production modules remain unchanged.

**Tech Stack:** Python, pytest, JSON temporary manifests, `analysis.evidence_manifest`, `analysis.evidence_report`.

---

### Task 1: Establish Boundary

**Files:**
- Read: `tests/test_evidence_manifest.py`

- [x] Run `python -m pytest --collect-only -q tests/test_evidence_manifest.py` and record the current residual count: 6 report-path tests.
- [x] Keep `test_event_evidence_report_validates_manifest_artifacts`, artifact byte identity, missing artifact metadata, artifact metadata key mismatch, malformed artifact metadata, and missing artifact tests in `tests/test_evidence_manifest.py`.
- [x] Move the remaining invalid-manifest shape/path/key/extension tests from `test_event_evidence_report_rejects_missing_top_level_studies` through `test_event_evidence_report_rejects_wrong_contract_artifact_extension`.

### Task 2: Move Manifest Shape Report Tests

**Files:**
- Create: `tests/test_evidence_report_manifest_shape.py`
- Modify: `tests/test_evidence_manifest.py`

- [x] Copy the moved tests into `tests/test_evidence_report_manifest_shape.py` with imports for `json`, `pytest`, `evidence_manifest`, and `evidence_report`.
- [x] Remove those tests from `tests/test_evidence_manifest.py`.
- [x] Remove the `pytest` import from `tests/test_evidence_manifest.py` if it is no longer referenced there.

### Task 3: Update Current Ledgers

**Files:**
- Modify: `docs/codex-review/QUALITY_GATES.md`
- Modify: `wiki/review-backlog.md`
- Modify: `docs/opus-review/OPUS_REVIEW_PACKET.md`

- [x] Add `tests/test_evidence_report_manifest_shape.py` to the targeted gate ownership list.
- [x] Update `tests/test_evidence_manifest.py` wording so it is described as report smoke plus artifact identity/presence/metadata checks.

### Task 4: Verify Equivalence

**Files:**
- No production edits expected.

- [x] Run `python -m pytest --collect-only -q tests/test_evidence_manifest.py tests/test_evidence_report_manifest_shape.py` and confirm the current combined count is 9.
- [x] Run `python -m pytest tests/test_evidence_report_manifest_shape.py tests/test_evidence_manifest.py -q`: 9 passed.
- [x] Run the extracted evidence group including `tests/test_evidence_report_manifest_shape.py`: 43 passed.
- [x] Run `python -m analysis.evidence_report` and confirm output includes `artifact_check ok studies=3 files=8`.
- [x] Run `python -m scripts.review_authority_lint` and confirm output includes `review authority order ok`.
