"""Metric source -> audit context -> credit replay demo.

This demo keeps the transport local and deterministic, but uses the same
Prometheus/OpenTelemetry adapters that a production job would use.

Run with::

    python -m examples.demo_metric_source_replay
"""

from __future__ import annotations

import json

import numpy as np

from attention_residuals.sre_control import AuditTrail, SignalSpec, WeightedConvexCombiner
from attention_residuals.sre_math import (
    AuditCreditReplay,
    MetricLossMapper,
    MetricLossSpec,
    TemporalCreditAssigner,
)
from attention_residuals.sre_metrics import (
    OpenTelemetryJSONMetricReader,
    PrometheusContextReader,
    PrometheusHTTPClient,
    PrometheusQuery,
)


def fake_prometheus_transport(url: str, timeout: float) -> str:
    del timeout
    if "latency" in url:
        value = "420" if "time=20.0" in url else "180"
    else:
        value = "8" if "time=20.0" in url else "1"
    return json.dumps({
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [{"metric": {}, "value": [20.0, value]}],
        },
    })


def otel_payload(queue_depth: float, *, include_histogram: bool = False) -> str:
    metrics = [
        {"name": "queue_depth", "gauge": {"dataPoints": [{"asDouble": queue_depth}]}},
    ]
    if include_histogram:
        # Two datapoints from two worker pods; bounds are identical so they
        # merge element-wise before quantile extraction.
        metrics.append({
            "name": "req.duration",
            "histogram": {"dataPoints": [
                {
                    "bucketCounts": [3, 4, 2, 1, 0],
                    "explicitBounds": [0.05, 0.1, 0.25, 0.5],
                    "count": 10, "sum": 1.3,
                },
                {
                    "bucketCounts": [2, 3, 3, 1, 1],
                    "explicitBounds": [0.05, 0.1, 0.25, 0.5],
                    "count": 10, "sum": 2.1,
                },
            ]},
        })
    return json.dumps({"resourceMetrics": [{"scopeMetrics": [{"metrics": metrics}]}]})


def main() -> None:
    prometheus = PrometheusContextReader(
        PrometheusHTTPClient("http://prometheus:9090", transport=fake_prometheus_transport),
        [
            PrometheusQuery("latency_ms", "latency_p99_ms", reducer="first"),
            PrometheusQuery("error_rate", "error_rate", reducer="first"),
        ],
    )
    otel = OpenTelemetryJSONMetricReader(
        histogram_quantiles=(0.5, 0.95),
        histogram_extras=("count", "sum"),
    )

    combiner = WeightedConvexCombiner(
        [SignalSpec("latency"), SignalSpec("errors"), SignalSpec("queue")],
        query_dim=3,
        rng_seed=0,
    )
    combiner.W_K = np.eye(3)
    trail = AuditTrail()

    for tick in range(30):
        prom_context = prometheus.read_context(ts=20.0 if tick >= 20 else 10.0)
        otel_context = otel.read_context(
            otel_payload(70.0 if tick >= 20 else 12.0, include_histogram=tick >= 20)
        )
        context = {**prom_context, **otel_context, "tick": float(tick)}
        query = np.array([
            max(0.0, context["latency_ms"] - 250.0) / 250.0,
            context["error_rate"],
            context["queue_depth"] / 100.0,
        ])
        action, _ = combiner.combine(
            query,
            [np.array([2.0]), np.array([3.0]), np.array([1.0])],
        )
        trail.record(combiner, action, context=context)

    tca = TemporalCreditAssigner(decay=0.9)
    replay = AuditCreditReplay(
        tca,
        MetricLossMapper({
            "latency": MetricLossSpec("latency_ms", target=250.0, mode="above", scale=100.0),
            "errors": MetricLossSpec("error_rate", target=1.0, mode="above", scale=1.0),
            "queue": MetricLossSpec("queue_depth", target=50.0, mode="above", scale=20.0),
        }),
    )
    replay.replay_jsonl(trail.to_jsonl())
    blamed = tca.attribute(incident_tick=29, window=10, top_k=5)

    print("=" * 86)
    print("Metric sources -> audit context -> temporal credit")
    print("=" * 86)
    print(f"Audit records: {len(trail)}")
    # Print the last-tick context so histogram expansion is visible in the
    # demo output (the reader populated req.duration__p50/p95/... keys).
    last_record = next(iter(reversed(list(trail))))
    last_context = last_record.context
    hist_keys = sorted(k for k in last_context if k.startswith("req.duration__"))
    if hist_keys:
        print("Histogram-expanded keys at tick 29:")
        for k in hist_keys:
            print(f"  {k:>24} = {last_context[k]:.4f}")
    print(f"{'rank':>4} {'tick':>4} {'signal':>8} {'weight':>8} {'loss':>8} {'score':>8}")
    for i, entry in enumerate(blamed, start=1):
        print(
            f"{i:>4} {entry.tick:>4} {entry.signal_name:>8} "
            f"{entry.weight:>8.3f} {entry.loss:>8.3f} {entry.score:>8.3f}"
        )


if __name__ == "__main__":
    main()
