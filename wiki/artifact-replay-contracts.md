# Artifact Replay Contracts

This page summarizes the runtime/replay artifact compatibility contract. The source-of-truth implementation lives in `gan_matchmaking/sre/artifacts/`, `gan_matchmaking/sre/self_iteration.py`, and `gan_matchmaking/sre/replay.py`.

## Core invariant

A fitted replay bundle must not validate successfully if runtime hydration would downgrade or ignore its retention artifact.

Runtime and replay therefore share the same compatibility classifier:

```text
retention_scaling_compatibility(retention)
  -> status: match | mismatch | unknown | absent
  -> expected_version
  -> actual_version
  -> artifact_version
```

## Status semantics

| Status | Runtime hydration | Replay validation |
|---|---|---|
| `match` | Hydrate retention weights. | Accept. |
| `mismatch` | Log `artifacts.retention.scaling_mismatch`, mark trace `mismatch`, drop retention and fall back. | Reject with `DataError`. |
| `unknown` | Legacy runtime behavior: hydrate retention and mark trace `unknown`. | Reject by default; accept only with explicit `allow_legacy_unknown=True`. |
| `absent` | Mark trace `absent`; do not report a false `match`. | Scaling check passes; existing fitted/empty-bundle rules decide validity. |

## Trace fields

Relevant trace paths:

```text
trace.artifacts.version
trace.artifacts.fitted
trace.artifacts.retention
trace.artifacts.validation_errors
trace.artifacts.rating_scaling_status
trace.stages.eomm.source
```

Modern fitted replay fixtures must assert:

```json
{
  "expected": {
    "trace_values": {
      "artifacts.rating_scaling_status": "match"
    }
  }
}
```

## Replay export safety

Replay export validates artifact bundles before archiving them.

Rejected by default:

- retention `rating_scaling_version` mismatch
- retention `rating_scaling_version` missing (`unknown`) unless explicitly allowed
- artifact filename config containing traversal or absolute paths
- empty/non-fitted artifact bundle when fitted artifacts are required
- artifact validation errors from retention/Cox manifest or shape checks

Artifact filename config is basename-only. The validation rejects both POSIX and Windows path forms:

```text
../retention_weights.npz
..\\retention_weights.npz
/tmp/retention_weights.npz
C:\\tmp\\retention_weights.npz
\\\\server\\share\\retention_weights.npz
```

## CLI knobs

```bash
python -m gan_matchmaking.cli export-replay \
  --state-db state.sqlite \
  --correlation-id <id> \
  --allow-fitted-artifacts \
  --artifact-dir runtime-artifacts \
  --artifact-output-dir tests/fixtures/replay/artifact-bundles/<id>
```

Legacy fitted artifacts without rating-scaling metadata require an explicit opt-in:

```bash
python -m gan_matchmaking.cli export-replay ... --allow-legacy-unknown
```

## Tests

Primary tests:

- `tests/test_rating_scaling.py`
- `tests/test_replay_export.py`
- `tests/test_replay_corpus.py`
- `tests/test_core_config.py`
- `tests/test_artifacts_public_api.py`

Focused command:

```bash
python -m pytest tests/test_rating_scaling.py tests/test_replay_export.py tests/test_replay_corpus.py tests/test_core_config.py tests/test_artifacts_public_api.py -q
```
