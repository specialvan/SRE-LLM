# Claude Deep Review

This file is retained as historical review context. Earlier findings drove the
PR-A through PR-D hardening work and later audit passes. Current live risks are
tracked in `OPEN_RISKS.md`.

## Historical Findings Now Resolved

| Historical area | Current status |
|---|---|
| Section 10 continuous failure trace | Implemented with one continuous stack, full/sample JSONL, bounded background events, and full injected-window expected-kind coverage |
| Per-sensor innovation gates | Implemented and tested through `Signal.gate_threshold`, threshold resolution, and trace fields |
| Allocator fallback returning zero shares | Replaced with last-good fallback when the allocator signature is still valid; bootstrap still falls back to zero |
| EKF covariance update | Joseph form and covariance symmetrization are implemented and tested |
| HTML entry drift | V2 is canonical current entry; V1 is archive |

## Current Reviewer Focus

Reviewers should now focus on evidence boundaries rather than re-opening the
resolved findings:

1. Section 5 EKF evidence now includes radar + near-field fiducial updates, but
   should still not be over-described as production sensor proof.
2. StabilityGuard now has the `sre_error_budget_V` example; review should keep
   it scoped as a synthetic SRE energy candidate, not a universal alert rule.
3. Synthetic before/after studies should remain explicitly scenario-scoped.
4. Catch-to-SRE migration, if pursued, should happen through wrappers while
   preserving the `starship/` to `sre_control/` dependency boundary.

## Verification Pointers

Use the current gates instead of historical command output:

```bash
python -m pytest tests -q
python -m analysis.run_all
python -m analysis.s10_failure_trace
```

See `QUALITY_GATES.md` for the current pass count and gate families.
