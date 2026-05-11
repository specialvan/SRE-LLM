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

Supported value fields:

- `asDouble`
- `doubleValue`
- `asInt`
- `intValue`
- `value`

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
