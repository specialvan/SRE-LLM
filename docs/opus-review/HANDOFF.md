# Opus Review Handoff

Date: 2026-05-31
Repository: `D:\workspace\SRE-LLM\spacex`
Branch: `spacex-session`

This is the current Opus re-review handoff. It is written as the first file an
external reviewer should read before inspecting the larger packet. Treat the
live ledgers as the source of truth before reading historical packets:

1. `wiki/review-backlog.md`
2. `docs/codex-review/OPEN_RISKS.md`
3. `docs/codex-review/QUALITY_GATES.md`
4. `docs/opus-review/OPUS_REVIEW_PACKET.md`
5. Historical packets under `claude-review/docs/` and `docs/opus-review/v1.0/`

The repository remains a public-material research reproduction. Synthetic
scenario evidence is review evidence, not a production or SpaceX-official
claim.

The returned `claude-review/docs/v2026-05-31/` packet is now historical review
input. It found M1 pytest-count documentation drift and M2 an incomplete
reviewer-side `quality_gate_counts` capture; the live status is the current
handoff, `QUALITY_GATES.md`, `wiki/review-backlog.md`, and fresh command output.

## Git Review Scope Snapshot

Opus should refresh this with
`git status --short --branch --untracked-files=all` before making a review
decision. The pre-submit local snapshot captured for this handoff was
`spacex-session...origin/spacex-session [ahead 93]` with a large intentionally
dirty review surface. If this handoff has already been committed, review the
new content-split commits in `origin/spacex-session..HEAD` and treat the
snapshot below as the pre-commit inventory that explains why those files belong
in scope.

Recommended git commands for the review setup:

```bash
git status --short --branch --untracked-files=all
git log --oneline --decorate -5
git log --reverse --oneline origin/spacex-session..HEAD
git diff --name-status
git ls-files --others --exclude-standard
git diff --check
```

- The tracked modified surface spans review docs, quality-gate scripts,
  evidence-report split helpers, generated evidence summaries, historical
  packet demotions, and targeted tests such as
  `tests/test_synthetic_evidence_boundaries.py` and
  `tests/test_quality_gate_counts.py`. Treat this as the current
  review packet scope, not as unrelated churn.
- Treat the dirty/untracked surface as review scope until a fresh reviewer
  export or merge deliberately includes or excludes each item.
- The untracked files are intentional review scope. They include the split
  evidence consistency helper `analysis/evidence_consistency.py`, Superpowers
  inventories `docs/superpowers/plans/README.md` and
  `docs/superpowers/specs/README.md`, dated plan/spec artifacts, split
  control-center tests such as `tests/test_control_center_browser_dom.py`, and
  split evidence report tests such as `tests/test_evidence_report_manifest_shape.py` and
  `tests/test_evidence_contract_boundary_report.py`.
- For any merge or external packet export, do not omit untracked split files;
  the synchronized quality gates and handoff claims depend on them.
- `git diff --check` may print LF-to-CRLF warnings on this Windows checkout;
  line-ending warnings are not review blockers when the command exits zero.
- unexpected files outside these categories should be treated as review questions,
  not silently ignored or reverted.

Current untracked review-scope inventory:

- `analysis/evidence_consistency.py`
- `docs/superpowers/plans/2026-05-29-evidence-artifact-test-split.md`
- `docs/superpowers/plans/2026-05-29-evidence-consistency-split.md`
- `docs/superpowers/plans/2026-05-29-evidence-contract-report-test-split.md`
- `docs/superpowers/plans/2026-05-29-evidence-manifest-check-test-split.md`
- `docs/superpowers/plans/2026-05-29-evidence-manifest-generation-test-split.md`
- `docs/superpowers/plans/2026-05-29-evidence-replay-artifact-report-test-split.md`
- `docs/superpowers/plans/2026-05-29-evidence-report-manifest-shape-test-split.md`
- `docs/superpowers/plans/2026-05-29-evidence-s10-trace-report-test-split.md`
- `docs/superpowers/plans/2026-05-30-control-center-browser-dom-test-split.md`
- `docs/superpowers/plans/2026-05-30-control-center-browser-manifest-test-split.md`
- `docs/superpowers/plans/2026-05-30-evidence-contract-report-follow-on-split.md`
- `docs/superpowers/plans/2026-05-30-evidence-report-orchestrator-cleanup.md`
- `docs/superpowers/plans/README.md`
- `docs/superpowers/specs/2026-05-29-evidence-artifact-test-split-design.md`
- `docs/superpowers/specs/2026-05-29-evidence-consistency-split-design.md`
- `docs/superpowers/specs/README.md`
- `tests/test_control_center_browser_dom.py`
- `tests/test_control_center_browser_error_manifest.py`
- `tests/test_control_center_browser_manifest.py`
- `tests/test_control_center_browser_report.py`
- `tests/test_evidence_consistency.py`
- `tests/test_evidence_contract_boundary_report.py`
- `tests/test_evidence_contract_fallback_report.py`
- `tests/test_evidence_contract_report.py`
- `tests/test_evidence_contract_trace_report.py`
- `tests/test_evidence_manifest_generation.py`
- `tests/test_evidence_replay_artifacts_report.py`
- `tests/test_evidence_replay_consistency_report.py`
- `tests/test_evidence_replay_report.py`
- `tests/test_evidence_report_artifact_paths.py`
- `tests/test_evidence_report_contract_shape.py`
- `tests/test_evidence_report_manifest_shape.py`
- `tests/test_evidence_report_study_shape.py`
- `tests/test_evidence_trace_report.py`
- `tests/test_evidence_wrapper_report.py`

