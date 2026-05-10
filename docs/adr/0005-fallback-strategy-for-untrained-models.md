# ADR-0005 · Fallback strategy for untrained models

Status: Accepted
Date: 2026-05-10

## Context

Two components need training data we usually don't have during bootstrap:
the EOMM retention model (`RetentionModel`) and the churn Cox model
(`CoxModel`). A reviewer asked the correct question: "what does the
pipeline do when these are untrained?"

## Decision

Every learned component has a **deterministic pessimistic fallback** that
the pipeline uses until real data arrives:

1. `RetentionModel` starts with zero weights → `sigmoid(0) = 0.5`. The SRE
   pipeline therefore falls back to the rule-based linear scoring in
   `_stage_eomm` until weights have been fit. This rule is kept in the
   tree because reviewers can read it without a training run.
2. `ChurnRiskMonitor` with an unfit Cox model evaluates a default-weighted
   logistic on the full feature vector rather than a single dimension.
   The default weights bias toward higher risk so `HOLD` / `ROLLBACK` is
   the safe default.
3. `HiddenScoreExtractor` raises `RuntimeError` if called before `fit`.
   The SRE pipeline catches this in `_stage_pca` and emits a degraded
   stage trace instead of failing the whole decision.

## Consequences

- **+** The pipeline is safe to run on Day 1 with zero historical data.
- **+** Reviewers can trace every fallback from the `trace.stages` payload.
- **−** The pessimistic bias means a healthy team may see more `CANARY`
  recommendations than necessary during bootstrap. Acceptable cost; we
  prefer false positives to false negatives for reliability.
