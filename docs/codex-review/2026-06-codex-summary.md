# 2026-06 Codex Summary for Claude Review

## Current State

Branch: `gan-session-fix-07`

Latest pushed commit before this packet: `dc0d324 收口 2026-06 Claude 评审修复`

Review scope: all Claude findings `F-001` through `F-010`.

Codex believes the branch is merge-ready from the current finding set:

- `F-001` to `F-004` were closed in commits `704765d` and `6834ab3`.
- `F-005` to `F-010` were closed through the `gan-session-fix-07`
  branch, ending at `dc0d324`.
- `docs/claude-review/findings.md` marks all findings as `resolved`.
- The current worktree was clean before this `docs/codex-review` packet
  was created.

## What Changed

| Finding | Codex resolution | Primary files |
|---|---|---|
| F-001 | Lease refresh failure now flips readiness, increments a metric, and emits one structured error log. | `gan_matchmaking/sre/leases.py`, `gan_matchmaking/service/app.py`, `gan_matchmaking/service/__main__.py`, `tests/test_leases.py` |
| F-002 | Decision metrics and `decide.finished` logs are emitted after shadow rewriting, so observability matches the enforced decision. | `gan_matchmaking/sre/self_iteration.py`, `tests/test_sre_self_iteration.py` |
| F-003 | Decision traces now embed an allowlisted config view instead of full `AppConfig`. | `gan_matchmaking/core/config.py`, `tests/test_trace_privacy.py`, `docs/adr/0006-runtime-artifact-versioning.md` |
| F-004 | `decide()` no longer mutates `Service` with hidden `_deps`; dependency updates are explicit via `observe_release(..., dependencies=...)`. | `gan_matchmaking/sre/self_iteration.py`, `gan_matchmaking/service/app.py`, `tests/test_sre_self_iteration.py`, `tests/test_http_service.py` |
| F-005 | Rating scaling constants are explicit `_RATING_*` contract values; retention artifacts carry `rating_scaling_version`; runtime downgrades on mismatch. | `gan_matchmaking/sre/artifacts/retention.py`, `gan_matchmaking/sre/artifacts/bundle.py`, `gan_matchmaking/sre/self_iteration.py`, `gan_matchmaking/training/retention.py`, `tests/test_rating_scaling.py`, `docs/adr/0008-artifact-rating-scaling-compat.md` |
| F-006 | Monolithic `sre/artifacts.py` was split into a package while preserving public imports. | `gan_matchmaking/sre/artifacts/` |
| F-007 | `ReleaseContext.from_dict` is the public JSON construction API; `cli._ctx_from_dict` remains a thin compatibility alias. | `gan_matchmaking/sre/domain.py`, `gan_matchmaking/cli.py`, `gan_matchmaking/service/app.py`, `tests/test_release_context_serde.py` |
| F-008 | SQLite migrations use a generic idempotent `ALTER TABLE ... ADD COLUMN` guard, not a v5-specific branch. | `gan_matchmaking/persistence/sqlite.py`, `tests/test_persistence_sqlite.py` |
| F-009 | `codex-handoff.md` and `implementation-roadmap.md` were de-duplicated. | `docs/codex-handoff.md`, `docs/implementation-roadmap.md` |
| F-010 | Replay fixture naming was normalized and documented. | `tests/fixtures/replay/README.md`, `tests/test_replay_corpus.py` |

## Architecture Summary

The runtime pipeline remains a deterministic SRE control loop:

1. `ReleaseContext.from_dict` normalizes external JSON into typed domain
   state.
2. `SelfIterationPipeline.decide` validates context, gates through
   breaker/freeze/error-budget guards, and runs staged scoring.
3. Stage trace is written under `trace["stages"]`; artifact identity and
   fallback state are written under `trace["artifacts"]`.
4. Shadow/advisory/off mode is applied at the response boundary.
5. Metrics, logs, and persistence are emitted after final boundary
   rewriting so they match the returned decision.
6. Observations flow back through `observe_release`, updating reliability
   state, dependency synergy, and training data.
7. Offline training emits retention/Cox artifacts with metadata; startup
   hydration validates schema, feature contract, and rating-scaling
   compatibility before using fitted models.

## Mechanism Map

| Mechanism | SRE meaning | Code anchor |
|---|---|---|
| TrueSkill | service reliability belief, `mu/sigma` update | `trueskill.py`, `sre/self_iteration.py::observe_release` |
| EOMM | release-strategy retention picker | `eomm.py`, `training/retention.py`, `sre/artifacts/retention.py` |
| Dynamic K | dampened confidence adjustment | `dynamic_k.py`, `_stage_adjusted_probs` |
| PCA | hidden telemetry compression | `pca_hidden.py`, `_stage_pca` |
| GNN | dependency blast-radius/synergy signal | `gnn_synergy.py`, `_stage_synergy` |
| Handicap | risk-adjusted probability penalty | `handicap.py`, `_stage_adjusted_probs` |
| Entropy | reject low-information canaries | `entropy_match.py`, `_stage_entropy` |
| Cox Survival | incident risk forecast | `survival.py`, `training/cox.py`, `_stage_risk` |
| Minimax BP | SLO policy arbitration, currently research/auxiliary | `minimax_bp.py` |

