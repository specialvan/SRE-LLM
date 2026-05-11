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
