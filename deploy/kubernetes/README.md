# Kubernetes manifests

Single-node deployment of the SRE decision service. Suitable for 1
replica scenarios; for >1 replica swap the SQLite store for PostgreSQL
(see [`ADR-0006`](../../docs/adr/0006-horizontal-scaling.md) — TODO).

## Apply

```bash
kubectl apply -f configmap.yaml
kubectl apply -f deployment.yaml
kubectl apply -f cronjob-training.yaml
```

## Smoke-test from inside the cluster

```bash
kubectl port-forward svc/gan-matchmaking 8080:80 &
curl -s http://localhost:8080/healthz
curl -s http://localhost:8080/metrics | head -n 20
curl -s -X POST http://localhost:8080/v1/decide \
  -H 'Content-Type: application/json' \
  -d @/path/to/sample_context.json
```

## Key operational levers

| Surface | Where to change |
| --- | --- |
| Config (thresholds, seed, log level) | `configmap.yaml` → rolling restart |
| CPU / memory | `deployment.yaml#resources` |
| Training cadence | `cronjob-training.yaml#schedule` |
| State retention | `PersistentVolumeClaim#storage` |
| Image | `deployment.yaml#image`; built from root `Dockerfile` |

## Observability hooks

- Prometheus: scrape `:/metrics` — annotations already in place.
- Logs: JSONL on stderr. Ship with fluent-bit / loki without special
  parsers.
- Traces: every response carries `X-Correlation-Id`. Join with logs on
  that key.