## Content Partitions For Commit And Review

Use these partitions when reading the new commits or when exporting the review
packet. A file should appear in exactly one dominant partition even when it also
supports a quality-gate count or documentation sync.

| Partition | Primary paths | Review intent |
|---|---|---|
| Evidence report split | `analysis/evidence_report.py`, `analysis/evidence_consistency.py`, `tests/test_evidence_*.py`, `docs/EVENT_EVIDENCE_MANIFEST.md`, `docs/STACK_DATA_CONTRACT.md` | Confirm the reviewer CLI remains a thin orchestrator while manifest, artifact, study-consistency, and stack-contract checks have clear module/test ownership. |
| Control-center browser evidence | `analysis/control_center_data.py`, `scripts/package_smoke.py`, `tests/test_control_center*.py`, `analysis/artifacts/control-center-*`, `docs/CONTROL_CENTER_HANDOFF.md` | Confirm normal, backend-error, and frontend-contract-error browser replay paths are covered by saved manifests, report replay, package smoke, and integration audit evidence. |
| Review authority and quality gates | `scripts/review_authority_lint.py`, `scripts/evidence_boundary_lint.py`, `scripts/quality_gate_counts.py`, `tests/test_quality_gate_counts.py`, `tests/test_synthetic_evidence_boundaries.py`, current quality-gate docs | Confirm current ledgers precede historical packets, public prose stays inside the synthetic-evidence boundary, and the `943` pytest count plus canonical command block remain synchronized. |
| Opus/Codex handoff and historical packets | `docs/opus-review/`, `docs/codex-review/`, `docs/claude-review/`, `claude-review/docs/`, `docs/claude-development-audit/`, `wiki/`, `spacex-Session.md` | Confirm historical review packets are trace inputs only, not current open-risk authority, and that Opus starts from this handoff plus live ledgers. |
| Superpowers plan/spec inventory | `docs/superpowers/plans/`, `docs/superpowers/specs/` | Confirm dated execution traces and design notes are audit artifacts; open checkboxes in old prose are not treated as live risk unless the current ledgers agree. |
| Generated metric and public-summary sync | `README.md`, `PR-REQUIREMENTS.md`, `analysis/artifacts/SUMMARY.txt`, `docs/V2_Knowledge/knowledge-base.html`, `docs/knowledge-base.html` | Confirm public summaries match current generated evidence and keep the research/synthetic boundary explicit. |

Suggested commit order:

1. Evidence report split and tests.
2. Control-center browser evidence and generated browser artifacts.
3. Review authority, evidence-boundary lint, and quality-gate synchronization.
4. Superpowers plan/spec inventories.
5. Opus/Codex handoff, historical-packet routing, wiki ledger, and public-summary
   sync.

## Current Baseline

- Worktree and ahead count: inspect live with
  `git status --short --branch --untracked-files=all`.
- Current synchronized pytest count: `943`.
- Fresh local verification from this continuation pass:
  - `python -m pytest tests -q` passed.
  - `python -m analysis.run_all` completed all 12 studies.
  - `python -m analysis.evidence_manifest` regenerated the event evidence manifest.
  - `python -m analysis.evidence_report` reported `artifact_check ok studies=3 files=8`.
  - `python -m scripts.review_authority_lint` reported `review authority order ok`.
  - `python -m scripts.evidence_boundary_lint` reported `evidence boundary lint ok`.
  - `python -u -m scripts.quality_gate_counts` reported `quality gate pytest count: 943`.
  - `python -m scripts.quality_gate_counts --check --skip-expensive` reported `quality gate docs check passed`.
  - The v2026-05-31 returned-review M1/M2 count-sync findings are resolved for
    the current handoff surface by these synchronized current-count checks.

