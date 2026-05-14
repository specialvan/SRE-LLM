# GAN SRE Decision Wiki

This wiki is the project knowledge index. It does not replace `docs/`; it gives future reviewers and operators a short path to the current contracts, implementation anchors, replay fixtures, and verification commands.

Maintenance rule: update the source architecture or contract doc first, then update this wiki summary and the linked verification commands. Wiki pages should reuse terms already defined in `docs/` and must not introduce new runtime contracts on their own.

## Start here

| Topic | Read |
|---|---|
| System overview | [`System Overview`](system-overview.md), [`docs/architecture.md`](../docs/architecture.md), [`docs/architecture/README.md`](../docs/architecture/README.md) |
| Module ownership map | [`Module Map`](module-map.md) |
| Decision flow and trace | [`docs/architecture/02-decision-flow.md`](../docs/architecture/02-decision-flow.md), [`docs/architecture/03-trace-schema.md`](../docs/architecture/03-trace-schema.md) |
| Artifact lifecycle | [`docs/architecture/05-artifact-lifecycle.md`](../docs/architecture/05-artifact-lifecycle.md), [`Artifact Replay Contracts`](artifact-replay-contracts.md) |
| Replay corpus | [`Replay Corpus`](replay-corpus.md), [`tests/fixtures/replay/README.md`](../tests/fixtures/replay/README.md) |
| Lease/readiness boundary | [`docs/architecture/06-concurrency-and-leases.md`](../docs/architecture/06-concurrency-and-leases.md), [`Lease Readiness Boundary`](lease-readiness-boundary.md) |
| Operator runbook | [`Operations Runbook`](operations-runbook.md), [`Review and Merge Checklist`](review-merge-checklist.md) |
| Frontend/static UI | [`Frontend Static UI`](frontend-static-ui.md) |
| Observability | [`docs/architecture/07-observability-contract.md`](../docs/architecture/07-observability-contract.md) |
| Current refined pass | [`docs/codex-review/CLAUDE_REFINED_SPEC.md`](../docs/codex-review/CLAUDE_REFINED_SPEC.md) |
| Next roadmap | [`docs/implementation-roadmap.md`](../docs/implementation-roadmap.md) |

## Current branch knowledge snapshot

As of the current documentation pass, the key operational facts are:

1. **Retention rating-scaling compatibility is shared** between runtime hydration and replay validation.
2. **Replay validation rejects retention scaling mismatch** and rejects legacy `unknown` metadata unless the caller explicitly opts in.
3. **Modern fitted replay fixtures carry `rating_scaling_version`** and assert `trace.artifacts.rating_scaling_status == "match"`.
4. **Replay corpus includes incident narratives** for rating-scaling mismatch fallback and open circuit breaker escalation.
5. **Artifact filenames are basename-only** at both AppConfig and replay-validation boundaries.
6. **Lease refresh failure flips readiness, not process health**: `/readyz` becomes not-ready; `/healthz` remains process health only; orchestrator drains traffic.

## Verification commands

```bash
python -m pytest tests/test_rating_scaling.py tests/test_replay_corpus.py tests/test_replay_export.py tests/test_core_config.py tests/test_http_service.py tests/test_artifacts_public_api.py -q
python -m pytest -q
python -m bench.latency --quick --p99-ms 50
```

Run the verification commands above before merge and record dated evidence in the PR or release note rather than treating wiki status as durable truth.

## Wiki pages

- [`System Overview`](system-overview.md)
- [`Module Map`](module-map.md)
- [`Artifact Replay Contracts`](artifact-replay-contracts.md)
- [`Lease Readiness Boundary`](lease-readiness-boundary.md)
- [`Replay Corpus`](replay-corpus.md)
- [`Operations Runbook`](operations-runbook.md)
- [`Frontend Static UI`](frontend-static-ui.md)
- [`Review and Merge Checklist`](review-merge-checklist.md)
