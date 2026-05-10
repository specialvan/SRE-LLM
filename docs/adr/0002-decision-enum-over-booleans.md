# ADR-0002 · Decision enum over booleans

Status: Accepted
Date: 2026-05-10

## Context

The first cut of the SRE pipeline returned a boolean "is it safe to
release?". Real SRE practice needs finer granularity: a release can be
safe but only as a 1% canary; it can be blocked not because of risk but
because of a change-freeze window; it can be unsafe enough that we have
to revert the live version.

## Decision

Introduce :class:`DecisionKind` with exactly five values:

1. `GO`       — full rollout.
2. `CANARY`   — ramp-up via a canary.
3. `HOLD`     — wait, gather more signal.
4. `ROLLBACK` — the live version is unhealthy; revert.
5. `ESCALATE` — pipeline could not decide → page a human.

Return a :class:`Decision` dataclass containing the kind, the chosen
candidate (or None), the risk level, the confidence, the free-form
rationale tokens, and the full audit trace.

## Consequences

- **+** Dashboards can count decisions per kind per service; this is the
  primary SLO for the self-iteration system itself.
- **+** The test suite can assert on kind, not on flags.
- **+** Explicit `ESCALATE` fail-open avoids the "silent HOLD" class of bugs.
- **−** Downstream consumers that assumed "bool" must be updated; migration
  is documented in `docs/runbooks/migrate-to-decision-enum.md`.
