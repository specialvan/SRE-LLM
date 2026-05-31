# Claude Development Audit

> This package is the ongoing deep-review ledger for Claude/Codex-developed work in this repository. It audits the code, process docs, wiki, HTML knowledge bases, analysis artifacts, and git history without replacing the existing `docs/codex-review/` or `docs/claude-review/` packets.

## Scope

This package reviews:

- implementation under `starship/`, `sre_control/`, `analysis/`, `scripts/`, and `examples/`
- process documents under `wiki/`, `docs/codex-review/`, `docs/claude-review/`, and root specs
- HTML knowledge-base assets under `docs/knowledge-base.html`, `docs/V2_Knowledge/`, and `docs/control-center.html`
- local git history on `spacex-session`
- reproducibility gates such as `pytest`, `analysis.run_all`, and generated artifacts

It does not claim any SpaceX internal implementation detail. All review claims are limited to the current repository, public-source mathematical analogies, and synthetic scenarios.

## Package Index

| File | Purpose |
|---|---|
| `reports/2026-05-15-deep-review.md` | First deep review of Claude/Codex-developed content |
| `reports/2026-05-15-continuation-review.md` | Follow-up pass reconciling the first report against the current working tree |
| `reports/2026-05-15-completion-audit.md` | Prompt-to-artifact completion audit for the active goal |
| `reports/2026-05-15-encoding-repair-note.md` | Correction note after reverting unsafe bulk doc edits |
| `reports/2026-05-15-post-commit-review.md` | Post-commit pass reconciling committed audit work against remaining backlog |
| `reports/2026-05-15-joseph-form-cleanup.md` | Targeted pass resolving the Joseph-form derivation drift |
| `reports/2026-05-15-quality-gates-html-canonical.md` | Targeted pass resolving generated quality-gate counts and HTML canonical entry drift |
| `reports/2026-05-16-package-smoke.md` | Targeted pass resolving installed-wheel smoke coverage |
| `reports/2026-05-16-control-center-exposure.md` | Targeted pass resolving control-center localhost and route exposure policy |
| `reports/2026-05-16-adapter-cause-taxonomy.md` | Targeted pass resolving adapter exception cause taxonomy granularity |
| `reports/2026-05-16-synthetic-evidence-boundaries.md` | Targeted pass locking synthetic before/after counterexamples as tests |
| `reports/2026-05-16-release-hygiene.md` | Targeted pass resolving spec/package version and tag hygiene |
| `evidence/2026-05-15-snapshot.md` | Command evidence and repository snapshot for the first report |
| `evidence/2026-05-15-continuation-snapshot.md` | Command evidence for the follow-up pass |
| `evidence/2026-05-15-post-commit-snapshot.md` | Command evidence for the post-commit pass |
| `evidence/2026-05-15-joseph-form-cleanup-snapshot.md` | Command evidence for the Joseph-form cleanup pass |
| `evidence/2026-05-15-quality-gates-html-canonical-snapshot.md` | Command evidence for the quality-gate and HTML canonical pass |
| `evidence/2026-05-16-package-smoke-snapshot.md` | Command evidence for installed-wheel smoke coverage |
| `evidence/2026-05-16-control-center-exposure-snapshot.md` | Command evidence for control-center exposure policy |
| `evidence/2026-05-16-adapter-cause-taxonomy-snapshot.md` | Command evidence for adapter exception cause taxonomy |
| `evidence/2026-05-16-synthetic-evidence-boundaries-snapshot.md` | Command evidence for synthetic evidence boundary tests |
| `evidence/2026-05-16-release-hygiene-snapshot.md` | Command evidence for release hygiene tests |
| `git/timeline.md` | Local commit timeline interpreted for reviewers |
| `backlog.md` | Living queue of active, resolved, and watch issues |

## Review Rules

1. Source code plus tests outrank stale docs.
2. Each finding must cite file/line anchors or command evidence.
3. Resolved findings stay visible, but only as historical context.
4. Synthetic before/after studies are mechanism evidence, not production guarantees.
5. New event kinds, runtime states, formulas, and package surfaces must update code, docs, tests, and review packet together.
6. Each pass appends a new dated report and updates `backlog.md`; do not overwrite old review conclusions in place.

## Current Status Routing

This directory preserves the dated Claude development-audit history. It is not
the live source for current branch status, open risks, or reviewer command
gates. For Opus handoff work, read the live ledgers first:

- `wiki/review-backlog.md` for current completed/open review state.
- `docs/codex-review/OPEN_RISKS.md` for the current risk register.
- `docs/codex-review/QUALITY_GATES.md` for canonical re-run commands and the
  current synchronized pytest count.
- `docs/opus-review/HANDOFF.md` for the current Opus first-read runbook and
  `Git Review Scope Snapshot`; refresh
  `git status --short --branch --untracked-files=all` and
  `git ls-files --others --exclude-standard` before reviewing dirty/untracked
  files from this audit surface.

Use the reports and evidence snapshots in this directory only as historical
context when tracing why a resolved item exists.
