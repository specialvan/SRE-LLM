# GAN Matchmaking / SRE Self-Iteration Architecture

This document describes the production-facing architecture of the
`gan_matchmaking` package: what it must do, how the layers fit together,
which parts are production-ready, and which parts are still research-grade.

## 1. Problem Statement

The system takes release context, telemetry, dependency state, and history,
then emits one of:

`GO`, `CANARY`, `HOLD`, `ROLLBACK`, `ESCALATE`

The decision must be:

- auditable
- deterministic
- safe under missing data
- replayable
- operable from a simple CLI or HTTP service

The nine mathematical mechanisms are not the product by themselves. They
are reusable scoring / filtering / policy primitives inside a larger SRE
control loop.

## 2. Architecture Goals

1. Separate infrastructure from domain logic.
2. Keep the decision policy explainable.
3. Make learned components optional, not required.
4. Preserve runtime safety under cold start.
5. Expose every decision as trace + metrics + persisted state.
6. Support offline training without changing runtime code paths.

## 3. Requirements

### 3.1 Functional

- Validate every release context before scoring.
- Produce a typed decision object with rationale and trace.
- Score release confidence, hidden telemetry, dependency synergy, risk,
  and retention.
- Support per-service sequential decisioning.
- Persist observations, services, decisions, and synergy edges.
- Reload persisted state on startup.
- Train Cox and retention models from stored observations.
- Serve decisions over HTTP and CLI.

### 3.2 Non-functional

- Deterministic for same config + same input + same seed.
- Single-process multi-thread safe for decision calls.
- Fail closed under model or numeric failure.
- Latency bounded and measurable.
- Logging must be structured JSONL.
- Metrics must be Prometheus-compatible.

### 3.3 Operational

- Health/readiness/metrics endpoints.
- Shadow/advisory rollout modes.
- Circuit breaker for dependency or runtime instability.
- Runbooks for replay, bootstrap, threshold tuning, and escalation.
- SQLite or memory backend for local and small-scale deployment.

### 3.4 Governance

- Decision kind must be an enum, not a boolean.
- Fallback behavior must be explicit and documented.
- Production and research code paths must not import each other.

## 4. Layered Architecture

### 4.1 Core Infrastructure

`gan_matchmaking/core/`

- typed config
- typed errors
- JSONL logging
- metrics registry
- tracing / correlation id
- deterministic RNG
- narrow protocols

This layer is dependency-light and reusable across sibling systems.

### 4.2 Domain Layer

`gan_matchmaking/sre/`

- `domain.py`: `Service`, `ReleaseCandidate`, `ReleaseContext`, `Decision`
- `self_iteration.py`: the primary control loop
- `locking.py`: per-service mutex
- `circuit.py`: breaker
- `shadow.py`: off / shadow / advisory

This is the production decision plane.

### 4.3 Mechanism Layer

Top-level modules:

- `trueskill.py`
- `eomm.py`
- `dynamic_k.py`
- `pca_hidden.py`
- `gnn_synergy.py`
- `handicap.py`
- `entropy_match.py`
- `survival.py`
- `minimax_bp.py`

These modules are algorithmic primitives. Some are directly used by the SRE
pipeline; some remain more exploratory.

### 4.4 Interface / Runtime Layer

- `service/app.py`
- `cli.py`
- `bench/latency.py`
- `deploy/kubernetes/`
- `.github/workflows/ci.yml`

### 4.5 Learning / Persistence Layer

- `persistence/`
- `training/`

These components make the loop persistent and re-trainable.

## 5. Execution Flow

```text
decide(ctx)
  -> validate ctx
  -> circuit breaker gate
  -> per-service lock
  -> PCA stage
  -> GNN synergy stage
  -> adjusted probability stage
  -> entropy filter
  -> EOMM strategy choice
  -> Cox risk monitor
  -> policy resolution
  -> emit decision
  -> shadow/advisory boundary rewrite
  -> persist / log / metric
```

The important design rule is that scoring stages are not policy stages.
Policy lives in the final resolution step.

## 6. Mechanism Map

