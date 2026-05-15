# 2026-05-16 Synthetic Evidence Boundary Review

## Verdict

`WATCH-001` is resolved in the working tree. The synthetic before/after evidence now has executable guardrails for the two easiest-to-overstate tradeoffs:

- Section 5 EKF improves velocity RMSE in the seed-0 scenario, but its `pos_p95` tail position error is worse than the raw-radar baseline.
- Section 8 catch allocation eliminates throttle-bound violations, but its mean wrench residual is not better than the unconstrained pseudoinverse baseline.

## Evidence

- `tests/test_synthetic_evidence_boundaries.py` calls `analysis.s05_ekf.main(seed=0)` and asserts both sides of the tradeoff: `after["vel_rmse"] < before["vel_rmse"]` and `after["pos_p95"] > before["pos_p95"]`.
- The same test file calls `analysis.s08_catch_allocation.main(seed=0)` and asserts `after["saturation_violation_pct"] == 0` while keeping `after["mean_residual"] >= before["mean_residual"]` visible.
- These checks turn the review language from a passive documentation warning into a regression test: if a future report or script hides these counterexamples by changing the scenario or metric names, the quality gate fails.

## Verification

```text
python -m pytest tests/test_synthetic_evidence_boundaries.py -q
..                                                                       [100%]
```

Additional full-suite and artifact verification is recorded in the paired evidence snapshot.

## Backlog Result

- `WATCH-001` moved to `RES-022`.
- Remaining watch item: release tag hygiene.
