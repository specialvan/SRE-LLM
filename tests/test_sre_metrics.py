"""Tests for production-shaped metric-source adapters."""

from __future__ import annotations

import json
import urllib.parse

import pytest

from attention_residuals.sre_metrics import (
    MetricPoint,
    OpenTelemetryJSONMetricReader,
    PrometheusContextReader,
    PrometheusHTTPClient,
    PrometheusQuery,
    quantile_from_histogram,
    reduce_points,
)


def test_reduce_points_builtin_reducers():
    pts = [MetricPoint("x", 1.0), MetricPoint("x", 3.0), MetricPoint("x", 2.0)]
    assert reduce_points(pts, "first") == 1.0
    assert reduce_points(pts, "sum") == 6.0
    assert reduce_points(pts, "max") == 3.0
    assert reduce_points(pts, "min") == 1.0
    assert reduce_points(pts, "avg") == 2.0
    assert reduce_points(pts, lambda xs: xs[-1].value) == 2.0
    with pytest.raises(ValueError):
        reduce_points([], "first")
    with pytest.raises(ValueError):
        reduce_points(pts, "median")


def test_prometheus_client_parses_vector_response_and_encodes_query():
    seen = {}

    def transport(url: str, timeout: float) -> str:
        seen["url"] = url
        seen["timeout"] = timeout
        return json.dumps({
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": [
                    {
                        "metric": {"__name__": "http_requests", "job": "api"},
                        "value": [1710000000.0, "3.5"],
                    }
                ],
            },
        })

    client = PrometheusHTTPClient("http://prometheus:9090/", timeout=2.5, transport=transport)
    points = client.instant_query('sum(rate(http_requests_total{job="api"}[5m]))', ts=123.0)
    assert len(points) == 1
    assert points[0].name == "http_requests"
    assert points[0].value == 3.5
    assert points[0].labels["job"] == "api"
    assert seen["timeout"] == 2.5
    parsed = urllib.parse.urlparse(seen["url"])
    assert parsed.path == "/api/v1/query"
    qs = urllib.parse.parse_qs(parsed.query)
    assert qs["time"] == ["123.0"]


def test_prometheus_client_parses_scalar_response():
    client = PrometheusHTTPClient(
        "http://prom",
        transport=lambda *_: json.dumps({
            "status": "success",
            "data": {"resultType": "scalar", "result": [10.0, "7"]},
        }),
    )
    point = client.instant_query("vector(7)")[0]
    assert point.name == "vector(7)"
    assert point.value == 7.0
    assert point.timestamp == 10.0


def test_prometheus_context_reader_reduces_multiple_series():
    def transport(url: str, timeout: float) -> str:
        del url, timeout
        return json.dumps({
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": [
                    {"metric": {"instance": "a"}, "value": [1, "2"]},
                    {"metric": {"instance": "b"}, "value": [1, "5"]},
                ],
            },
        })

    reader = PrometheusContextReader(
        PrometheusHTTPClient("http://prom", transport=transport),
        [PrometheusQuery("rps", "sum(rate(...))", reducer="sum")],
    )
    assert reader.read_context()["rps"] == 7.0


def test_prometheus_client_rejects_failed_or_unsupported_payloads():
    client = PrometheusHTTPClient(
        "http://prom",
        transport=lambda *_: json.dumps({"status": "error", "error": "boom"}),
    )
    with pytest.raises(ValueError):
        client.instant_query("up")
    client = PrometheusHTTPClient(
        "http://prom",
        transport=lambda *_: json.dumps({
            "status": "success",
            "data": {"resultType": "matrix", "result": []},
        }),
    )
    with pytest.raises(ValueError):
        client.instant_query("up[5m]")


def test_otel_json_reader_extracts_gauge_and_sum_metrics():
    payload = {
        "resourceMetrics": [
            {
                "scopeMetrics": [
                    {
                        "metrics": [
                            {
                                "name": "queue.depth",
                                "gauge": {
                                    "dataPoints": [
                                        {
                                            "asDouble": 3.0,
                                            "timeUnixNano": "1000000000",
                                            "attributes": [
                                                {"key": "route", "value": {"stringValue": "a"}}
                                            ],
                                        },
                                        {"asDouble": 4.0},
                                    ]
                                },
                            },
                            {
                                "name": "error.count",
                                "sum": {"dataPoints": [{"asInt": "2"}]},
                            },
                        ]
                    }
                ]
            }
        ]
    }
    ctx = OpenTelemetryJSONMetricReader(reducer="sum").read_context(payload)
    assert ctx["queue.depth"] == 7.0
    assert ctx["error.count"] == 2.0


