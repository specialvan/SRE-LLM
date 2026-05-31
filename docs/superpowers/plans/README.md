# Superpowers Plan Artifacts

This directory contains dated execution traces and implementation plans used by
agentic workers. These files are useful for reconstructing how a split or
cleanup was executed, but they are not the live review backlog.

Current review state is authoritative in this order:

1. Source, tests, generated evidence artifacts, and fresh command output.
2. `wiki/review-backlog.md`.
3. `docs/codex-review/OPEN_RISKS.md`.
4. `docs/codex-review/QUALITY_GATES.md`.
5. `docs/opus-review/HANDOFF.md`, especially its `Git Review Scope Snapshot`;
   refresh `git status --short --branch --untracked-files=all` and
   `git ls-files --others --exclude-standard` before deciding whether
   dirty/untracked plan artifacts are in scope.

Some dated execution traces intentionally preserve task-level checkboxes,
historical baseline counts, or TDD red/green instructions from the moment the
plan was written. Do not treat an unchecked box in an old plan as an open risk
unless the current source, tests, or live ledgers also show the work is still
missing.

When a plan file is part of the current dirty/untracked review surface, use
fresh `pytest --collect-only`, focused tests, the `Git Review Scope Snapshot`,
and the live ledgers above to decide whether the plan is complete, superseded,
or still actionable.

As of the current review surface, no current plan artifact has open task
checkboxes. A literal `- [ ]` mention may still appear as explanatory syntax,
but dated plan task lines should remain closed unless a fresh live ledger shows
the work is actually missing.

## Current Artifact Inventory

- `2026-05-15-claude-development-audit.md`
- `2026-05-29-evidence-artifact-test-split.md`
- `2026-05-29-evidence-consistency-split.md`
- `2026-05-29-evidence-contract-report-test-split.md`
- `2026-05-29-evidence-manifest-check-test-split.md`
- `2026-05-29-evidence-manifest-generation-test-split.md`
- `2026-05-29-evidence-replay-artifact-report-test-split.md`
- `2026-05-29-evidence-report-manifest-shape-test-split.md`
- `2026-05-29-evidence-s10-trace-report-test-split.md`
- `2026-05-30-control-center-browser-dom-test-split.md`
- `2026-05-30-control-center-browser-manifest-test-split.md`
- `2026-05-30-evidence-contract-report-follow-on-split.md`
- `2026-05-30-evidence-report-orchestrator-cleanup.md`
