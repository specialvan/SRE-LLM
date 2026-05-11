# Implementation Roadmap

This document turns the architecture into a concrete delivery sequence.
It is the bridge between the architecture summary, ADRs, and PR-level
work.

## 1. Release Sequence

### Phase 0 - Control plane hardening

Goal: freeze the decision contract.

- typed config
- deterministic seeding
- structured logs
- metrics registry
- correlation-id tracing
- enum decision kinds

### Phase 1 - Domain pipeline

Goal: make the self-iteration loop production-shaped.

- `ReleaseContext` / `Decision`
- stage orchestration
- guard clauses
- shadow / advisory / off
- circuit breaker
- per-service lock
- process-level writer lease

### Phase 2 - Persistence and replay

Goal: make every decision reconstructable.

- service state persistence
- observation log
- synergy graph persistence
- decision persistence
- replay runbook and golden traces
- SQLite audit-row to replay-fixture exporter

### Phase 3 - Training and artifact hydration

Goal: make learned components operational.

- retention training
- Cox training
- artifact serialization
- startup hydration
- artifact versioning in trace

### Phase 4 - Runtime surfaces

Goal: expose the loop to operators and automation.

- HTTP service
- CLI
- benchmark
- deployment manifests
- CI coverage

### Phase 5 - Knowledge and reviewability

Goal: make the system easy to review and evolve.

- ADRs
- runbooks
- knowledge base
- architecture-to-module map

## 2. PR Map

| Phase | PR family | Purpose |
| --- | --- | --- |
| 0 | PR-0-01 to PR-0-06 | control plane primitives |
| 1 | PR-1-01 to PR-1-06 | decision loop + policy engine |
| 2 | PR-2-01 to PR-2-06 | persistence + replay |
| 3 | PR-3-01 to PR-3-04 | training + runtime artifacts |
| 4 | PR-4-01 to PR-4-04 | interfaces + deployability |
| 5 | ADR / runbook / docs | governance and explanation |

## 3. Detailed Task Breakdown

### A. Contract

- freeze `DecisionKind`
- freeze `Decision.trace` structure
- define model artifact metadata schema
- define replay input contract

### B. Compute

- keep each mathematical mechanism isolated
- ensure deterministic defaults
- keep fallback logic explicit

### C. State

- persist all decision-relevant state
- hydrate on startup
- record model artifact identity

### D. Policy

- keep policy resolution pure and testable
- centralize hard rules
- keep critical-tier overrides explicit

### E. Operability

- maintain runbooks
- keep readiness and metrics actionable
- support replay from a single archived decision
- export replay fixtures from persisted SQLite decisions

## 4. Risks to Watch

- learned models without versioning
- silent fallback paths
- cross-process concurrency
- local lease mistaken for distributed consensus
- trace schema drift
- mixing research demos into runtime

## 5. Next Delivery Target

The best next increment is:

1. expand the replay corpus from branch coverage into incident-style
   scenario coverage
2. add replay promotion rules for fitted-artifact decisions
3. prototype a distributed lease backend if the deployment target needs
   multiple writable replicas
