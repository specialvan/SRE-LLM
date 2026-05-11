# Runbook - Multi-instance lease boundary

**When to use**: before changing replica count, moving the state store, or
debugging startup failures with `gan.lease.not_acquired`.

## Current safe mode

The supported SQLite deployment is single writer:

- Kubernetes `replicas: 1`
- deployment strategy `Recreate`
- one SQLite state file
- optional local `GAN_LEASE_FILE` on the same state volume

The local file lease is a guardrail for accidental duplicate processes. It
is not a distributed lock.

## Startup checks

1. Confirm the service is using one state path:
   ```
   echo $GAN_STATE_DB
   echo $GAN_LEASE_FILE
   ```

2. If startup fails with `gan.lease.not_acquired`, inspect the lease file:
   ```
   cat $GAN_LEASE_FILE
   ```

3. Compare `expires_at` to current Unix time. If the holder is alive, do
   not delete the file. If the holder is gone and the lease has expired,
   restart the service and let it take over.

4. If the file is corrupt, stop all writers before deleting it manually.

## Scaling rule

Do not scale the current SQLite deployment by changing only
`spec.replicas`.

Horizontal scale requires all three changes together:

1. external database for service state, observations, synergy, and decisions;
2. distributed lease or database advisory lock for writer ownership;
3. replay validation proving decisions remain deterministic under the new
   state boundary.

## Recommended external leases

- Kubernetes `Lease` object for one active writer in one cluster.
- PostgreSQL advisory lock when the state store moves to PostgreSQL.
- Redis `SET key token NX PX ttl` with token-checked release when Redis is
  already part of the SRE control plane.

Whichever backend is chosen, preserve the same semantics as
`sre.leases.FileLease`: owner identity, TTL, token-checked release, and
visible failure when ownership cannot be acquired.
