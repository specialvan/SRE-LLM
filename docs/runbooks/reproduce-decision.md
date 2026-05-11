# Runbook · Reproduce a decision byte-for-byte

**When to use**: Post-incident review. You have a `Decision.trace` and
need to confirm the pipeline would return the same decision given the
same inputs.

## Preconditions

- Git SHA of the pipeline at decision time (from the deploy manifest).
- The `trace` dict (or its JSONL export).
- The config JSON used at decision time.
- The runtime artifact directory, if `trace.artifacts.version` is not
  `bootstrap`.

## Steps

1. Check out the pipeline at that commit:
   ```
   git checkout <sha>
   pip install -e .
   ```

2. Export a deterministic environment:
   ```
   set PYTHONHASHSEED=0
   set GAN_SEED=<config.seed>
   ```

3. Reconstruct the `ReleaseContext`.
   - Newer decisions store the exact replay input under
     `trace.input.context`.
   - Older decisions may require manual reconstruction from
     `trace.stages.*`, the request log, and the input feature vectors.

4. Call the pipeline with the exact same config:
   ```python
   from gan_matchmaking.core import load_config
   from gan_matchmaking.sre import SelfIterationPipeline
   cfg = load_config("path/to/config.json")
   pipeline = SelfIterationPipeline(config=cfg)
   decision = pipeline.decide(reconstructed_ctx)
   ```

5. Compare `decision.kind`, `decision.risk_level`, `decision.chosen.id`
   against the archived `Decision`. They must match bit-for-bit.

## Golden Corpus

The repository ships a regression corpus under
`tests/fixtures/replay/*.json`. Each fixture contains:

- `config`: minimal `AppConfig` input.
- `artifacts`: optional fitted retention / Cox artifact specs.
- `context`: the `ReleaseContext` payload.
- `expected`: stable decision fields and selected trace assertions.
- `expected.rationale_contains`: optional substrings that must appear in
  the emitted rationale.
- `expected.trace_values`: optional dotted trace paths and exact values.
- `scenario`: optional incident narrative metadata explaining why the
  fixture exists.

Run the corpus with:

```
python -m pytest -q tests/test_replay_corpus.py
```

Add a fixture whenever a post-incident replay exposes a new branch,
fallback, or policy boundary. Prefer incident-style fixtures that assert
the guardrail reason in `rationale_contains` and at least one trace value,
not only the final decision kind.

## Export From SQLite Audit

For decisions produced by the current pipeline, the SQLite audit row already
contains `trace.input.context` and the embedded config snapshot. Export it
directly into the replay fixture format:

```
python -m gan_matchmaking.cli export-replay ^
  --state-db state.sqlite ^
  --correlation-id <decision-correlation-id> ^
  --output tests/fixtures/replay/<incident-name>.json ^
  --name <incident-name>
```

The exporter is intentionally conservative:

- Bootstrap decisions become standalone fixtures.
- Fitted-artifact decisions require `--allow-fitted-artifacts` **and** a
  matching `--artifact-dir`, because the decision audit table records
  artifact identity but not model weights.
- If `trace.input.context` is missing, the row came from an older runtime
  and must be reconstructed manually before it can be promoted to golden
  corpus.

## Promote a fitted-artifact replay

A fitted decision may enter the golden corpus only when code, config,
fixture, and artifact bundle are archived together.

```
python -m gan_matchmaking.cli export-replay ^
  --state-db state.sqlite ^
  --correlation-id <decision-correlation-id> ^
  --allow-fitted-artifacts ^
  --artifact-dir /path/to/runtime/artifacts ^
  --artifact-output-dir tests/fixtures/replay/<incident-name>-artifacts ^
  --output tests/fixtures/replay/<incident-name>.json ^
  --name <incident-name>
```

Promotion rules:

- The artifact bundle version must exactly match the archived decision's
  `artifact_version`.
- Runtime artifact manifest validation must pass before export.
- The exporter writes `replay_artifact_manifest.json` beside the copied
  artifact files.
- The fixture records `requires_artifact_version` and `artifact_bundle`,
  so replay tests can load the archived bundle rather than the operator's
  current runtime directory.
- If artifact validation fails, add an incident fixture for the fallback
  decision instead of forcing the bad artifact into the corpus.

## If they don't match

- Double-check the config SHA and the commit SHA — even a whitespace
  config diff re-seeds the SeedManager.
- Check `trace.artifacts.version` first. A decision may differ because the
  runtime loaded a different retention / Cox artifact even when the code
  and config are unchanged.
- If `trace.artifacts.validation_errors` is non-empty, the runtime skipped
  at least one artifact because its manifest did not match the expected
  feature contract, shape, or Cox baseline arrays. Re-run with the exact
  artifact directory or rebuild the artifact from the matching trainer.
- Look for *shared-registry* test pollution: if two pipelines run in the
  same process and share `default_registry`, metrics snapshot may differ
  but the `Decision` should still match.
- File a bug with both traces attached.
