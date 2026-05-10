# ADR-0003 · Layered structure — core / sre / game

Status: Accepted
Date: 2026-05-10

## Context

The project started as a translation of the "game matchmaking" article
and grew into an SRE decision engine. Mixing both vocabularies in the
same module breaks review: a reliability engineer should not have to
read about win streaks, and a game engineer should not have to read about
error budgets.

## Decision

Split the package into three disjoint concern groups:

```
gan_matchmaking/
├── core/      infrastructure: config, logging, metrics, tracing, errors, RNG
├── sre/       domain layer — release decisions, self-iteration pipeline
└── <top>      the nine mathematical modules, agnostic to either domain
```

- `core/` has **no** dependency on the maths modules.
- The nine maths modules have **no** dependency on `sre/`.
- `sre/` depends on both.
- The old `GanPipeline` (game demo) stays at the top level for tutorial
  purposes but is explicitly *not* the SRE artefact.

## Consequences

- **+** Reviewers can read `sre/` end-to-end without touching the game
  analogies.
- **+** The nine maths modules are reusable outside SRE (e.g. a future
  CI scheduler or a cost-vs-latency game).
- **+** `core/` becomes a micro-library we can vendor into sibling tools
  (the `auto-decide` repo already has similar needs).
- **−** Three-layer import discipline is a review-time responsibility.
  A lint rule in `pyproject.toml` (future work) can enforce it.
