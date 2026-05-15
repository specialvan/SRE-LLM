# 2026-05-15 Encoding Repair Note

## What Changed

During the continuation pass, a bulk PowerShell replacement path risked corrupting non-ASCII Chinese documentation. To avoid committing mojibake, the affected pre-existing docs were restored from `HEAD`, and the audit backlog was corrected back to the actual current state.

The review package itself remains valid and ASCII-safe. The code/test fixes that do not depend on bulk Chinese-doc rewrites remain in scope:

- `pyproject.toml` includes `sre_control*`.
- `sre_control/stack.py` allocator signatures include `zone_vector`.
- `tests/test_contracts.py` adds package/import and allocator topology regression tests.
- `tests/test_event_schema.py` adds docs/schema sync tests for `EVENT_SCHEMA.md` and `RUNTIME_STATES.md`.
- `docs/RUNTIME_STATES.md` was safely patched so `SignalFusion.step()` documents both `missing_sensor` and `outlier_rejected`.

## Corrected Active Risks

The following items are still active because the unsafe bulk doc edits were not kept:

- `PR-REQUIREMENTS.md` still needs a safe refresh for I-5 and quality gates.
- `docs/knowledge-base.html` and `docs/V2_Knowledge/knowledge-base.html` still need a canonical-entry decision.
- `docs/SPECIAL_SOLUTIONS_DERIVATIONS.md` still needs Joseph-form snippet cleanup.
- Version policy still needs to be added safely to the canonical spec.
- Quality-gate counts should be generated or edited with an encoding-safe workflow.

## Verification After Repair

Fresh command evidence after removing the unsafe V2 HTML tests:

```text
python -m pytest --collect-only -q  -> 85 collected tests
python -m pytest tests -q           -> exit 0 over 85 tests
```

`python -m analysis.run_all` also completed all 10 studies after the repair path.

## Completion Impact

The goal should not be marked complete yet. The engineering package exists and is useful, but the canonical-doc refresh work remains active, and the package/supporting changes still need a clean commit.
