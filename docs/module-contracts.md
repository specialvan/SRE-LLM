# Module Contracts and Readiness

This document goes one level deeper than the architecture overview. It
describes what each module owns, which state it mutates, how it fails,
and whether it is production-shaped or still exploratory.

## 1. Reading Order

1. `core/` and `sre/domain.py`
2. `sre/self_iteration.py`
3. persistence and training
4. the 9 mechanism modules
5. runtime surfaces and docs

## 2. Control Plane Contracts

| Module | Owns | Inputs | Outputs | Failure mode | Readiness |
| --- | --- | --- | --- | --- | --- |
| `core/config.py` | typed config | dict / JSON / path | `AppConfig` | `ConfigError` | production |
| `core/errors.py` | exception taxonomy | any failure | typed exception | explicit code + details | production |
| `core/logging.py` | JSONL logging | events / fields | structured log lines | sink failure | production |
| `core/metrics.py` | in-process metrics | counter/gauge/histogram calls | Prometheus text / snapshots | invalid labels / NaN | production |
| `core/tracing.py` | correlation ids / spans | logical execution context | span events | context loss | production |
| `core/random.py` | deterministic randomness | root seed + name | stable RNGs | none if seed valid | production |
| `core/protocols.py` | interface seams | typed collaborators | runtime-checkable protocols | protocol mismatch | production |

## 3. Domain Contracts

| Module | Owns | Inputs | Outputs | Failure mode | Readiness |
| --- | --- | --- | --- | --- | --- |
| `sre/domain.py` | decision DTOs | service / candidate / context | `Decision` | validation errors | production |
| `sre/self_iteration.py` | end-to-end decisioning | context + state + config | decision + trace | guarded fallback / escalation | production |
| `sre/locking.py` | per-service serialization | service id | exclusive critical section | timeout | production |
| `sre/leases.py` | process writer ownership | lease file / owner / TTL | single-writer lease | `LeaseNotAcquiredError` | production |
| `sre/circuit.py` | breaker state machine | success/failure signals | allow / deny / snapshot | open state | production |
| `sre/shadow.py` | rollout mode boundary | mode flag | rewritten or advisory decision | invalid mode | production |
| `sre/primitives.py` | transferable primitive catalog | nine mechanism definitions | reusable SRE capability map | missing lookup | production |

## 4. Mechanism Contracts

The mechanism modules are also exposed as reusable SRE control primitives
in `sre/primitives.py`. The primitive catalog intentionally names the
engineering capability, not just the mathematical mechanism, so the same
pattern can be moved to alert triage, capacity decisions, and rollback
control.

### 4.1 TrueSkill

- File: `trueskill.py`
- Input: current ratings + match result
- Output: updated `mu`, `sigma`, streaks
- State mutated: service reliability state
- Fallback: cold start prior
- Readiness: production-shaped

### 4.2 EOMM

- File: `eomm.py`
- Input: history + candidate config set
- Output: chosen candidate / retention score
- State mutated: model weights when trained
- Fallback: rule-based scoring in the runtime pipeline
- Readiness: mixed, runtime-safe but partly research-backed

### 4.3 Dynamic K

- File: `dynamic_k.py`
- Input: streak length
- Output: adaptive K factor
- State mutated: none
- Fallback: deterministic closed form
- Readiness: production-shaped

### 4.4 PCA Hidden Score

- File: `pca_hidden.py`
- Input: telemetry matrix
- Output: compressed latent score
- State mutated: PCA basis
- Fallback: degraded stage trace when unfit
- Readiness: production-shaped

### 4.5 GNN Synergy

- File: `gnn_synergy.py`
- Input: dependency graph + node features
- Output: synergy embedding / pair score
- State mutated: adjacency-derived embeddings
- Fallback: skip when graph is too small or sparse
- Readiness: mixed, explicit and auditable but still lightweight

### 4.6 Handicap Elo

- File: `handicap.py`
- Input: streak / penalty context
- Output: adjusted expected win rate
- State mutated: none
- Fallback: standard Elo behavior when penalty is low
- Readiness: production-shaped

### 4.7 Entropy Filter

- File: `entropy_match.py`
- Input: candidate probabilities
- Output: filtered / ranked candidate set
- State mutated: none
- Fallback: highest-entropy candidate when all are below threshold
- Readiness: production-shaped

### 4.8 Cox Survival

- File: `survival.py`
- Input: risk features
- Output: risk probability + warn/alarm level
- State mutated: fitted Cox coefficients
- Fallback: pessimistic logistic heuristic
- Readiness: mixed, production-shaped runtime with research-grade fit loop

### 4.9 Minimax BP

- File: `minimax_bp.py`
- Input: payoff matrix
- Output: mixed strategy + game value
- State mutated: none
- Fallback: none; failures are explicit
- Readiness: research / auxiliary

## 5. Persistence Contracts

| Store | Owns | Notes |
| --- | --- | --- |
| `ServiceRepository` | service belief state | source of truth for hydrated runtime services |
| `SynergyRepository` | co-release graph | dependency memory |
| `ObservationRepository` | audit log + training corpus | replay and retraining source |
| `PipelineStore` | repository bundle | runtime bootstrapping unit |

Current implementations:

- `memory.py` for tests and dry-runs
- `sqlite.py` for durable local / small deployment use

## 6. Training Contracts

| Trainer | Input | Output | Runtime effect |
| --- | --- | --- | --- |
| `training/retention.py` | observations | retention artifact | replaces or calibrates EOMM weights |
| `training/cox.py` | observations | Cox artifact | replaces or calibrates risk monitor |

The runtime should always know whether it is using:

- fitted artifact
- fallback heuristic
- uninitialized model

That identity should be visible in trace and persistence.

## 7. Runtime Surface Contracts

| Surface | Purpose | Contract |
| --- | --- | --- |
| `service/app.py` | HTTP entry point | JSON request in, typed decision or error out |
| `cli.py` | operator / test entry point | file or stdin in, decision JSON out |
| `bench/latency.py` | latency verification | p50 / p95 / p99 budget reporting |
| `deploy/kubernetes/` | deployment shape | config, service, cronjob, volume, probes |

## 8. Readiness Summary

### Production-shaped today

- control plane
- domain model
- persistence
- HTTP / CLI / benchmark surface
- docs / ADR / runbooks

### Mixed

- EOMM
- Cox survival
- GNN synergy

### Research / auxiliary

- minimax BP
- legacy `pipeline.py`

## 9. What to Refine Next

1. Thread artifact version metadata through trace and persisted decisions.
2. Add an explicit runtime artifact loader for retention and Cox.
3. Record fallback mode in every stage payload.
4. Add a small golden replay corpus for one happy path, one fallback
   path, and one escalation path.
