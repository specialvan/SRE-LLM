# ADR-0001 · Why no deep-learning framework

Status: Accepted
Date: 2026-05-10

## Context

The nine mechanisms include a GNN (§5) and, in principle, could run learned
retention / churn models. A typical reflex would be to pull in PyTorch or
TensorFlow. This project targets SRE self-iteration: decisions must be
reviewable, reproducible, and runnable on any SRE host without a model
server.

## Decision

Stay on numpy + scipy. Implement the GNN as an explicit
`h = ReLU(W h + A h U)` matrix multiplication. Use Cox partial likelihood
solved with a plain gradient loop. Keep the option of swapping any module
for a trained counterpart at the protocol level (see
`core/protocols.py`).

## Consequences

- **+** Zero CUDA / cuDNN / tokenizer dependencies; `pip install -e .`
  works behind restrictive firewalls.
- **+** Every intermediate math step is visible in the codebase; codex /
  reviewer can audit without opening a model card.
- **+** Deterministic by construction — see ADR-0004.
- **−** Throughput is O(100) RPS on a single core, not O(10k). That's fine
  for per-release decisions but rules out online per-request use.
- **−** If we ever need a proper learned retention model we must either
  embed a small neural core or call out to a sidecar service. The
  `RetentionModel` class already exposes the right seam.
