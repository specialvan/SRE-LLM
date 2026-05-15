# 2026-05-15 Post-Commit Review

## Verdict

The audit engineering package is now durable: it is committed on `spacex-session` and the working tree was clean at the start of this pass. The branch is ahead of `origin/spacex-session` by six commits, so remote publication remains a separate delivery step if needed.

The current active work is no longer "create the audit package"; it is "continue the audit loop by safely fixing canonical-doc drift without corrupting Chinese UTF-8 content."

## Findings

### [P1] Canonical PR spec still mixes current and historical quality gates

Evidence:

- `PR-REQUIREMENTS.md` current front matter records 83 tests and 11 event kinds.
- The same file still contains older historical mentions of 51-test gates in PR history sections.
- `2026-05-15-encoding-repair-note.md` records that unsafe bulk editing was reverted to avoid mojibake.

Impact:

The top-level gates are current, but historical sections can still be mistaken for current facts unless each old count is clearly marked as historical. This is a documentation trust issue, not a runtime defect.

Next action:

Use line-scoped UTF-8-safe edits only. Do not use broad PowerShell rewrite operations on Chinese docs.

### [P2] Joseph-form derivation cleanup remains active

Evidence:

- Earlier review evidence identified `docs/SPECIAL_SOLUTIONS_DERIVATIONS.md` snippets that label simplified covariance updates as Joseph form.
- The runtime implementation in `starship/ekf.py` already uses Joseph form and symmetrization.
- The unsafe bulk-doc path was reverted, so this cleanup remains active.

Impact:

The code is correct, but the derivation document can teach the wrong update if read in isolation.

Next action:

Patch only the specific formula/snippet lines, then rerun `pytest tests/test_ekf.py tests/test_event_schema.py -q`.

### [P2] HTML canonical-entry wording remains a review target

Evidence:

- V2 HTML is more current and includes the 11-kind event index.
- V1 `docs/knowledge-base.html` remains a plausible entry point.
- `backlog.md` keeps this as `AUDIT-005`.

Impact:

Reviewers can still enter through the older page unless README/V1/V2 wording clearly distinguishes current entry vs archive.

Next action:

Patch the small visible labels only, then consider a drift check.

## Resolved Since Previous Pass

| Item | Evidence |
|---|---|
| Audit package git persistence | `72e960c audit: land claude development review package` |
| Post-commit status reconciliation | `93e85ab audit: finalize review package status` |
| Historical event-count wording | `6000034 docs: clarify historical event counts` |
| Quality-gate count back to 83 | `2fc5b5e docs: align audit quality gate count` |
| Final analysis evidence | `0785d9e`, `0b2292f` |

## Next Review Route

1. Fix `SPECIAL_SOLUTIONS_DERIVATIONS.md` Joseph snippets with minimal patch.
2. Refresh `PR-REQUIREMENTS.md` historical quality-gate wording with minimal patch.
3. Decide whether V1 HTML should be visibly marked archive in page chrome.
4. Push `spacex-session` if remote persistence is required.
