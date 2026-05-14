# Replay Corpus

The replay corpus is the incident-regression suite for SRE decisions. Fixtures live in `tests/fixtures/replay/*.json` and are exercised by `tests/test_replay_corpus.py`.

## Naming convention

```text
{scenario}_{expected_kind}.json
```

`expected_kind` must be one of:

```text
go | canary | hold | rollback | escalate
```

The convention is enforced by `test_fixture_naming_matches_convention`.

## Fixture schema essentials

```json
{
  "name": "artifact_canary",
  "config": { "seed": 0 },
  "artifacts": { "retention": {}, "cox": {} },
  "artifact_bundle": { "path": "..." },
  "circuit_breaker": "open",
  "context": { "service": {}, "candidates": [] },
  "expected": {
    "kind": "canary",
    "chosen_id": "...",
    "risk_level": "ok",
    "artifact_version": "bootstrap",
    "eomm_source": "artifact",
    "rationale_contains": [],
    "trace_values": {}
  }
}
```

Only include fields needed by the scenario.

## Current incident narratives

| Fixture | Narrative | Key assertion |
|---|---|---|
| `artifact_canary.json` | Modern fitted artifacts steer the decision. | `artifacts.rating_scaling_status == "match"` |
| `artifact_scaling_mismatch_go.json` | Stale retention scaling downgrades to bootstrap/fallback. | `artifacts.rating_scaling_status == "mismatch"` |
| `breaker_open_escalate.json` | Open circuit breaker bypasses scoring. | `circuit_breaker.state == "open"`, kind `escalate` |
| `shadow_strategy_hold.json` | Shadow traffic strategy is not production traffic. | strategy `shadow`, kind `hold` |
| `risk_warn_canary.json` | Risk WARN downgrades full rollout to canary. | `stages.risk.level == "warn"` |
| `budget_rollback.json` | Exhausted budget forces rollback posture. | kind `rollback` |
| `freeze_hold.json` | Freeze window pins HOLD. | kind `hold` |
| `unknown_strategy_escalate.json` | Unknown strategy escalates to human. | kind `escalate` |

See `tests/fixtures/replay/README.md` for the full catalog.

## How to add a fixture

1. Reproduce or construct the decision context.
2. Add a JSON fixture under `tests/fixtures/replay/`.
3. Ensure filename ends with the expected decision kind.
4. Add precise `expected.trace_values` for the contract being protected.
5. Run:

```bash
python -m pytest tests/test_replay_corpus.py -q
```

## Future fixture backlog

- Artifact metadata-shape failure with `artifacts.validation_errors`.
- Advisory-mode rollout fixture with `trace.shadow_mode == "advisory"`.
- Additional lease/readiness HTTP-drain fixtures if the deployment harness grows.
