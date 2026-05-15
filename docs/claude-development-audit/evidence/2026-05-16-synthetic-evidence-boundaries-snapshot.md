# 2026-05-16 Synthetic Evidence Boundary Evidence

## Repository State

```text
git status --short
 M PR-REQUIREMENTS.md
 M analysis/artifacts/SUMMARY.txt
 M docs/V2_Knowledge/knowledge-base.html
 M docs/claude-development-audit/README.md
 M docs/claude-development-audit/backlog.md
?? docs/claude-development-audit/evidence/2026-05-16-synthetic-evidence-boundaries-snapshot.md
?? docs/claude-development-audit/reports/2026-05-16-synthetic-evidence-boundaries.md
?? tests/test_synthetic_evidence_boundaries.py
```

## Focused Verification

```text
python -m pytest tests/test_synthetic_evidence_boundaries.py -q
..                                                                       [100%]
```

## Locked Boundary Metrics

From `analysis/artifacts/SUMMARY.txt` before this pass:

```text
Section 5 EKF:
  pos_p95   before=59.44  after=77.34
  vel_rmse  before=481.1  after=51.07

Section 8 catch allocation:
  mean_residual             before=1.809e+06  after=1.875e+06
  saturation_violation_pct  before=33.75      after=0
```

These are intentionally mixed results. The repository can claim scenario-local speed-estimation and bound-satisfaction improvements, but not a universal improvement across every metric.

## Full Verification

```text
python -m pytest tests -q
........................................................................ [ 69%]
................................                                         [100%]
```

```text
python -m scripts.quality_gate_counts
quality gate pytest count: 104
```

```text
python -m analysis.run_all
All 10 studies finished in 3.32s. Artifacts in analysis/artifacts/.
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
