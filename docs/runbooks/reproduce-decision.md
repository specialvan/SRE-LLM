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

3. Reconstruct the `ReleaseContext` from the trace (`trace.stages.*` plus
   the input feature vectors).

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

Run the corpus with:

```
python -m pytest -q tests/test_replay_corpus.py
```

Add a fixture whenever a post-incident replay exposes a new branch,
fallback, or policy boundary.

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
