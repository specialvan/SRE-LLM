# Evidence Contract Report Follow-On Split Implementation Plan

> Historical planning artifact; it is not the current handoff.
> Opus review should start from `docs/opus-review/HANDOFF.md`, then verify
> live status in `wiki/review-backlog.md`,
> `docs/codex-review/OPEN_RISKS.md`, and
> `docs/codex-review/QUALITY_GATES.md`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce `tests/test_evidence_contract_report.py` by splitting stack-contract report-path coverage into focused files without changing collected test count or report behavior.

**Architecture:** Keep stack-contract scope, route, and stage-interface artifact drift checks in `tests/test_evidence_contract_report.py`. Move fallback field/map drift checks, S10 trace contract-routing checks, and split-boundary/event-routing checks into separate pytest modules that still exercise `analysis.evidence_report.main(...)` through generated manifest artifacts.

**Tech Stack:** Python, pytest, JSON/JSONL temporary artifacts, `analysis.evidence_manifest`, `analysis.evidence_report`.

---

### Task 1: Baseline

**Files:**
- Read: `tests/test_evidence_contract_report.py`

- [x] Run `python -m pytest --collect-only -q tests/test_evidence_contract_report.py` before the split.
- [x] Record that the current focused split group still collects 23 report-path tests after the split: `7 + 5 + 8 + 3` across contract, fallback, trace, and boundary files.

### Task 2: Split Test Ownership

**Files:**
- Modify: `tests/test_evidence_contract_report.py`
- Create: `tests/test_evidence_contract_fallback_report.py`
- Create: `tests/test_evidence_contract_trace_report.py`
- Create: `tests/test_evidence_contract_boundary_report.py`

- [x] Keep production claim, event kind, route key/value, stage-entry, and stage-interface tests in `tests/test_evidence_contract_report.py`.
- [x] Move malformed fallback field and fallback action/mode map drift tests to `tests/test_evidence_contract_fallback_report.py`.
- [x] Move trace fallback, adapter-family, fault-family, exception-cause, and recoverability routing tests to `tests/test_evidence_contract_trace_report.py` with its local `_sha256` and `_replace_first_s10_trace_event` helpers.
- [x] Move split-boundary and trace-event-allowed routing tests to `tests/test_evidence_contract_boundary_report.py`.

### Task 3: Update Review Ledgers

**Files:**
- Modify: `docs/codex-review/QUALITY_GATES.md`
- Modify: `docs/codex-review/ENGINEERING_PACKET.md`
- Modify: `docs/opus-review/HANDOFF.md`
- Modify: `docs/opus-review/OPUS_REVIEW_PACKET.md`
- Modify: `wiki/review-backlog.md`
- Modify: `tests/test_quality_gate_counts.py`

- [x] Replace single-file stack-contract report wording with the four split report files.
- [x] Update targeted evidence commands to include all split files.
- [x] Update guard tests so docs fail if the split files disappear from current review packets.

### Task 4: Verify Equivalence

**Files:**
- No production edits expected.

- [x] Run focused collect for the four contract-report split files and confirm 23 collected.
- [x] Run focused pytest for the four contract-report split files.
- [x] Run the expanded evidence report group.
- [x] Run `python -m pytest tests/test_quality_gate_counts.py -q`.
- [x] Run `python -m scripts.review_authority_lint`.
- [x] Run `python -m analysis.evidence_report`.
- [x] Run `python -m scripts.quality_gate_counts --check --skip-expensive`.
- [x] Run `python -m pytest --collect-only -q tests` and confirm 624 collected in the then-current workspace before the plan-boundary guard was added.
- [x] Run `python -m pytest tests -q` and confirm the then-current 624-test suite exits cleanly before the plan-boundary guard was added.
