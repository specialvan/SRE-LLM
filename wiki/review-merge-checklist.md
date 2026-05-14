# Review and Merge Checklist

Use this checklist before opening or merging a PR that changes runtime decisions, artifacts, replay, readiness, or observability.

## Required checks

```bash
python -m pytest -q
python -m bench.latency --quick --p99-ms 50
```

When touching artifacts or replay, also run:

```bash
python -m pytest tests/test_rating_scaling.py tests/test_replay_corpus.py tests/test_replay_export.py tests/test_artifacts_public_api.py -q
```

When touching config, HTTP readiness, dashboard routes, or lease behavior, also run:

```bash
python -m pytest tests/test_core_config.py tests/test_http_service.py tests/test_leases.py -q
```

When touching static documentation UI assets, also run:

```bash
python -m pytest tests/test_docs_static_ui.py -q
```

## Contract checklist

- [ ] Decision trace schema remains auditable.
- [ ] Metrics/logs reflect final enforced decision kind.
- [ ] Shadow/advisory behavior is explicit in trace and metrics.
- [ ] Replay fixtures protect any new incident path.
- [ ] Fitted artifact replay bundles validate before export/archive.
- [ ] Artifact filename config remains basename-only.
- [ ] Legacy artifact behavior requires explicit opt-in when replay validation would otherwise reject it.
- [ ] Lease loss affects `/readyz`, not `/healthz` process liveness.
- [ ] No distributed multi-writer claims are made while using `FileLease`.

## Documentation checklist

Update docs when changing these areas:

| Change | Docs to update |
|---|---|
| Decision behavior or trace fields | `docs/architecture/02-decision-flow.md`, `docs/architecture/03-trace-schema.md` |
| Artifact format or validation | `docs/architecture/05-artifact-lifecycle.md`, `wiki/artifact-replay-contracts.md` |
| Replay corpus | `tests/fixtures/replay/README.md`, `wiki/replay-corpus.md` |
| Lease/readiness | `docs/architecture/06-concurrency-and-leases.md`, `wiki/lease-readiness-boundary.md` |
| Metrics/log events | `docs/architecture/07-observability-contract.md` |
| Runtime dashboard or docs UI | `README.md`, `wiki/operations-runbook.md`, `docs/assets/` |
| Roadmap/scope | `docs/implementation-roadmap.md`, `docs/codex-review/CLAUDE_REFINED_SPEC.md` |

## Evidence recording

Record dated validation evidence in the PR or release note after running the commands above. Treat this checklist as the command source of truth, not as a durable pass/fail ledger.
