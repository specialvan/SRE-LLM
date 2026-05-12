# Metric Sources (Round 9)

Round 9 adds a small, dependency-free adapter layer that turns
production-shaped metrics into audit contexts.

The goal is not to replace Prometheus or OpenTelemetry clients. The goal
is to define the narrow contract needed by this project:

```text
metric source -> context dict -> AuditTrail -> TemporalCreditAssigner
```

## Prometheus

```python
from attention_residuals.sre_metrics import (
    PrometheusHTTPClient,
    PrometheusContextReader,
    PrometheusQuery,
)

reader = PrometheusContextReader(
    PrometheusHTTPClient("http://prometheus:9090"),
    [
        PrometheusQuery("latency_ms", "histogram_quantile(...)", reducer="first"),
        PrometheusQuery("error_rate", "sum(rate(errors_total[5m]))", reducer="sum"),
    ],
)

context = reader.read_context()
```

Supported Prometheus result types:

- `scalar`
- `vector`

Reducers:

- `first`
- `sum`
- `max`
- `min`
- `avg`
- custom callable

Tests inject a fake `transport(url, timeout) -> text`, so no network is
needed for verification.

## OpenTelemetry

```python
from attention_residuals.sre_metrics import OpenTelemetryJSONMetricReader

reader = OpenTelemetryJSONMetricReader(reducer="sum")
context = reader.read_context(otlp_json_payload)
```

Supported OTLP JSON metric shapes:

- `resourceMetrics[].scopeMetrics[].metrics[].gauge.dataPoints[]`
- `resourceMetrics[].scopeMetrics[].metrics[].sum.dataPoints[]`
- `resourceMetrics[].scopeMetrics[].metrics[].histogram.dataPoints[]`
  *(opt-in via `histogram_quantiles=` / `histogram_extras=`; see below)*

Supported value fields:

- `asDouble`
- `doubleValue`
- `asInt`
- `intValue`
- `value`

### Histogram expansion (Round 11)

Histograms are ignored by default so existing callers are unchanged. Opt in
by passing `histogram_quantiles=(...)` to extract quantiles from bucket
counts, and/or `histogram_extras=(...)` with any subset of
`("avg", "count", "sum")`:

```python
reader = OpenTelemetryJSONMetricReader(
    histogram_quantiles=(0.5, 0.95, 0.99),
    histogram_extras=("count", "sum"),
)
context = reader.read_context(otlp_json_payload)
# => context["http.req.duration__p50"], ..__p95, ..__p99, ..__count, ..__sum
```

The derived keys follow the convention `<metric>__pXX` / `<metric>__{avg,count,sum}`.
The double underscore keeps the key grep-able and avoids colliding with OTel
attribute-encoded colons.

Quantile extraction semantics:

- Bucket counts are merged **element-wise** across datapoints that share the
  same `explicitBounds`. Mismatched bounds raise `ValueError` — we refuse to
  silently merge incompatible histograms.
- Linear interpolation within the target bucket, clamped to the previous
  bound from below (`0.0` if the target is the first finite bucket).
- If the target falls in the `+Inf` overflow bucket, the returned value is
  the last finite bound. We refuse to extrapolate beyond what was observed.
- For zero-count histograms the function raises `ValueError`. Quantiles of
  empty distributions are undefined; callers should skip the metric.

The underlying helper `quantile_from_histogram(bucket_counts, explicit_bounds, q)`
is exported from the same module for callers that want to compute quantiles
directly from pre-extracted bucket arrays (e.g. for Prometheus `histogram`
sample exposition).

## Demo

```bash
python -m examples.demo_metric_source_replay
```

The demo uses fake Prometheus transport and an OTLP JSON payload, writes
an `AuditTrail`, then replays it through `AuditCreditReplay`.

## Full Loop

```text
Prometheus / OTLP
        |
        v
context metrics
        |
        v
WeightedConvexCombiner + AuditTrail
        |
        v
AuditCreditReplay + MetricLossMapper
        |
        v
TemporalCreditAssigner
        |
        v
CreditAwareLabeler + LearnedSafetyEnvelope
```
