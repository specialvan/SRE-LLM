# 2026-05-16 Release Hygiene Review

> Historical audit artifact; it is not the current handoff.
> Opus review should start from `docs/opus-review/HANDOFF.md`, then verify
> live status in `wiki/review-backlog.md`,
> `docs/codex-review/OPEN_RISKS.md`, and
> `docs/codex-review/QUALITY_GATES.md`.

## Verdict

`WATCH-004` is resolved in the working tree. The repository still has no git tags, and that is correct for the current state: `PR-REQUIREMENTS.md` is a spec/review-ledger document at `0.3.7`, while the installable Python package remains `0.1.0`.

No release tag was added in this pass because the project has not promoted the spec-ledger version into a package or artifact release promise.

## Evidence

- `git tag --list` returns no tags.
- `pyproject.toml`, `starship.__version__`, and `sre_control.__version__` all expose package version `0.1.0`.
- `PR-REQUIREMENTS.md` keeps the spec/review-ledger version separate from Python package version under NFR-7.
- `tests/test_release_hygiene.py` now makes that policy executable:
  - package version surfaces must move together;
  - the spec ledger version must remain explicitly documented as separate from package release;
  - front matter must not pin `head-commit` to a concrete SHA.

## Verification

```text
python -m pytest tests/test_release_hygiene.py -q
..                                                                       [100%]
```

Additional full-suite and quality-gate evidence is recorded in the paired evidence snapshot.

## Backlog Result

- `WATCH-004` moved to `RES-023`.
- No active or watch items remain after this pass.
