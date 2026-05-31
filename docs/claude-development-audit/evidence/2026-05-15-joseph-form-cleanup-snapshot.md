# 2026-05-15 Joseph-Form Cleanup Evidence

> Historical audit artifact; it is not the current handoff.
> Opus review should start from `docs/opus-review/HANDOFF.md`, then verify
> live status in `wiki/review-backlog.md`,
> `docs/codex-review/OPEN_RISKS.md`, and
> `docs/codex-review/QUALITY_GATES.md`.

## Repository State

```text
git rev-parse --short HEAD
32913d0
```

Working tree at the time of this pass included the Joseph documentation edits plus pre-existing/concurrent control-center drilldown edits:

```text
git status --short --branch
## spacex-session...origin/spacex-session [ahead 9]
 M docs/SPECIAL_SOLUTIONS_DERIVATIONS.md
 M PR-REQUIREMENTS.md
 M docs/V2_Knowledge/knowledge-base.html
 M docs/claude-development-audit/reports/2026-05-15-post-commit-review.md
 M docs/control-center.html
 M tests/test_control_center.py
```

## Line Anchors

```text
rg -n "P_\{k\|k\}.*标准形式|Joseph form|Joseph形式|joseph_left" docs/SPECIAL_SOLUTIONS_DERIVATIONS.md
44:  P_{k|k}   = (I - K_k · H_k) · P_{k|k-1}           (标准形式)
45:            = (I-K_kH_k)P_{k|k-1}(I-K_kH_k)^T + K_kR_kK_k^T  (Joseph form)
78:# 协方差更新使用 Joseph form，避免 (I-KH) 的病态问题
83:joseph_left = identity_matrix - K @ H_mat
84:posterior = joseph_left @ P_prior @ joseph_left.T + K @ R @ K.T
689:P_{k|k}   = (I - K_k · H_k) · P_{k|k-1}                  (7a) 标准形式
690:          = (I-K_kH_k)P_{k|k-1}(I-K_kH_k)^T + K_kR_kK_k^T (7b) Joseph形式
826:joseph_left = np.eye(3) - K @ H
827:P_new = joseph_left @ P_pred @ joseph_left.T + K @ R_metrics @ K.T  # Joseph form
```

## Verification

```text
python -m pytest tests/test_ekf.py tests/test_event_schema.py -q
.........                                                                [100%]
```

```text
python -m pytest tests/test_control_center.py -q
......                                                                   [100%]
```

```text
python -m pytest tests -q
........................................................................ [ 84%]
.............                                                            [100%]
```

```text
html.parser smoke check
docs\control-center.html: ok
docs\V2_Knowledge\knowledge-base.html: ok
docs\knowledge-base.html: ok
```

```text
git diff --check
warning: LF will be replaced by CRLF warnings only; no whitespace errors.
```

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
