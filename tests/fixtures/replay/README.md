# Replay Fixtures

Each file in this directory is a JSON snapshot of a decision replay used
by `tests/test_replay_corpus.py`. Snapshots have the shape::

    {
      "name": "<scenario>_<expected_kind>",
      "context": { ... ReleaseContext.from_dict input ... },
      "config": { ... AppConfig overrides (optional) ... },
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
| artifact_canary.json | Fitted retention artifact steers to canary | canary |
| budget_rollback.json | Error budget exhausted → rollback posture | rollback |
| critical_tier_downgrade_canary.json | Critical-tier full rollout forced to canary | canary |
| fallback_go.json | No artifact + healthy service → bootstrap GO | go |
| freeze_hold.json | `freeze_window=true` pins HOLD regardless of signal | hold |
| risk_warn_canary.json | Cox survival WARN downgrades to canary | canary |
| shadow_strategy_hold.json | `strategy="shadow"` → effectively HOLD | hold |
| unknown_strategy_escalate.json | Unknown strategy label → escalate to human | escalate |

## Adding a new fixture

1. Capture the fixture with `python -m gan_matchmaking.cli export-replay`
   (see `gan_matchmaking/sre/replay.py` for the schema).
2. Rename the output to match `{scenario}_{expected_kind}.json`.
3. Make sure `expected` matches the observed decision; the parametrised
   test picks up any new file automatically.
4. Update the catalog table above so reviewers can find the new case.
