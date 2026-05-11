# ADR-0007 - Single-writer lease boundary

Status: Accepted
Date: 2026-05-11

## Context

The current production-shaped store is SQLite. That is appropriate for a
small deployment and for easy on-call inspection, but it is still a single
writable state file. The in-process `PerServiceLock` only serialises
threads in one Python process; it cannot protect against two HTTP servers
writing the same SQLite file from separate processes or pods.

Without an explicit lease boundary, a rollout mistake could create
split-brain decision writers:

- two processes update the same service reliability state;
- both append decision audit rows with competing assumptions;
- replay and training data become harder to trust.

## Decision

1. Keep `PerServiceLock` as the per-service in-process mutex.
2. Add `sre.leases.FileLease` as a process-level single-writer guard for
   local / single-node / ReadWriteOnce PVC deployments.
3. Wire the HTTP service entry point to optionally acquire and refresh that
   lease with `GAN_LEASE_FILE`.
4. Keep Kubernetes at `replicas: 1` and `strategy: Recreate` while using
   SQLite.
5. Treat true horizontal scale as a separate architecture: distributed
   lease plus external database, not just more pods.

## Consequences

- **+** Accidental duplicate local writers fail fast.
- **+** Crash recovery is possible because the lease has a TTL and can be
  taken over after expiry.
- **+** The lease interface gives future Redis / etcd / PostgreSQL advisory
  lock implementations a clear insertion point.
- **-** `FileLease` is not a distributed consensus primitive and should not
  be used to justify multi-writer scale.
- **-** Operators need to tune TTL and rollout timing so stale leases do not
  delay recovery longer than intended.
