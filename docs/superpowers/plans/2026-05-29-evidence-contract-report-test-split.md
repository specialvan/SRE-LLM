# Evidence Contract Report Test Split Implementation Plan

> Historical planning artifact; it is not the current handoff.
> Opus review should start from `docs/opus-review/HANDOFF.md`, then verify
> live status in `wiki/review-backlog.md`,
> `docs/codex-review/OPEN_RISKS.md`, and
> `docs/codex-review/QUALITY_GATES.md`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move stack-contract report-path tests out of the oversized evidence manifest report test file.

**Architecture:** Keep direct `analysis.evidence_contracts` unit tests in `tests/test_evidence_contracts.py`. Create `tests/test_evidence_contract_report.py` for `analysis.evidence_report.main(...)` paths that mutate `sre_stack_data_contract.json` or inject contract-routing failures into S10 trace artifacts.

**Tech Stack:** Python, pytest, JSON/JSONL temporary artifacts.

---

### Task 1: Establish Baseline

**Files:**
- Read: `tests/test_evidence_manifest.py`
- Read: `tests/test_evidence_contracts.py`

- [x] Run `python -m pytest --collect-only -q tests/test_evidence_manifest.py tests/test_evidence_contracts.py` and record the current combined count: 8 tests (`6 + 2`) after the report-path split.
- [x] Confirm the report-path contract block starts at `test_event_evidence_report_rejects_stack_contract_production_claim` and continues through `test_event_evidence_report_rejects_trace_event_not_allowed_by_stack_contract`. Current ownership is split across `tests/test_evidence_contract_report.py` and follow-on fallback/trace/boundary report files.

### Task 2: Move Contract Report Tests

**Files:**
- Create: `tests/test_evidence_contract_report.py`
- Modify: `tests/test_evidence_manifest.py`

- [x] Copy `_sha256` and `_replace_first_s10_trace_event` into the stack-contract report surface; after the follow-on split, those helpers live in `tests/test_evidence_contract_trace_report.py`.
- [x] Move all stack-contract `evidence_report.main(...)` tests from the bottom block into the stack-contract report test surface.
- [x] Remove `_sha256` and `_replace_first_s10_trace_event` from `tests/test_evidence_manifest.py` if no longer referenced there.
- [x] Keep generic manifest contract-shape tests, such as missing contract fields and artifact key checks, in manifest-shape/report artifact files because they validate manifest shape rather than stack-contract artifact semantics.

### Task 3: Verify Equivalence

**Files:**
- No production edits expected.

- [x] Run `python -m pytest --collect-only -q tests/test_evidence_manifest.py tests/test_evidence_contracts.py tests/test_evidence_contract_report.py tests/test_evidence_contract_fallback_report.py tests/test_evidence_contract_trace_report.py tests/test_evidence_contract_boundary_report.py` and confirm the current combined stack-contract report surface collects 31 tests.
- [x] Run `python -m pytest tests/test_evidence_manifest.py tests/test_evidence_contracts.py tests/test_evidence_contract_report.py tests/test_evidence_contract_fallback_report.py tests/test_evidence_contract_trace_report.py tests/test_evidence_contract_boundary_report.py -q`: 31 passed.
- [x] Run `python -m analysis.evidence_report`: `artifact_check ok studies=3 files=8`.

### Task 4: Ledger Check

**Files:**
- Modify if stale: `wiki/review-backlog.md`
- Modify if stale: `docs/opus-review/OPUS_REVIEW_PACKET.md`
- Modify if stale: `docs/codex-review/QUALITY_GATES.md`

- [x] Update B2 wording if current-facing docs still imply stack-contract report-path tests live only in `tests/test_evidence_manifest.py`. Current ledgers already describe the split contract report files.
