# Lease Readiness Boundary

This page summarizes how local writer lease failures affect HTTP health and traffic routing.

## Contract

| Endpoint / behavior | Meaning |
|---|---|
| `/healthz` | Process health only. It can remain 200 after lease refresh failure. |
| `/readyz` | Serving readiness. It includes lease health and returns 503 after lease refresh failure. |
| `/v1/decide` / `/v1/observe` | Not directly blocked by lease loss in the handler. Traffic drain is delegated to the orchestrator through readiness. |
| `FileLease` | Local-filesystem coordination only. It is not a distributed multi-writer lock. |

## Why readiness, not direct request blocking?

The service boundary is designed for orchestrator-driven traffic drain:

1. `LeaseRefreshLoop` fails to refresh the local lease.
2. The configured `on_failure` callback calls `DecisionApp.mark_lease_unhealthy()`.
3. The app increments `gan_lease_refresh_failures_total{reason=...}`.
4. The app emits `lease.refresh.failed` with lease path, owner, and error type.
5. `/readyz` returns 503 with `reason=lease_unhealthy`.
6. The orchestrator removes the pod from service endpoints.

This keeps `/healthz` useful for distinguishing process liveness from serving safety.

## Deployment boundary

Current production assumption:

```text
SQLite + local FileLease + single writable replica
```

`FileLease` does not solve cross-node multi-writer coordination. If deployment needs multiple writable replicas, add an external lease/backend and document it with a new ADR, for example:

```text
Kubernetes Lease + leader-only writes
PostgreSQL advisory lock + external DB
Redis lease + external state store
```

## Observability

Metrics:

```text
gan_lease_refresh_failures_total{reason}
gan_breaker_state
```

Logs:

```text
lease.refresh.failed
```

HTTP assertions:

```text
/readyz -> 503, status=not_ready, reason=lease_unhealthy
/healthz -> 200, status=ok
```

## Tests

Primary tests:

- `tests/test_leases.py::test_refresh_failure_*`
- `tests/test_http_service.py::test_readyz_http_reflects_lease_failure`

Focused command:

```bash
python -m pytest tests/test_leases.py tests/test_http_service.py -q
```

## Source docs

- [`docs/architecture/06-concurrency-and-leases.md`](../docs/architecture/06-concurrency-and-leases.md)
- [`docs/architecture/04-state-and-failure-domains.md`](../docs/architecture/04-state-and-failure-domains.md)
- [`docs/architecture/07-observability-contract.md`](../docs/architecture/07-observability-contract.md)
- [`docs/adr/0007-single-writer-lease-boundary.md`](../docs/adr/0007-single-writer-lease-boundary.md)