## Reviewer Runbook

Use this order so the review starts from current state instead of old packet
context:

1. First 15 minutes: run
   `git status --short --branch --untracked-files=all`, inspect this handoff,
   then read `wiki/review-backlog.md`, `docs/codex-review/OPEN_RISKS.md`, and
   `docs/codex-review/QUALITY_GATES.md`.
   Confirm whether the dirty/untracked set is intentional and whether any new
   files are missing from the review surface.
2. Evidence replay: use `docs/codex-review/QUALITY_GATES.md` as the canonical
   command list, then run the minimum evidence commands in Section 5 of
   `docs/opus-review/OPUS_REVIEW_PACKET.md`, especially
   `analysis.evidence_manifest` before `analysis.evidence_report`. Expected
   snippets are listed below, but the live command output is authoritative.
3. Targeted code review: inspect the split evidence-report modules, stack
   contract routing, adapter exception payloads, control-center browser
   evidence, and quality-gate updater tests named in the Review Focus section.
4. Risk decision: decide whether the remaining items in
   `docs/codex-review/OPEN_RISKS.md` are acceptable research follow-ups or
   blockers for the next merge/handoff.

## Handoff Sanity Checklist

- Fresh `git status --short --branch --untracked-files=all` has been captured
  by the reviewer.
- `python -m pytest --collect-only -q tests` still totals 943 collected tests.
- `analysis.evidence_report` is run after `analysis.evidence_manifest` when
  generated evidence may have changed.
- Browser evidence includes normal, backend-error, and frontend-error manifest
  replay paths.
- New untracked split files are included in the review and not silently omitted
  from any handoff or merge scope.
- Root `spacex-Session.md` is treated as a historical session export, not a
  current review authority; use this handoff and the live ledgers instead.
- `docs/superpowers/plans/README.md` and
  `docs/superpowers/specs/README.md` have been checked before using any dated
  plan or design note as evidence; those files are execution trace artifacts
  and design note artifacts, not the live review backlog.
- Do not promote synthetic scenario evidence to production proof, and do not
  describe the repository as a SpaceX-official implementation.

## Evidence Report Split State

`analysis.evidence_report` is now the thin reviewer CLI/orchestrator. Validation
ownership is split as follows:

- `analysis.evidence_artifacts`: artifact paths, missing files, byte identity,
  JSON/JSONL/PNG parseability, trace and runtime-event schema checks.
- `analysis.evidence_manifest_checks`: manifest top-level, study, contract,
  artifact key/extension, metadata, and SHA-256 shape checks.
- `analysis.evidence_consistency`: S10/S11/S12 study-level consistency checks.
- `analysis.evidence_contracts`: stack-contract artifact consistency and
  trace-route contract-event checks.

Report-path test ownership is also split:

- `tests/test_evidence_manifest.py`: report smoke plus artifact presence,
  metadata, and byte-identity failures.
- `tests/test_evidence_report_manifest_shape.py`: top-level manifest JSON/file
  rejection paths.
- `tests/test_evidence_report_study_shape.py`: study-entry manifest-shape
  rejection paths.
- `tests/test_evidence_report_contract_shape.py`: contract-entry
  manifest-shape rejection paths.
- `tests/test_evidence_report_artifact_paths.py`: artifact path portability,
  key parity, and extension rejection paths.
- `tests/test_evidence_contract_report.py`: stack-contract artifact scope,
  route-map, and stage-interface report paths.
- `tests/test_evidence_contract_fallback_report.py`: stack-contract fallback
  field and fallback action/mode map report paths.
- `tests/test_evidence_contract_trace_report.py`: stack-contract trace-route
  fallback, adapter-family, fault-family, exception-cause, and recoverability
  report paths.
- `tests/test_evidence_contract_boundary_report.py`: stack-contract
  split-boundary and trace-event routing report paths.
- `tests/test_evidence_trace_report.py`: S10 trace consistency, time-field, and
  runtime-event schema report paths.
- `tests/test_evidence_wrapper_report.py`: S11 catch-wrapper PNG and diagnostics
  report paths.
- `tests/test_evidence_replay_report.py`: S12 diagnostics artifact-field report
  paths.
- `tests/test_evidence_replay_consistency_report.py`: S12 replay diagnostics
  consistency report paths.
