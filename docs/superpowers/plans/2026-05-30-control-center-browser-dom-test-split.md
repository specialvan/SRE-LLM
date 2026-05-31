# Control Center Browser DOM Test Split Implementation Plan

> Historical planning artifact; it is not the current handoff.
> Opus review should start from `docs/opus-review/HANDOFF.md`, then verify
> live status in `wiki/review-backlog.md`,
> `docs/codex-review/OPEN_RISKS.md`, and
> `docs/codex-review/QUALITY_GATES.md`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Further reduce `tests/test_control_center_browser_smoke.py` by moving control-center frontend DOM and payload assertion tests into a focused module without changing behavior or total collected test count.

**Architecture:** Keep browser launch, live fetch, API snapshot, system-browser execution, error-path CLI, and handoff documentation tests in `tests/test_control_center_browser_smoke.py`. Move static frontend interaction-hook checks, DOM assertion helper tests, backend/frontend error DOM checks, payload-aware DOM checks, and validator shape tests into `tests/test_control_center_browser_dom.py`. The new file imports `scripts.control_center_browser_smoke` directly and uses the existing helper APIs; no production code changes are expected.

**Tech Stack:** Python, pytest, temporary HTML strings, `scripts.control_center_browser_smoke`, `docs/control-center.html`.

---

### Task 1: Baseline

**Files:**
- Read: `tests/test_control_center_browser_smoke.py`

- [x] Run `python -m pytest --collect-only -q tests/test_control_center_browser_smoke.py` and record the current 46-test count.
- [x] Identify the DOM/frontend assertion block from `test_control_center_frontend_contains_smoke_interaction_hook` through `test_browser_smoke_validator_rejects_inconsistent_frontend_lengths`.

### Task 2: Move DOM Assertion Tests

**Files:**
- Modify: `tests/test_control_center_browser_smoke.py`
- Create: `tests/test_control_center_browser_dom.py`

- [x] Move the static frontend hook tests, DOM dump assertion tests, backend/frontend error DOM tests, payload-aware DOM tests, selected-tick tests, interaction-probe tests, and payload validator tests into `tests/test_control_center_browser_dom.py`.
- [x] Keep all browser execution and CLI tests in `tests/test_control_center_browser_smoke.py`.
- [x] Do not change production code.

### Task 3: Update Current Ledgers

**Files:**
- Modify: `docs/codex-review/QUALITY_GATES.md`
- Modify: `docs/codex-review/ENGINEERING_PACKET.md`
- Modify: `docs/opus-review/HANDOFF.md`
- Modify: `docs/opus-review/OPUS_REVIEW_PACKET.md`
- Modify: `wiki/review-backlog.md`
- Modify: `tests/test_quality_gate_counts.py`

- [x] Add `tests/test_control_center_browser_dom.py` beside the existing browser smoke/manifest/report split files.
- [x] Update descriptions so `test_control_center_browser_smoke.py` no longer appears to own DOM assertion coverage alone.

### Task 4: Verify

**Files:**
- No production edits expected.

- [x] Run focused collect for `test_control_center_browser_smoke.py` and `test_control_center_browser_dom.py`; confirm their combined count remains 46.
- [x] Run focused pytest for the smoke and DOM files.
- [x] Run focused browser group including manifest/error/report/dom/smoke files.
- [x] Run `python -m pytest tests/test_quality_gate_counts.py -q`.
- [x] Run `python -m scripts.quality_gate_counts --check --skip-expensive`.
- [x] Run `python -m pytest --collect-only -q tests` and confirm 624 collected in the then-current workspace before the plan-boundary guard was added.
- [x] Run `python -m pytest tests -q` with a 300 s timeout; the then-current 624-test suite exits cleanly before the plan-boundary guard was added.