def test_otel_json_reader_accepts_json_string_and_avg_reducer():
    payload = {
        "resourceMetrics": [
            {"scopeMetrics": [{"metrics": [
                {"name": "latency", "gauge": {"dataPoints": [{"value": 10}, {"value": 20}]}}
            ]}]}
        ]
    }
    ctx = OpenTelemetryJSONMetricReader(reducer="avg").read_context(json.dumps(payload))
    assert ctx["latency"] == 15.0


# ---------------------------------------------------------------------------
# Round 11 · OTLP histogram expansion (closes open_gap:otel_no_histogram_expansion)
# ---------------------------------------------------------------------------


def _hist_metric(name, bucket_counts, explicit_bounds, *, count=None, total_sum=None):
    """Build one OTLP histogram metric dict for tests."""
    point = {
        "bucketCounts": list(bucket_counts),
        "explicitBounds": list(explicit_bounds),
    }
    if count is not None:
        point["count"] = count
    if total_sum is not None:
        point["sum"] = total_sum
    return {
        "name": name,
        "histogram": {"dataPoints": [point]},
    }


def _otlp_payload(*metrics):
    return {"resourceMetrics": [{"scopeMetrics": [{"metrics": list(metrics)}]}]}


def test_quantile_from_histogram_linear_interpolation():
    # 10 samples, each bucket holds 5: [0, 0.1] and (0.1, 0.2].
    # p50 -> end of first bucket.
    q50 = quantile_from_histogram([5, 5, 0], [0.1, 0.2], 0.5)
    assert q50 == pytest.approx(0.1)
    # p90 -> deep into second bucket: 4 of 5 samples needed, 80% across
    # (0.1, 0.2] -> 0.1 + 0.8 * 0.1 = 0.18.
    q90 = quantile_from_histogram([5, 5, 0], [0.1, 0.2], 0.9)
    assert q90 == pytest.approx(0.18)


def test_quantile_from_histogram_overflow_clamped_to_last_finite_bound():
    # p99 would fall in the +Inf overflow bucket; we refuse to extrapolate
    # and return the last finite bound instead.
    q99 = quantile_from_histogram([1, 1, 10], [0.1, 0.2], 0.99)
    assert q99 == pytest.approx(0.2)


def test_quantile_from_histogram_validates_inputs():
    with pytest.raises(ValueError, match="q must be in"):
        quantile_from_histogram([1, 1], [0.1], 0.0)
    with pytest.raises(ValueError, match="q must be in"):
        quantile_from_histogram([1, 1], [0.1], 1.0)
    with pytest.raises(ValueError, match="bucket_counts must be non-empty"):
        quantile_from_histogram([], [], 0.5)
    with pytest.raises(ValueError, match="must equal len"):
        quantile_from_histogram([1, 1], [0.1, 0.2], 0.5)
    with pytest.raises(ValueError, match="strictly increasing"):
        quantile_from_histogram([1, 1, 1], [0.2, 0.1], 0.5)
    with pytest.raises(ValueError, match="zero samples"):
        quantile_from_histogram([0, 0, 0], [0.1, 0.2], 0.5)


def test_otel_reader_ignores_histograms_by_default():
    # Default reader (no histogram kwargs) must not fabricate extra keys.
    payload = _otlp_payload(
        _hist_metric("http.req.duration", [2, 3, 1], [0.1, 0.2], count=6, total_sum=0.42),
        {"name": "queue.depth", "gauge": {"dataPoints": [{"value": 7}]}},
    )
    ctx = OpenTelemetryJSONMetricReader().read_context(payload)
    assert ctx == {"queue.depth": 7.0}