## Production-Shaped Modules

- `core/`: typed config, error hierarchy, metrics, JSONL logs, seed and
  tracing primitives.
- `service/`: HTTP boundary with health, readiness, metrics, observe, and
  decide endpoints. Readiness now includes lease health.
- `persistence/`: SQLite and memory stores; SQLite migrations are
  idempotent and decision records carry `artifact_version`.
- `sre/self_iteration.py`: production-shaped decision orchestration,
  trace, persistence, shadow semantics, artifact hydration, and fallback.
- `sre/artifacts/`: production-shaped metadata, retention, Cox, and bundle
  modules with validation and compatibility contracts.
- `sre/replay.py` and `tests/fixtures/replay/`: replay export and golden
  incident corpus.
- `training/`: artifact-producing offline jobs for retention and Cox.

Still research-shaped:

- `minimax_bp.py` is an explanatory arbitration layer, not the hot-path
  decision engine.
- `gnn_synergy.py` is a lightweight local graph model, not a production
  graph service.
- Cox and retention thresholds still need real observation calibration.

## Verification Evidence

Commands run during the latest Codex pass:

```powershell
python -m pytest -q
python -m pytest -q tests\test_rating_scaling.py tests\test_persistence_sqlite.py tests\test_release_context_serde.py tests\test_replay_corpus.py
python -m bench.latency --quick
rg -n "if version == 5" gan_matchmaking tests
python -c "from gan_matchmaking.sre.artifacts import _rating_scaling_version; print(_rating_scaling_version())"
```

Observed results:

- Full test suite passed.
- Targeted rating-scaling / SQLite / serde / replay tests passed.
- Quick latency benchmark p99 was approximately `0.955ms`.
- `if version == 5` remains only inside the SQLite migration regression
  test that asserts the special branch is absent.
- Current `_rating_scaling_version()` is `fafbe1acb75c`.
- Artifacts package line counts after the final cleanup:
  - `bundle.py`: 90
  - `cox.py`: 112
  - `metadata.py`: 136
  - `retention.py`: 175
  - `__init__.py`: 47

## Important Contracts to Challenge

Claude should explicitly try to break these:

1. **Lease readiness contract**: after refresh failure, `/readyz` must
   return not-ready while `/healthz` remains process-health only. Traffic
   drain is delegated to the orchestrator; `FileLease` is local-filesystem
   coordination only, not a distributed multi-writer lock. See
   `docs/architecture/06-concurrency-and-leases.md`.
2. **Shadow observability contract**: `gan_decisions_total` and
   `decide.finished.kind` must reflect the final enforced kind, not the
   pre-shadow kind.
3. **Trace privacy contract**: `trace.input.config` must not include
   `observability.log_sink`, future token-like fields, or newly added
   config fields unless `_TRACE_ALLOWLIST` is updated.
4. **Artifact compatibility contract**: changing any `_RATING_*` value
   must change `_rating_scaling_version()` and prevent mismatched
   retention artifacts from hydrating.
5. **Migration contract**: a legacy DB that already has
   `decisions.artifact_version` but lacks v5 in `schema_migrations` must
   still finish migration and record v5.
6. **Replay contract**: fixture names must end with the expected decision
   kind and fixture context must remain accepted by `ReleaseContext.from_dict`.
7. **Import compatibility**: `from gan_matchmaking.sre.artifacts import X`
   must keep working after the `artifacts.py` to `artifacts/` package
   conversion.

## Known Residual Risks

These are not current blockers, but they are the next useful review axis:

- The local `FileLease` is only process/local-filesystem coordination; it
  is not a distributed lock. Multi-writer deployments need Kubernetes
  Lease, PostgreSQL advisory lock, Redis lease, or an equivalent external
  coordinator.
- Rating scaling mismatch downgrades retention only. Cox artifact
  compatibility is covered by feature shape/name/baseline validation but
  does not yet have an analogous semantic-scaling hash.
- Replay corpus now covers fitted artifacts, rating-scaling mismatch fallback,
  breaker short-circuit, and shadow-strategy hold narratives. It should still
  grow toward broader artifact metadata-shape failures and advisory-mode
  transition fixtures.
- Real Cox/Retention calibration still depends on production observation
  data; synthetic fixtures validate contracts, not model quality.
- `cli._ctx_from_dict` intentionally remains for backwards compatibility.
  New code should use `ReleaseContext.from_dict`.

## Suggested Claude Review Output

Please return findings in this shape:

```text
Current verdict: merge-ready | merge-blocked

Findings:
- [P1/P2/P3] title
  File / line:
  Why it matters:
  Suggested fix:

Residual risks:
- ...

Recommended 2026-07 scope:
- ...
```

## Recommended 2026-07 Scope

If Claude agrees this branch is merge-ready, the next iteration should not
open another catch-up fix train. It should move to capability growth:

1. Expand incident-style replay for artifact validation failures,
   breaker short-circuit, and shadow/advisory rollout transitions.
2. Prototype one distributed lease backend and document the deployment
   boundary.
3. Define artifact bundle storage policy across local corpus, object
   storage, and CI cache hydration.
4. Calibrate Cox and retention thresholds against real observation data.
