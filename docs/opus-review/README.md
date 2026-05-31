# Opus Review Entry

This directory is the entrypoint for Opus re-review. Start from the live
handoff and ledgers, then use historical packets only for traceability.

## First-Read Files

| File | Purpose | How to read it |
|---|---|---|
| [`HANDOFF.md`](./HANDOFF.md) | Current Opus first-read handoff with baseline, runbook, content partitions, sanity checklist, focus areas, questions for Opus, and the `Git Review Scope Snapshot` for dirty/untracked review scope | Read first; refresh `git status --short --branch --untracked-files=all` and `git ls-files --others --exclude-standard` before any review decision, then review the content-split commits by partition |
| [`../../wiki/review-backlog.md`](../../wiki/review-backlog.md) | Cross-session completion ledger and evidence index | Check completed/open status |
| [`../codex-review/OPEN_RISKS.md`](../codex-review/OPEN_RISKS.md) | Current risk register | Decide whether anything remains a blocker |
| [`../codex-review/QUALITY_GATES.md`](../codex-review/QUALITY_GATES.md) | Current canonical command gates and observed local snippets | Use the required-command block for reruns; treat observed snippets as examples |
| [`OPUS_REVIEW_PACKET.md`](./OPUS_REVIEW_PACKET.md) | Current re-entry packet with verification commands, evidence assets, and historical-finding crosswalk | Use for command reruns and spot checks |
| [`docs/superpowers/plans/README.md`](../superpowers/plans/README.md), [`docs/superpowers/specs/README.md`](../superpowers/specs/README.md) | Superpowers plan/spec inventories for dated execution traces and design notes | Confirm every dated plan or spec artifact in the dirty/untracked surface is included in review scope or intentionally excluded |

## Historical Inputs

| File | Meaning |
|---|---|
| [`../../claude-review/docs/v2026-05-31/README.md`](../../claude-review/docs/v2026-05-31/README.md) | Historical Opus v2026-05-31 returned review context; M1/M2 were documentation/count-sync findings and current status is controlled by the live handoff and ledgers |
| [`../../claude-review/docs/v2026-05-28/README.md`](../../claude-review/docs/v2026-05-28/README.md) | Opus v2.1 continuation review context |
| [`../../claude-review/docs/v2026-05-26/README.md`](../../claude-review/docs/v2026-05-26/README.md) | Opus v2.0 historical review context |
| [`v1.0/`](./v1.0/) | Earlier Opus packet retained as trace material |

## Authority Order

1. Current source, tests, and generated evidence artifacts.
2. `docs/opus-review/HANDOFF.md`.
3. `wiki/review-backlog.md`.
4. `docs/codex-review/OPEN_RISKS.md`.
5. `docs/codex-review/QUALITY_GATES.md`.
6. `docs/opus-review/OPUS_REVIEW_PACKET.md`.
7. `claude-review/docs/v2026-05-31/README.md`.
8. `claude-review/docs/v2026-05-28/README.md`.
9. `claude-review/docs/v2026-05-26/README.md`.
10. `docs/opus-review/v1.0/` historical files.

## Boundaries

- Old review files provide historical context, not current completed/open state.
- Superpowers dated plans and specs are not the live review backlog; use their
  README inventory sections only to audit dirty/untracked review-scope coverage.
- This repository is a public-material research reproduction, not a SpaceX
  official implementation.
- Analysis artifacts are synthetic scenario evidence; review conclusions must
  keep that boundary explicit.
