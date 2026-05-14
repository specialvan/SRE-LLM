# Replay Fixtures

Each file in this directory is a JSON snapshot of a decision replay used
by `tests/test_replay_corpus.py`. Snapshots have the shape::

    {
      "name": "<scenario>_<expected_kind>",
      "context": { ... ReleaseContext.from_dict input ... },
      "config": { ... AppConfig overrides (optional) ... },
      "shadow_mode": "off" | "shadow" | "advisory",   # optional
      "artifacts": { ... inline artifact payload (optional) ... },
      "artifact_bundle": { "path": "...", ... }   # alternative to "artifacts"
      "expected": {
        "kind": "go" | "canary" | "hold" | "rollback" | "escalate",
        "chosen_id": "...",
        "risk_level": "ok" | "warn" | "alarm",
        "artifact_version": "bootstrap" | "retention@..." | ...
      }
    }

## Naming convention

File name: `{scenario}_{expected_kind}.json`

- `{scenario}`: a short snake_case description of the trigger (e.g.
  `budget`, `fallback`, `freeze`, `critical_tier_downgrade`).
- `{expected_kind}`: the enforced `Decision.kind` value produced by the
  pipeline for this replay. Must be one of `go`, `canary`, `hold`,
  `rollback`, `escalate`.

The convention is enforced by `test_replay_corpus.py::test_fixture_naming_matches_convention`.

## Catalog

| File | Scenario | Expected kind |
|---|---|---|
| advisory_mode_rollback.json | Advisory mode keeps the rollback decision visible but annotates it as do-not-enforce | rollback |
| artifact_canary.json | Fitted retention artifact steers to canary | canary |
| artifact_metadata_missing_go.json | A fixture-local retention bundle missing metadata is treated as unversioned and falls back to bootstrap GO after manifest validation fails | go |
| artifact_scaling_mismatch_go.json | Stale retention scaling is rejected and falls back to bootstrap scoring | go |
| artifact_scaling_mismatch_warn_canary.json | Stale retention scaling is rejected during a WARN-risk rollout, and bootstrap fallback still enforces CANARY | canary |
| artifact_validation_failure_go.json | A fixture-local invalid retention manifest is rejected at runtime and replay falls back to bootstrap GO | go |
| breaker_open_escalate.json | Open circuit breaker short-circuits to human escalation | escalate |
| budget_rollback.json | Error budget exhausted → rollback posture | rollback |
| critical_tier_downgrade_canary.json | Critical-tier full rollout forced to canary | canary |
| fallback_go.json | No artifact + healthy service → bootstrap GO | go |
| freeze_hold.json | `freeze_window=true` pins HOLD regardless of signal | hold |
| risk_warn_canary.json | Cox survival WARN downgrades to canary | canary |
| shadow_mode_rollback_hold.json | Top-level shadow mode rewrites a rollback-ready decision to HOLD while keeping the suppressed kind in trace | hold |
| shadow_strategy_hold.json | `strategy="shadow"` → effectively HOLD | hold |
| unknown_strategy_escalate.json | Unknown strategy label → escalate to human | escalate |

## Adding a new fixture

1. Capture the fixture with `python -m gan_matchmaking.cli export-replay`
   (see `gan_matchmaking/sre/replay.py` for the schema).
2. Rename the output to match `{scenario}_{expected_kind}.json`.
3. Make sure `expected` matches the observed decision; the parametrised
   test picks up any new file automatically.
4. Update the catalog table above so reviewers can find the new case.
5. If the captured decision was emitted under `shadow` or `advisory`, preserve it with a top-level `shadow_mode` field so replay uses the same rollout boundary.
6. Exported fixtures automatically carry `expected.trace_values.shadow_mode`; when `shadow_mode="shadow"`, export also locks `expected.trace_values.shadow_suppressed_kind`.
7. `artifact_bundle.path` must be a relative directory path that stays under `tests/fixtures/replay/`; absolute paths and `..` escapes are rejected by the corpus harness.
8. Fixture-local artifact bundle directories must not contain symlink entries; the corpus harness rejects them before runtime hydration.
9. Do not set `config.artifacts.directory` directly in replay fixtures; use top-level `artifacts` or `artifact_bundle` so the harness can constrain paths.
