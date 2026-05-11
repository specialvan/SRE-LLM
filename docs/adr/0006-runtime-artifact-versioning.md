# ADR-0006 - Runtime artifact versioning for trained models

Status: Accepted
Date: 2026-05-11

## Context

The SRE pipeline already has offline training paths for the EOMM retention
model and the Cox churn model. However, the runtime currently treats the
models as implementation details rather than versioned deployment
artifacts. That makes post-incident replay and rollout auditing harder:

- which exact model version was used?
- was the runtime using a fallback or a fitted artifact?
- did a decision change because of code or because of data?

Without explicit artifact versioning, the system cannot fully separate
code drift from data drift.

## Decision

1. Treat trained runtime models as first-class versioned artifacts.
2. Record artifact identity in the decision trace and in persisted
   decision records.
3. Prefer artifact hydration at pipeline startup over ad-hoc loading in
   the hot path.
4. Keep deterministic fallback behavior when no artifact is available.

Minimum artifact metadata:

- model name
- artifact version
- training timestamp
- source store or dataset window
- config hash
- git SHA or build identifier

## Consequences

- **+** Replays can distinguish code change from model change.
- **+** Operations can tell whether runtime is using a fitted model or a
  fallback.
- **+** Rollbacks can include model artifact rollback, not just code
  rollback.
- **-** More metadata must be stored and threaded through decision traces.

## Related: What must never enter trace

Independent of model artifacts, the decision trace is an audit surface.
`AppConfig.to_trace_dict()` enforces an explicit allowlist so the trace
never embeds fields by default when the runtime config grows.

The following classes of values must not enter trace payloads:

- API tokens, passwords, DSNs, credentials, or other secrets.
- PII, customer identifiers, tenant identifiers, or raw request bodies.
- URLs, hosts, network paths, and log sink paths that expose internal
  topology or local filesystem layout.
- Any config field added after this ADR unless `_TRACE_ALLOWLIST` is
  explicitly updated and reviewed.

Adding a field to `_TRACE_ALLOWLIST` requires a snapshot-test update and a
PR note explaining why the field is safe for long-lived audit logs.
