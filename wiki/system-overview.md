# System Overview

This project is an auditable SRE rollout decision engine. One `decide(ctx)` call turns release context, service state, telemetry, artifacts, and policy into a `Decision` plus replayable trace.

## Core contract

```text
ReleaseContext -> SelfIterationPipeline.decide(ctx) -> Decision(kind, chosen_id, rationale, trace)
```

The system optimizes for four properties:

1. **Algorithmic decisions** — decision kind is produced by deterministic stages and policy rules.
2. **Auditable evidence** — trace records inputs, stage outputs, artifact identity, and short-circuit reasons.
3. **Replayability** — SQLite decisions and JSON fixtures can reproduce behavior.
4. **Recoverability** — invalid artifacts, open breakers, freezes, and budget exhaustion degrade to explicit safe outcomes.

## Decision kinds

```text
go | canary | hold | rollback | escalate
```

The final emitted kind is after shadow/advisory wrapping, so metrics and logs reflect enforced behavior.

## Runtime stages

| Stage | Purpose | Important trace fields |
|---|---|---|
| Validate | Reject invalid context before decision. | no decision on failure |
| Guard clauses | Freeze and exhausted budget short-circuit. | empty `trace.stages` |
| Circuit breaker | Open breaker returns `escalate`. | `trace.circuit_breaker` |
| PCA | Compress telemetry into fused reliability score. | `stages.pca.fused` |
| Synergy | Score dependency graph influence. | `stages.synergy.score` |
| Adjusted probs | Apply dynamic K and handicap. | `stages.adjusted_probs.probs` |
| Entropy | Keep information-bearing candidates. | `stages.entropy.acceptable_idx` |
| EOMM | Choose candidate via artifact or fallback scoring. | `stages.eomm.source`, `chosen_id` |
| Risk | Cox/fallback incident risk. | `stages.risk.prob`, `level` |
| Policy | Resolve final decision kind. | final `Decision.kind` |
| Shadow wrap | Apply `off`, `advisory`, or `shadow`. | `trace.shadow_mode` |

## Current safety boundaries

- `FileLease` is local-filesystem coordination only, not distributed consensus.
- Lease refresh failure affects `/readyz`; `/healthz` remains process liveness.
- Runtime artifact validation can downgrade to bootstrap without blocking process startup.
- Replay validation is stricter than runtime for fitted artifacts: it rejects bundles runtime would downgrade.
- Artifact config filenames are basename-only to prevent path traversal.

## Main source docs

- [`docs/architecture/README.md`](../docs/architecture/README.md)
- [`docs/architecture/02-decision-flow.md`](../docs/architecture/02-decision-flow.md)
- [`docs/architecture/03-trace-schema.md`](../docs/architecture/03-trace-schema.md)
- [`docs/architecture/04-state-and-failure-domains.md`](../docs/architecture/04-state-and-failure-domains.md)
- [`docs/architecture/07-observability-contract.md`](../docs/architecture/07-observability-contract.md)
