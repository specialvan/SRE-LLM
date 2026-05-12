# ADR-0008 · Artifact rating scaling compatibility

Date: 2026-05-12
Status: Accepted
Related: F-005, F-006

## Context

`_service_player` / `_candidate_player` in
`gan_matchmaking/sre/artifacts/retention.py` convert SRE reliability
state (`Service` + `ReleaseCandidate`) into Elo-scale
`Player(mu, sigma)` ratings. These Player objects feed `build_match_config`
which in turn drives EOMM feature construction at both training time
(inside `training/retention.py`) and runtime (inside
`SelfIterationPipeline._decide_locked`).

Historically the mapping used inline magic numbers:

```python
mu = 25.0 + 18.0 * (service.mu - 0.5) + 1.5 * win_streak - 1.0 * loss_streak
sigma = max(1.0, 5.0 + 10.0 * service.sigma + 0.5 * loss_streak)
```

There was no explicit contract linking the constants used at training
time to the constants used at runtime. A well-intentioned refactor of
either side would silently shift the trained retention weights away from
the input space they were fitted on. The symptom would be drift in
decision quality rather than a loud crash.

## Decision

1. All rating scaling constants are promoted to module-level
   `_RATING_*` named constants in
   `gan_matchmaking/sre/artifacts/retention.py`. Each constant carries a
   comment documenting its effect and the invalidation semantics.
2. `_rating_scaling_version()` returns a stable 12-hex SHA-256 prefix
   hash over the `_RATING_*` payload. The value bumps whenever any
   constant changes.
3. `training/retention.py` writes the current hash into
   `ArtifactMetadata.extra["rating_scaling_version"]` at every new
   retention artifact produced.
4. `SelfIterationPipeline._hydrate_runtime_artifacts` refuses to hydrate
   a retention artifact whose declared version differs from the
   runtime's current `_rating_scaling_version()`. On mismatch:
   - emit a `WARNING` level `artifacts.retention.scaling_mismatch` log
     with `expected` / `actual` / `artifact_version` fields
   - replace the runtime artifact bundle with
     `bundle.with_scaling_status("mismatch")`, which drops the retention
     artifact so the pipeline falls back to the bootstrap path
5. Legacy artifacts predating this ADR (no
   `rating_scaling_version` key) are marked
   `rating_scaling_status="unknown"` but still loaded; operators see the
   marker in `trace["artifacts"]["rating_scaling_status"]` and can
   retrain at their discretion.

## Consequences

- Changing any `_RATING_*` constant is now an explicit breaking change
  that invalidates every deployed retention artifact. Retrain + release.
- The snapshot test `test_rating_scaling_contract_snapshot` (in
  `tests/test_rating_scaling.py`) catches accidental drift with a
  byte-level assertion on computed `(mu, sigma)` outputs.
- Review gate: PRs touching `_RATING_*` must include a note stating
  whether existing retention artifacts will be retrained, linked to this
  ADR.
- The runtime artifact trace always carries a `rating_scaling_status`
  indicator (`"match"` / `"mismatch"` / `"unknown"`). Operators can
  dashboard on the `"mismatch"` / `"unknown"` counts to detect
  outstanding artifact-rollout hygiene issues.

## Related: What must never enter trace

(Carried forward from ADR-0006.) Independent of model artifacts, the
trace itself is an audit surface. `AppConfig.to_trace_dict()` enforces
an allowlist so URLs, tokens, PII, log sink paths, and any
config field added after ADR-0006 without an explicit privacy-review
note are never embedded.
