# Evidence Replay Artifact Report Test Split Implementation Plan

> Historical planning artifact; it is not the current handoff.
> Opus review should start from `docs/opus-review/HANDOFF.md`, then verify
> live status in `wiki/review-backlog.md`,
> `docs/codex-review/OPEN_RISKS.md`, and
> `docs/codex-review/QUALITY_GATES.md`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move S12 replay trace and fixture artifact report-path tests out of the oversized manifest report test file.

**Architecture:** Keep generic manifest-shape and cross-study artifact-path rejection tests in `tests/test_evidence_manifest.py`. Expand `tests/test_evidence_replay_report.py` so it owns reviewer-facing S12 replay report behavior for both diagnostics JSON and replay trace/fixture JSONL artifacts. Production modules remain unchanged.

**Tech Stack:** Python, pytest, JSON/JSONL temporary artifacts, `analysis.evidence_manifest`, `analysis.evidence_report`.

---

### Task 1: Establish Boundary

**Files:**
- Read: `tests/test_evidence_manifest.py`
- Read: `tests/test_evidence_replay_report.py`

- [x] Run `python -m pytest --collect-only -q tests/test_evidence_manifest.py tests/test_evidence_replay_report.py` and record the combined count. Current ownership later split S12 trace/fixture artifact checks into `tests/test_evidence_replay_artifacts_report.py`; the current manifest/replay/report-artifact group collects 39 tests (`6 + 22 + 11`).
- [x] Confirm the S12 trace/fixture artifact report-path block starts at `test_event_evidence_report_rejects_inconsistent_artifact_content` and ends at `test_event_evidence_report_rejects_conflicting_s12_fixture_expected_fields`; the current block lives in `tests/test_evidence_replay_artifacts_report.py`.
- [x] Keep `test_event_evidence_report_rejects_schema_invalid_event_artifact` out of S12 replay artifact ownership because it validates S10 trace schema report behavior; the current owner is `tests/test_evidence_trace_report.py`.
- [x] Move `test_event_evidence_report_rejects_bounded_residual_without_sufficiency_fields` with the S12 block because it validates S12 replay trace runtime-event schema report behavior; the current owner is `tests/test_evidence_replay_artifacts_report.py`.

### Task 2: Move S12 Replay Artifact Report Tests

**Files:**
- Modify: `tests/test_evidence_manifest.py`
- Modify: `tests/test_evidence_replay_report.py`

- [x] Move the S12 replay trace/fixture artifact report-path tests out of `tests/test_evidence_manifest.py`; a follow-on split now owns them in `tests/test_evidence_replay_artifacts_report.py` while `tests/test_evidence_replay_report.py` owns diagnostics field report paths.
- [x] Remove those moved tests from `tests/test_evidence_manifest.py`.
- [x] Leave the remaining manifest file imports unchanged unless they become unused.

### Task 3: Update Current Ledgers

**Files:**
- Modify: `docs/codex-review/QUALITY_GATES.md`
- Modify: `wiki/review-backlog.md`
- Modify: `docs/opus-review/OPUS_REVIEW_PACKET.md`

- [x] Update test ownership wording so S12 replay diagnostics field paths are documented under `tests/test_evidence_replay_report.py` and S12 replay trace/fixture artifact paths are documented under `tests/test_evidence_replay_artifacts_report.py`.
- [x] Update manifest ownership wording so `tests/test_evidence_manifest.py` no longer claims S12 replay trace/fixture artifact report paths.

### Task 4: Verify Equivalence

**Files:**
- No production edits expected.

- [x] Run `python -m pytest --collect-only -q tests/test_evidence_manifest.py tests/test_evidence_replay_report.py tests/test_evidence_replay_artifacts_report.py tests/test_evidence_wrapper_report.py` and confirm the current combined count is 47.
- [x] Run `python -m pytest tests/test_evidence_replay_report.py tests/test_evidence_replay_artifacts_report.py tests/test_evidence_manifest.py tests/test_evidence_wrapper_report.py -q`: 47 passed.
- [x] Run `python -m pytest tests/test_evidence_manifest.py tests/test_evidence_replay_report.py tests/test_evidence_wrapper_report.py -q`; covered by the 47-test group above with the current S12 artifact split included.
- [x] Run `python -m pytest tests/test_evidence_manifest.py tests/test_evidence_wrapper_report.py tests/test_evidence_replay_report.py tests/test_evidence_artifacts.py tests/test_evidence_manifest_generation.py tests/test_evidence_manifest_checks.py tests/test_evidence_consistency.py tests/test_evidence_contracts.py tests/test_evidence_contract_report.py -q`; covered by the focused evidence split groups run in this continuation, including the current replay artifact split.
- [x] Run `python -m analysis.evidence_report` and confirm output includes `artifact_check ok studies=3 files=8`.
- [x] Run `python -m scripts.review_authority_lint` and confirm output includes `review authority order ok`.
