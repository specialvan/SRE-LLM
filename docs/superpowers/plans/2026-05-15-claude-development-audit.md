# Claude Development Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a durable engineering package for deep review of Claude/Codex-developed content across code, process docs, wiki, HTML, tests, and git history.

**Architecture:** Keep the review package separate from existing `docs/codex-review/` and `docs/claude-review/` so it can audit both without rewriting history. Each report must cite concrete files, line anchors, command evidence, and a clear active/resolved/watch status.

**Tech Stack:** Markdown documentation, local git evidence, pytest, `analysis.run_all`, existing Python control stack.

---

## File Structure

- Create: `docs/claude-development-audit/README.md`
  - Package entry point, operating rules, report index, evidence boundaries.
- Create: `docs/claude-development-audit/reports/2026-05-15-deep-review.md`
  - First deep review with findings ordered by priority.
- Create: `docs/claude-development-audit/evidence/2026-05-15-snapshot.md`
  - Reproducible command evidence and observed outputs.
- Create: `docs/claude-development-audit/git/timeline.md`
  - Local git history interpretation for review context.
- Create: `docs/claude-development-audit/backlog.md`
  - Living issue register for the next passes.
- Create: `docs/superpowers/plans/2026-05-15-claude-development-audit.md`
  - This implementation plan.

---

### Task 1: Create Package Shell

**Files:**
- Create: `docs/claude-development-audit/README.md`
- Create: `docs/claude-development-audit/backlog.md`

- [x] **Step 1: Define package purpose**

Write the README with scope, source-of-truth rules, and package index.

- [x] **Step 2: Define issue lifecycle**

Use `Active`, `Resolved`, and `Watch` states so stale review findings do not look current.

- [x] **Step 3: Add initial backlog**

Seed the backlog from current review evidence: packaging drift, allocator fallback signature, stale specs, docs/schema sync, HTML canonical drift, and formula drift.

### Task 2: Capture Evidence

**Files:**
- Create: `docs/claude-development-audit/evidence/2026-05-15-snapshot.md`

- [x] **Step 1: Record repository snapshot**

Include branch, HEAD, clean working tree before report edits, tracked file count, and key commit range.

- [x] **Step 2: Record verification commands**

Record:

```bash
python -m pytest --collect-only -q
python -m pytest tests -q
python -m analysis.run_all
```

- [x] **Step 3: Record evidence boundaries**

Call out that `analysis.run_all` rewrites timing fields in `analysis/artifacts/SUMMARY.txt`; timing churn is not treated as behavioral evidence.

### Task 3: Write Deep Review

**Files:**
- Create: `docs/claude-development-audit/reports/2026-05-15-deep-review.md`

- [x] **Step 1: Put findings first**

Order issues by severity and cite file/line anchors.

- [x] **Step 2: Separate resolved previous findings**

Explicitly mark per-sensor gate, allocator last-good fallback, and EKF Joseph update as implemented in code, while noting stale docs that still describe them as open.

- [x] **Step 3: Add next review route**

Make the next pass executable: package metadata, allocator signature test, spec drift fix, docs/schema sync test, canonical HTML decision.

### Task 4: Git Timeline

**Files:**
- Create: `docs/claude-development-audit/git/timeline.md`

- [x] **Step 1: Group commits by review phase**

Use the local log from `cf9c8dc` through `13e534e`.

- [x] **Step 2: Identify git hygiene risks**

Call out no tags, one author, version drift, and docs over relying on "see git log".

### Task 5: Verification

**Files:**
- Read-only verification plus generated review docs.

- [x] **Step 1: Run tests**

`python -m pytest tests -q` exited 0 over 77 collected tests.

- [x] **Step 2: Run analysis suite**

`python -m analysis.run_all` completed all 10 studies.

- [x] **Step 3: Confirm git diff scope**

Only the new audit package and this plan should remain changed.
