# Module Map

This page maps operational contracts to implementation and tests. Use it to find the right files before changing behavior.

## Runtime decision path

| Area | Implementation | Tests | Docs |
|---|---|---|---|
| Decision pipeline | `gan_matchmaking/sre/self_iteration.py` | `tests/test_sre_self_iteration.py`, `tests/test_replay_corpus.py` | `docs/architecture/02-decision-flow.md` |
| Core config | `gan_matchmaking/core/config.py` | `tests/test_core_config.py` | `docs/architecture/03-trace-schema.md` |
| HTTP surface | `gan_matchmaking/service/app.py` | `tests/test_http_service.py` | `docs/architecture/06-concurrency-and-leases.md` |
| CLI | `gan_matchmaking/cli.py` | CLI/export tests in replay suites | `docs/codex-handoff.md` |
| Benchmarks | `bench/latency.py` | `tests/test_latency_benchmark.py` | `docs/architecture/02-decision-flow.md` |

## Artifacts and replay

| Area | Implementation | Tests | Docs/wiki |
|---|---|---|---|
| Artifact package public API | `gan_matchmaking/sre/artifacts/__init__.py` | `tests/test_artifacts_public_api.py` | `wiki/artifact-replay-contracts.md` |
| Artifact bundle validation/archive | `gan_matchmaking/sre/artifacts/bundle.py` | `tests/test_replay_export.py` | `docs/architecture/05-artifact-lifecycle.md` |
| Retention compatibility | `gan_matchmaking/sre/artifacts/retention.py` | `tests/test_rating_scaling.py` | `wiki/artifact-replay-contracts.md` |
| Replay export/validation | `gan_matchmaking/sre/replay.py` | `tests/test_replay_export.py`, `tests/test_replay_corpus.py` | `wiki/replay-corpus.md` |
| Replay fixtures | `tests/fixtures/replay/*.json` | `tests/test_replay_corpus.py` | `tests/fixtures/replay/README.md` |

## State, leases, and readiness

| Area | Implementation | Tests | Docs/wiki |
|---|---|---|---|
| SQLite audit/state | `gan_matchmaking/persistence/sqlite.py` | state/replay tests | `docs/architecture/04-state-and-failure-domains.md` |
| Local leases | `gan_matchmaking/sre/leases.py` | `tests/test_leases.py` | `docs/architecture/06-concurrency-and-leases.md` |
| HTTP readiness | `gan_matchmaking/service/app.py` | `tests/test_http_service.py` | `wiki/lease-readiness-boundary.md` |

## Frontend and static UI

| Area | Implementation | Tests | Docs/wiki |
|---|---|---|---|
| Documentation UI shell | `docs/assets/knowledge-modern.css`, `docs/assets/knowledge-modern.js` | `tests/test_docs_static_ui.py` | `wiki/frontend-static-ui.md` |
| Knowledge pages | `docs/knowledge_base.html`, `docs/V2_Knowledge/knowledge-base.html`, `docs/V3_Knowledge/knowledge-base.html` | `tests/test_docs_static_ui.py` | `wiki/frontend-static-ui.md` |
| Runtime dashboard assets | `gan_matchmaking/service/static/*`, `gan_matchmaking/service/assets.py` | `python -m pytest tests/test_http_service.py -k dashboard -q` | `wiki/frontend-static-ui.md` |
| Dashboard state API | `gan_matchmaking/service/app.py::handle_dashboard_state` | `python -m pytest tests/test_http_service.py -k dashboard_state -q` | `wiki/frontend-static-ui.md` |

## Review and planning docs

| Purpose | File |
|---|---|
| Current implemented artifact/replay refinement summary | `docs/codex-review/CLAUDE_REFINED_SPEC.md` |
| Next executable spec expansion | `docs/claude-review/spec-v3/README.md` |
| Roadmap | `docs/implementation-roadmap.md` |
| Merge checklist | `wiki/review-merge-checklist.md` |

## Change routing

- Changing final decision behavior: update replay fixture(s), decision-flow docs, and observability docs.
- Changing trace fields: update trace schema docs and replay assertions.
- Changing artifacts: update artifact lifecycle docs and `wiki/artifact-replay-contracts.md`.
- Changing lease/readiness: update concurrency docs and `wiki/lease-readiness-boundary.md`.
- Changing fixture corpus: update `tests/fixtures/replay/README.md` and `wiki/replay-corpus.md`.
- Changing docs UI or runtime dashboard: update `wiki/frontend-static-ui.md` and the corresponding static UI tests.
