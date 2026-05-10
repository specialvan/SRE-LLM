# Runbook · Bootstrap a new service in the pipeline

**When to use**: Onboarding a new service. Before any real decisions are
trusted, the pipeline needs a handful of observations so its Gaussian
posterior is tighter than the prior.

## Minimum viable state

A service is "bootstrapped" when:

- `total_releases >= 10` recorded via `pipeline.observe_release`.
- `sigma <= 0.05` (i.e. reliability uncertainty is sub-5%).
- At least one dependency edge exists in `synergy_graph`.

Until those are true the pipeline will:

- Default to `CANARY` even on clean traffic, by policy.
- Keep `fallback_used=true` in `trace.stages.entropy`.

## Steps

1. Register the service with its tier:
   ```python
   pipeline.register_service(Service(id="svc-x", tier="standard"))
   ```

2. Replay 10–30 recent releases into the pipeline (order matters — the
   Kalman update is sequential):
   ```python
   for r in recent_releases:
       pipeline.observe_release(r.service_id, success=r.success)
   ```

3. Add dependency edges by calling
   `pipeline.synergy_graph.add_match([svc] + deps, win=True)` for each
   successful joint release, or `win=False` for failures.

4. Confirm with:
   ```python
   pipeline.decide(ctx).trace["stages"]
   ```
   Each stage should have non-degraded fields.

## If bootstrap data is missing

Run a synthetic dry-run on `examples/sre_demo.py` first; ship the
resulting trace to a reviewer. The reviewer should see deterministic
decisions with the default seed.
