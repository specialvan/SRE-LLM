# ADR-0004 · Determinism and seeding

Status: Accepted
Date: 2026-05-10

## Context

An SRE self-iterating system must be reproducible: given the same config
and input context, the output decision must be byte-identical. Otherwise
post-incident review cannot answer "why did the pipeline choose GO?".
The usual suspects for non-determinism are:

- numpy's default random state (thread-local, process-local but not
  reproducible across processes),
- Python's hash randomization (set / dict ordering on strings),
- matplotlib side effects during figure generation.

## Decision

1. Every RNG user goes through `core.SeedManager`, which derives named
   generators from a root seed via SHA-256.
2. The SRE pipeline accepts `seed` on `AppConfig`; the default is 0.
3. Tests allocate a fresh `MetricsRegistry` per test — no shared mutable
   state. Logs go to in-memory buffers in the test suite.
4. Figure generation is side-effect-isolated in `docs/generate_figures.py`
   and never imported from the library path.
5. `PYTHONHASHSEED` stays at default (0 / random) for normal runs; for
   reproducible decision audits we document setting `PYTHONHASHSEED=0` in
   `docs/runbooks/reproduce-decision.md`.

## Consequences

- **+** Decisions are replayable from the trace alone.
- **+** The regression test
  `test_deterministic_decision_under_same_config` locks this in.
- **−** Using the `default_registry` in multiple pipelines in the same
  process can produce confusing metric snapshots during tests — addressed
  by always injecting a dedicated registry from tests.