- `tests/test_evidence_replay_artifacts_report.py`: S12 replay
  trace/fixture/schema report paths.

Direct helper tests live in `tests/test_evidence_artifacts.py`,
`tests/test_evidence_manifest_checks.py`, `tests/test_evidence_consistency.py`,
`tests/test_evidence_contracts.py`, and
`tests/test_evidence_manifest_generation.py`.

## Review Focus

Start with these areas when re-reviewing the current workspace:

1. Review authority order: `scripts.review_authority_lint`,
   `wiki/review-backlog.md`, `OPEN_RISKS.md`, `QUALITY_GATES.md`, and
   `OPUS_REVIEW_PACKET.md`.
2. Evidence boundary wording: synthetic evidence must remain scoped as
   scenario/replay/research evidence. Check `scripts/evidence_boundary_lint.py`
   and `tests/test_synthetic_evidence_boundaries.py` for both overclaim wording
   and dynamic public prose coverage.
3. Evidence report modularization: confirm the split modules preserve
   reviewer-facing CLI output and phase ordering.
4. Stack contract and adapter exception routing: check `sre_control/stack.py`,
   `sre_control/events.py`, `sre_control/stack_contract.py`,
   `analysis/evidence_contracts.py`, `tests/test_contracts.py`,
   `tests/test_evidence_contract_report.py`,
   `tests/test_evidence_contract_fallback_report.py`,
   `tests/test_evidence_contract_trace_report.py`, and
   `tests/test_evidence_contract_boundary_report.py`.
5. Control-center browser evidence: check
   `scripts.control_center_browser_smoke`,
   `tests/test_control_center_browser_dom.py`,
   `tests/test_control_center_browser_smoke.py`,
   `tests/test_control_center_browser_manifest.py`,
   `tests/test_control_center_browser_error_manifest.py`,
   `tests/test_control_center_browser_report.py`,
   `tests/test_control_center_integration_audit.py`,
   `analysis/artifacts/control-center-browser-evidence-report.json`, and
   `docs/CONTROL_CENTER_HANDOFF.md`.
6. Quality-gate updater coverage: check `scripts/quality_gate_counts.py` and
   `tests/test_quality_gate_counts.py` for synchronized count updates,
   required command coverage, Opus authority ordering, evidence-boundary CLI
   coverage, stale non-quiet full-suite command rejection, update-before-check
   command ordering, full canonical command-sequence enforcement, contiguous
   command-surface enforcement, and Superpowers plan/spec inventory guards.

## Questions For Opus

Please make the re-review decision against these concrete questions:

1. Are any current `docs/codex-review/OPEN_RISKS.md` items blockers, or are
   they acceptable follow-up research slices?
2. Does the evidence-report split preserve the same reviewer-facing CLI
   behavior while improving test/module ownership?
3. Do the stack data contract and adapter exception payloads provide enough
   routeability for the current single-process research stack boundary?
4. Does the control-center browser evidence sufficiently cover normal,
   backend-error, and frontend-contract-error replay paths for this research
   handoff?
5. Are any dirty or untracked files outside the intentional merge/review scope
   shown by the live `git status --short --branch --untracked-files=all`
   output?
6. Does `scripts.evidence_boundary_lint` fail closed when new public prose docs
   are added without boundary-lint coverage?

## Recommended Re-Run Commands

```bash
python -m pytest tests -q
python -m analysis.s10_failure_trace
python -m analysis.run_all
python -m analysis.evidence_manifest
python -m analysis.evidence_report
python -m scripts.control_center_browser_smoke --report-manifests --report-json analysis/artifacts/control-center-browser-evidence-report.json
python -m scripts.package_smoke
python -m scripts.control_center_integration_audit
python -m scripts.review_authority_lint
python -m scripts.evidence_boundary_lint
python -m examples.demo_sre_loop
python -m examples.demo_powered_descent
python -m examples.demo_catch_phase
python -u -m scripts.quality_gate_counts
python -m scripts.quality_gate_counts --check --skip-expensive
```

Expected key output snippets in the current docs:

```text
quality gate pytest count: 943
artifact_check ok studies=3 files=8
manifest_replay=normal+backend_error+frontend_error
control-center integration audit ok
review authority order ok
evidence boundary lint ok
```

Browser evidence summaries should include normal desktop/mobile replay, backend
contract error replay, and frontend contract error replay. If DOM hashes or
artifact bytes change after rerunning generators, first decide whether the diff
comes from current generator output before treating it as a source regression.
