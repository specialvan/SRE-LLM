# Kubernetes manifests

Single-node deployment of the SRE decision service. Suitable for 1
replica scenarios; for >1 replica move the writer lock to a distributed
lease and swap SQLite for an external store (see
[`ADR-0007`](../../docs/adr/0007-single-writer-lease-boundary.md)).

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
| Process lease | `GAN_LEASE_FILE` / `GAN_LEASE_TTL_SECONDS` |
| Image | `deployment.yaml#image`; built from root `Dockerfile` |

## Observability hooks

- Prometheus: scrape `:/metrics` — annotations already in place.
- Logs: JSONL on stderr. Ship with fluent-bit / loki without special
  parsers.
- Traces: every response carries `X-Correlation-Id`. Join with logs on
  that key.

## Lease boundary

The manifest sets `replicas: 1`, `strategy: Recreate`, and a local
`GAN_LEASE_FILE` under the mounted state directory. This protects the
SQLite writer from accidental duplicate service processes during restarts
or manual launches.

Do not scale this deployment past one writable replica by only changing
`replicas`. For horizontal scale, replace the local file lease with an
external lease primitive and move state out of the single SQLite file.
