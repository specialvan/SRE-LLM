# Control Center Browser Manifest Test Split Implementation Plan

> Historical planning artifact; it is not the current handoff.
> Opus review should start from `docs/opus-review/HANDOFF.md`, then verify
> live status in `wiki/review-backlog.md`,
> `docs/codex-review/OPEN_RISKS.md`, and
> `docs/codex-review/QUALITY_GATES.md`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce the oversized `tests/test_control_center_browser_smoke.py` file by moving browser evidence manifest/report tests into focused modules without changing production behavior or total collected test count.

**Architecture:** Keep browser launch, live fetch, DOM assertion, and CLI path tests in `tests/test_control_center_browser_smoke.py`. Move normal manifest write/verify tests to `tests/test_control_center_browser_manifest.py`, error/frontend-error manifest tests to `tests/test_control_center_browser_error_manifest.py`, and report-summary/replay CLI tests to `tests/test_control_center_browser_report.py`. Duplicate only tiny local helpers (`_png_bytes`, `_blank_png_bytes`, `_valid_dom_for_payload`) where needed.

**Tech Stack:** Python, pytest, temporary JSON/PNG/HTML artifacts, `scripts.control_center_browser_smoke`.

---

### Task 1: Baseline

**Files:**
- Read: `tests/test_control_center_browser_smoke.py`

- [x] Run browser collect during the split and record that the completed browser group is preserved at 69 tests across smoke, DOM, normal manifest, error manifest, and report files.
- [x] Identify the manifest block from `test_write_dom_dump_normalizes_line_endings` through `test_control_center_browser_smoke_writes_json_report_after_replay`.

### Task 2: Split Normal Manifest Tests

**Files:**
- Modify: `tests/test_control_center_browser_smoke.py`
- Create: `tests/test_control_center_browser_manifest.py`

- [x] Move tests for `write_dom_dump`, `write_evidence_manifest`, and `verify_evidence_manifest` normal-manifest paths into the new normal manifest file.
- [x] Copy `_png_bytes`, `_blank_png_bytes`, and `_valid_dom_for_payload` into the new file if needed.

### Task 3: Split Error Manifest Tests

**Files:**
- Modify: `tests/test_control_center_browser_smoke.py`
- Create: `tests/test_control_center_browser_error_manifest.py`

- [x] Move tests for `write_error_evidence_manifest`, `verify_error_evidence_manifest`, `write_frontend_error_evidence_manifest`, and `verify_frontend_error_evidence_manifest` into the new error manifest file.
- [x] Copy only the PNG helper needed by the moved tests.

### Task 4: Split Report/Replay Tests

**Files:**
- Modify: `tests/test_control_center_browser_smoke.py`
- Create: `tests/test_control_center_browser_report.py`

- [x] Move manifest replay CLI tests and evidence-report summary tests into the new report file.
- [x] Keep browser execution path tests in the original smoke file.

### Task 5: Ledgers and Guards

**Files:**
- Modify if stale: `docs/codex-review/ENGINEERING_PACKET.md`
- Modify if stale: `docs/codex-review/QUALITY_GATES.md`
- Modify if stale: `docs/opus-review/OPUS_REVIEW_PACKET.md`
- Modify if stale: `docs/opus-review/HANDOFF.md`
- Modify if stale: `tests/test_quality_gate_counts.py`

- [x] Update current-facing merge-scope and targeted-gate ownership docs if they mention only `tests/test_control_center_browser_smoke.py` for browser evidence coverage.
- [x] Add guard assertions for the new split files if current guard tests enumerate merge-scope test files.

### Task 6: Verify

**Files:**
- No production edits expected.

- [x] Run focused collect for smoke plus normal/error/report split files and confirm 48 collected after the follow-on DOM split; the complete browser group including DOM remains 69.
- [x] Run focused pytest for the original plus three split files.
- [x] Run `python -m pytest tests/test_quality_gate_counts.py -q` if docs/guards changed.
- [x] Run `python -m scripts.quality_gate_counts --check --skip-expensive`.
- [x] Run `python -m pytest --collect-only -q tests` and confirm 624 collected in the then-current workspace before the plan-boundary guard was added.
- [x] Run `python -m pytest tests -q` with a 300 s timeout; the then-current 624-test suite exits cleanly before the plan-boundary guard was added.
