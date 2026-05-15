# 2026-05-15 Joseph-Form Cleanup Review

## Verdict

`AUDIT-006` is resolved in the working tree. The EKF runtime was already using Joseph form correctly; this pass repaired the derivation document so readers no longer see the simplified covariance update mislabeled as Joseph form.

## Evidence

- `docs/SPECIAL_SOLUTIONS_DERIVATIONS.md:44` now labels `(I - K_k H_k) P_{k|k-1}` as the standard form.
- `docs/SPECIAL_SOLUTIONS_DERIVATIONS.md:45` writes the full Joseph form with the right-side transpose term and measurement-noise term.
- `docs/SPECIAL_SOLUTIONS_DERIVATIONS.md:690` applies the same full expression in the complete EKF equation table.
- `docs/SPECIAL_SOLUTIONS_DERIVATIONS.md:826` and `docs/SPECIAL_SOLUTIONS_DERIVATIONS.md:827` now show code that computes `joseph_left @ P_pred @ joseph_left.T + K @ R_metrics @ K.T`.

## Verification

```text
python -m pytest tests/test_ekf.py tests/test_event_schema.py -q
.........                                                                [100%]
```

The unrelated control-center drilldown contract that appeared in the dirty worktree was also checked separately:

```text
python -m pytest tests/test_control_center.py -q
......                                                                   [100%]
```

Full-suite verification after the concurrent control-center tests:

```text
python -m pytest tests -q
........................................................................ [ 84%]
.............                                                            [100%]
```

HTML parser smoke check:

```text
docs\control-center.html: ok
docs\V2_Knowledge\knowledge-base.html: ok
docs\knowledge-base.html: ok
```

`git diff --check` emitted only CRLF normalization warnings and no whitespace errors.

Collection evidence:

```text
python -m pytest tests --collect-only -q
tests/test_allocation.py: 1
tests/test_contracts.py: 19
tests/test_control_center.py: 6
tests/test_ekf.py: 4
tests/test_event_schema.py: 5
tests/test_failure_trace.py: 10
tests/test_import_graph.py: 2
tests/test_mpc.py: 1
tests/test_quaternion.py: 3
tests/test_rigid_body.py: 2
tests/test_sre_control.py: 21
tests/test_stability_monitor.py: 8
tests/test_thrust_constraints.py: 3
```

Current-facing quality-gate text was synchronized to this dirty-tree count in `PR-REQUIREMENTS.md` and `docs/V2_Knowledge/knowledge-base.html`. This is still a manual sync; `AUDIT-010` remains open until the count comes from a generated source of truth.

## Remaining Risks

- `AUDIT-005`: the V1/V2 HTML knowledge-base entry relationship still needs a canonical-entry decision.
- `AUDIT-010`: quality-gate counts are still manually maintained in multiple docs; current-facing docs now say 85, but the count is not generated yet.
- `tests/test_control_center.py` and `docs/control-center.html` contain concurrent frontend-contract changes; keep them intact and review separately before committing.