def test_otel_reader_expands_histogram_to_quantiles_and_extras():
    payload = _otlp_payload(
        _hist_metric(
            "http.req.duration",
            bucket_counts=[5, 4, 1, 0],
            explicit_bounds=[0.1, 0.2, 0.5],
            count=10,
            total_sum=1.2,
        ),
    )
    reader = OpenTelemetryJSONMetricReader(
        histogram_quantiles=(0.5, 0.95),
        histogram_extras=("avg", "count", "sum"),
    )
    ctx = reader.read_context(payload)
    assert set(ctx) == {
        "http.req.duration__p50",
        "http.req.duration__p95",
        "http.req.duration__avg",
        "http.req.duration__count",
        "http.req.duration__sum",
    }
    # p50 sits in the first bucket at exactly the upper bound.
    assert ctx["http.req.duration__p50"] == pytest.approx(0.1)
    # p95 target = 9.5 samples. Cumulative reaches 9 after bucket 1, 10 after
    # bucket 2 ([0.2, 0.5]). Interpolate: 0.2 + 0.5 * 0.3 = 0.35. We do NOT
    # clamp to a last finite bound because bucket 2 is a finite bucket.
    assert ctx["http.req.duration__p95"] == pytest.approx(0.35)
    assert ctx["http.req.duration__count"] == 10.0
    assert ctx["http.req.duration__sum"] == pytest.approx(1.2)
    assert ctx["http.req.duration__avg"] == pytest.approx(0.12)


def test_otel_reader_histogram_merges_matching_datapoints():
    # Two datapoints with identical explicit_bounds are additive.
    payload = {
        "resourceMetrics": [{"scopeMetrics": [{"metrics": [
            {"name": "lat", "histogram": {"dataPoints": [
                {"bucketCounts": [1, 1, 0], "explicitBounds": [0.1, 0.2], "count": 2, "sum": 0.15},
                {"bucketCounts": [1, 2, 0], "explicitBounds": [0.1, 0.2], "count": 3, "sum": 0.35},
            ]}},
        ]}]}]
    }
    reader = OpenTelemetryJSONMetricReader(
        histogram_quantiles=(0.5,),
        histogram_extras=("avg", "count"),
    )
    ctx = reader.read_context(payload)
    # Merged bucket counts: [2, 3, 0]. p50 target = 2.5 samples. Cumulative
    # reaches 2 after bucket 0, so target lands in bucket 1 ([0.1, 0.2]).
    # Linear interp: 0.1 + (0.5/3) * 0.1 ≈ 0.11667.
    assert ctx["lat__p50"] == pytest.approx(0.1 + 0.1 / 6)
    assert ctx["lat__count"] == 5.0
    assert ctx["lat__avg"] == pytest.approx(0.10)


def test_otel_reader_histogram_rejects_mismatched_bounds():
    payload = {
        "resourceMetrics": [{"scopeMetrics": [{"metrics": [
            {"name": "lat", "histogram": {"dataPoints": [
                {"bucketCounts": [1, 0], "explicitBounds": [0.1]},
                {"bucketCounts": [1, 0], "explicitBounds": [0.2]},
            ]}},
        ]}]}]
    }
    reader = OpenTelemetryJSONMetricReader(histogram_quantiles=(0.5,))
    with pytest.raises(ValueError, match="cannot merge"):
        reader.read_context(payload)


def test_otel_reader_rejects_invalid_quantiles_and_extras():
    with pytest.raises(ValueError, match="histogram_quantiles"):
        OpenTelemetryJSONMetricReader(histogram_quantiles=(0.0,))
    with pytest.raises(ValueError, match="histogram_quantiles"):
        OpenTelemetryJSONMetricReader(histogram_quantiles=(1.0,))
    with pytest.raises(ValueError, match="histogram_extras"):
        OpenTelemetryJSONMetricReader(histogram_extras=("p50",))


def test_otel_reader_histogram_keeps_gauges_and_sums_flowing():
    # Mixed payload: histogram expansion must not drop non-histogram metrics.
    payload = _otlp_payload(
        _hist_metric("lat", [1, 1, 0], [0.1, 0.2], count=2, total_sum=0.2),
        {"name": "queue.depth", "gauge": {"dataPoints": [{"value": 7}]}},
        {"name": "err.count", "sum": {"dataPoints": [{"value": 2}]}},
    )
    reader = OpenTelemetryJSONMetricReader(histogram_quantiles=(0.5,))
    ctx = reader.read_context(payload)
    assert ctx["queue.depth"] == 7.0
    assert ctx["err.count"] == 2.0
    assert "lat__p50" in ctx
