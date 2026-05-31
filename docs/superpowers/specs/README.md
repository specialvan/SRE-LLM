# Superpowers Spec Artifacts

This directory contains dated design notes used to plan focused implementation
passes. These files are useful for reconstructing design intent, but they are
not the live review backlog.

Current review state is authoritative in this order:

1. Source, tests, generated evidence artifacts, and fresh command output.
2. `wiki/review-backlog.md`.
3. `docs/codex-review/OPEN_RISKS.md`.
4. `docs/codex-review/QUALITY_GATES.md`.
5. `docs/opus-review/HANDOFF.md`, especially its `Git Review Scope Snapshot`;
   refresh `git status --short --branch --untracked-files=all` and
   `git ls-files --others --exclude-standard` before deciding whether
   dirty/untracked spec artifacts are in scope.

Some dated design notes intentionally preserve assumptions, acceptance checks,
or future-slice language from the moment the design was written. Do not treat a
design note as an open risk unless the current source, tests, or live ledgers
also show the work is still missing.

When a spec file is part of the current dirty/untracked review surface, use
fresh `pytest --collect-only`, focused tests, the `Git Review Scope Snapshot`,
and the live ledgers above to decide whether the design is complete,
superseded, or still actionable.

## Current Artifact Inventory

- `2026-05-29-evidence-artifact-test-split-design.md`
- `2026-05-29-evidence-consistency-split-design.md`
