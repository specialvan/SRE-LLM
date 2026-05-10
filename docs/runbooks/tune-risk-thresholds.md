# Runbook · Tune risk thresholds

**When to use**: Rate of `ROLLBACK` or `HOLD` decisions is trending up
and you believe the pipeline is too conservative (false positives).

## Don't do this blindly

Before changing any threshold, confirm:

1. The elevated rate isn't a genuine reliability regression — pull
   raw SLO burn charts for the same window.
2. The affected services have `total_releases >= 20`. Below that the
   `sigma` is still wide and the pessimistic bootstrap (see
   [ADR-0005](../adr/0005-fallback-strategy-for-untrained-models.md))
   is doing its job.

## Change procedure

1. Open `config.json` (or the equivalent ConfigMap in your cluster) and
   adjust under `survival`:
   ```json
   "survival": { "warn_threshold": 0.35, "alarm_threshold": 0.65 }
   ```
   Never widen both by more than 0.05 in one change.

2. Add a line to the `changelog.md` referencing the ticket.

3. Ship the config change as a **canary** config — apply to one
   non-critical service first, observe 24h, then expand.

4. If you need to retrain the Cox model, use the collected
   `(feature_vector, event, duration)` tuples from
   `/var/log/gan/training.jsonl`:
   ```python
   from gan_matchmaking.survival import CoxModel
   model = CoxModel().fit(X, durations, events)
   ```

## Reviewing the change

- The regression test
  `test_loss_streak_and_alarm_triggers_rollback` should still pass.
- Add a new test if your change targets a specific feature weight.
