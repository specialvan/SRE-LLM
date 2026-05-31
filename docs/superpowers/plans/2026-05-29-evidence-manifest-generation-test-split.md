# Evidence Manifest Generation Test Split Implementation Plan

> Historical planning artifact; it is not the current handoff.
> Opus review should start from `docs/opus-review/HANDOFF.md`, then verify
> live status in `wiki/review-backlog.md`,
> `docs/codex-review/OPEN_RISKS.md`, and
> `docs/codex-review/QUALITY_GATES.md`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move direct `analysis.evidence_manifest` generation and manifest-documentation tests out of the oversized evidence report-path test file.

**Architecture:** Keep `tests/test_evidence_manifest.py` focused on `analysis.evidence_report.main(...)` report-path behavior. Create `tests/test_evidence_manifest_generation.py` for manifest writer guards, generated artifact shape, artifact byte metadata, artifact-global isolation, manifest documentation parity, and current review-doc byte-identity coverage.

**Tech Stack:** Python, pytest, JSON/JSONL temporary artifacts, Markdown table parsing.

---

### Task 1: Establish Baseline

**Files:**
- Read: `tests/test_evidence_manifest.py`

- [x] Run `python -m pytest --collect-only -q tests/test_evidence_manifest.py` and record the current residual count: 6 report-path tests.
- [x] Identify the generation/documentation tests at the top of `tests/test_evidence_manifest.py` before the first `evidence_report.main(...)` report-path test; they are now owned by `tests/test_evidence_manifest_generation.py`.

### Task 2: Move Generation Tests

**Files:**
- Create: `tests/test_evidence_manifest_generation.py`
- Modify: `tests/test_evidence_manifest.py`

- [x] Move `_resolve_manifest_artifact`, `_parse_markdown_table_rows`, and any imports used only by generation/doc tests to `tests/test_evidence_manifest_generation.py`.
- [x] Move `test_evidence_manifest_json_writers_reject_non_standard_floats`, `test_event_evidence_manifest_exports_stable_review_artifacts`, `test_event_evidence_manifest_exports_artifact_byte_metadata`, `test_event_evidence_manifest_does_not_patch_artifact_globals`, `test_event_evidence_manifest_doc_matches_generated_manifest`, and `test_current_review_docs_describe_manifest_byte_identity_validation` to `tests/test_evidence_manifest_generation.py`.
- [x] Keep `_sha256`, `_replace_first_s10_trace_event`, `_fake_artifact_metadata`, `_fill_fake_artifact_metadata`, and all `evidence_report.main(...)` tests in `tests/test_evidence_manifest.py`.

### Task 3: Verify Equivalence

**Files:**
- No production edits expected.

- [x] Run `python -m pytest --collect-only -q tests/test_evidence_manifest.py tests/test_evidence_manifest_generation.py` and confirm the current combined count is 16.
- [x] Run `python -m pytest tests/test_evidence_manifest.py tests/test_evidence_manifest_generation.py -q`: 16 passed.
- [x] Run `python -m analysis.evidence_report`: `artifact_check ok studies=3 files=8`.

### Task 4: Ledger Check

**Files:**
- Modify if stale: `wiki/review-backlog.md`
- Modify if stale: `docs/opus-review/OPUS_REVIEW_PACKET.md`

- [x] Update B2 wording if the ledgers still imply all manifest generation/doc tests live in `tests/test_evidence_manifest.py`. Current ledgers already describe `tests/test_evidence_manifest_generation.py` ownership.
