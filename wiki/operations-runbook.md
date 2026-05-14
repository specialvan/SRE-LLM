# Operations Runbook

This page collects operator-facing checks for local validation, replay, artifacts, and readiness.

## Fast local validation

```bash
python -m pytest tests/test_rating_scaling.py tests/test_replay_corpus.py tests/test_replay_export.py tests/test_core_config.py tests/test_http_service.py tests/test_artifacts_public_api.py -q
python -m bench.latency --quick --p99-ms 50
```

Full gate:

```bash
python -m pytest -q
python -m bench.latency --quick --p99-ms 50
```

## Replay workflow

Bootstrap decision export:

```bash
python -m gan_matchmaking.cli export-replay \
  --state-db state.sqlite \
  --correlation-id <correlation-id> \
  --output tests/fixtures/replay/<scenario>_<kind>.json
```

Fitted artifact decision export:

```bash
python -m gan_matchmaking.cli export-replay \
  --state-db state.sqlite \
  --correlation-id <correlation-id> \
  --output tests/fixtures/replay/<scenario>_<kind>.json \
  --allow-fitted-artifacts \
  --artifact-dir runtime-artifacts \
  --artifact-output-dir tests/fixtures/replay/artifact-bundles/<correlation-id>
```

Legacy fitted artifacts with unknown retention scaling metadata require explicit opt-in:

```bash
python -m gan_matchmaking.cli export-replay ... --allow-legacy-unknown
```

After adding a fixture:

```bash
python -m pytest tests/test_replay_corpus.py -q
```

## Artifact validation symptoms

| Symptom | Meaning | Action |
|---|---|---|
| `trace.artifacts.rating_scaling_status == "match"` | Retention artifact matches current scaling contract. | Accept normal fitted replay/runtime behavior. |
| `mismatch` | Runtime downgraded stale retention scaling. | Treat fitted replay bundle as invalid; retrain or use matching artifact. |
| `unknown` | Legacy artifact missing scaling metadata. | Runtime may hydrate; replay requires explicit legacy opt-in. |
| `absent` | No retention artifact present. | Bootstrap/partial hydrate behavior; verify expected scenario. |
| `trace.artifacts.validation_errors` present | Manifest/shape/semantic validation failed. | Inspect artifact metadata and feature contracts before promotion. |

## Runtime dashboard

Start the stdlib service and open the dashboard:

```bash
python -m gan_matchmaking.service --host 127.0.0.1 --port 8080 --state-db state.sqlite
```

Browser/API checks:

```text
http://127.0.0.1:8080/dashboard
http://127.0.0.1:8080/v1/dashboard/state
```

The dashboard is no-build static HTML/CSS/JS served by the Python service. Static assets are allowlisted under `/dashboard/assets/`; arbitrary paths must return 404.

## Readiness and lease checks

Expected healthy serving state:

```text
/healthz -> 200 status=ok
/readyz  -> 200 status=ready
```

Expected lease refresh failure state:

```text
/healthz -> 200 status=ok
/readyz  -> 503 status=not_ready reason=lease_unhealthy
```

Operational interpretation:

1. `/healthz` answers whether the process is alive.
2. `/readyz` answers whether the process should receive serving traffic.
3. Lease loss is drained through orchestrator readiness, not direct handler blocking.
4. `FileLease` only supports local-filesystem/single-writer assumptions.

## Latency budget

Current quick benchmark budget:

```bash
python -m bench.latency --quick --p99-ms 50
```

The command must exit non-zero when observed p99 exceeds the provided budget. CI should treat this as a release gate.

## Before merge

Use [`review-merge-checklist.md`](review-merge-checklist.md). Minimum evidence:

```text
focused tests: passed
full pytest: passed
latency quick gate: passed
no blocking code/security review findings
```