| # | Mechanism | Code | State / Input | Output |
| --- | --- | --- | --- | --- |
| 1 | TrueSkill | `trueskill.py`, `observe_release()` | `mu`, `sigma`, win/loss outcome | updated service reliability |
| 2 | EOMM | `eomm.py`, `_stage_eomm()` | history + candidate configs | chosen release strategy |
| 3 | Dynamic K | `dynamic_k.py`, `_stage_adjusted_probs()` | streak length | dynamic stake / decay |
| 4 | PCA | `pca_hidden.py`, `_stage_pca()` | telemetry vector | compressed hidden score |
| 5 | GNN synergy | `gnn_synergy.py`, `_stage_synergy()` | dependency graph | synergy score |
| 6 | Handicap Elo | `handicap.py`, `_stage_adjusted_probs()` | streak + canary fraction | adjusted success probability |
| 7 | Entropy filter | `entropy_match.py`, `_stage_entropy()` | candidate probabilities | filtered candidate set |
| 8 | Cox survival | `survival.py`, `_stage_risk()` | risk feature vector | incident probability + level |
| 9 | Minimax | `minimax_bp.py` | optional strategy game | mixed strategy / decision aid |

## 7. Production vs Research

### Production-shaped

- `core/`
- `sre/self_iteration.py`
- `persistence/`
- `service/app.py`
- `training/`
- `docs/adr`
- `docs/runbooks`
- `tests/`

### Research-shaped

- `minimax_bp.py` as a reusable strategy primitive, not a core runtime dependency
- `pipeline.py` legacy game demo
- `gnn_synergy.py` as a lightweight explicit GNN rather than a learned graph service
- `eomm.py` and `survival.py` fallback paths before full artifact hydration

## 8. Task Breakdown

### Epic A: Control Plane

- freeze `DecisionKind` and trace schema
- keep config typed and validated
- keep logs, metrics, and traces aligned
- ensure deterministic seeding

### Epic B: Decision Pipeline

- keep stage boundaries explicit
- keep policy resolution pure
- encode critical-tier and freeze-window hard rules
- preserve all fallback annotations in trace

### Epic C: Persistence and Replay

- persist services, observations, synergy, decisions
- support replay from trace + config + seed
- define a golden corpus for regression

### Epic D: Training and Artifacts

- train retention and Cox models from stored observations
- serialize model artifacts with version metadata
- hydrate runtime from persisted artifacts

### Epic E: Runtime Surfaces

- CLI for direct decisioning
- HTTP service for integration
- benchmark for latency budget
- Kubernetes and CI for deployment confidence

### Epic F: Knowledge and Ops

- ADR for why each design exists
- runbooks for failure modes
- HTML knowledge base for module-by-module explanation

## 9. Refinement Targets

1. Make runtime artifact loading explicit for trained models.
2. Split `policy` into a pure policy engine module if the decision tree grows.
3. Add cross-process locking if the system moves beyond one writer.
4. Add golden replay fixtures for every meaningful decision kind.
5. Clearly tag research-only modules in docs and packaging metadata.
6. Make model versioning part of the trace and persisted decision record.

## 10. Boundary Conditions

- Empty candidates must fail fast.
- Invalid candidate-service pairing must fail fast.
- Freeze window must override score-based optimism.
- Exhausted error budget must bias to rollback / hold.
- Unfit PCA / Cox / retention models must degrade deterministically.
- Shadow mode must not silently mutate trace without annotation.

## 11. Recommended Next Step

The next useful increment is to make the runtime artifact story first-class:

- version the trained retention and Cox outputs
- load them in the runtime pipeline
- record artifact version in trace and decision persistence

That closes the loop between observations, training, and enforcement.

See also:

- [`docs/state-lifecycle.md`](state-lifecycle.md)
- [`docs/module-contracts.md`](module-contracts.md)
- [`docs/adr/0006-runtime-artifact-versioning.md`](adr/0006-runtime-artifact-versioning.md)
- [`docs/implementation-roadmap.md`](implementation-roadmap.md)
