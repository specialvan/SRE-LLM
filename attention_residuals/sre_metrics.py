"""Metric-source adapters for the SRE control-plane demos.

The previous rounds gave us audit replay and temporal credit, but the
demo contexts were still synthetic dictionaries. This module is the thin
adapter layer that turns production-shaped metrics into those contexts:

* Prometheus instant-query JSON -> ``{context_key: value}``
* OpenTelemetry OTLP JSON export -> ``{metric_name: value}``

The implementation deliberately uses only the Python standard library so
it can be embedded in control-plane jobs without adding a new runtime
dependency. Tests inject fake HTTP transports; no network is required.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Union


@dataclass(frozen=True)
class MetricPoint:
    """One scalar metric sample."""

    name: str
    value: float
    timestamp: Optional[float] = None
    labels: Dict[str, str] = field(default_factory=dict)


Reducer = Callable[[Sequence[MetricPoint]], float]
Transport = Callable[[str, float], str]


def reduce_points(points: Sequence[MetricPoint], reducer: Union[str, Reducer] = "first") -> float:
    """Reduce one or more samples to a scalar context value."""
    if not points:
        raise ValueError("cannot reduce empty metric points")
    if callable(reducer):
        return float(reducer(points))
    values = [p.value for p in points]
    if reducer == "first":
        return float(values[0])
    if reducer == "sum":
        return float(sum(values))
    if reducer == "max":
        return float(max(values))
    if reducer == "min":
        return float(min(values))
    if reducer == "avg":
        return float(sum(values) / len(values))
    raise ValueError("reducer must be first/sum/max/min/avg or callable")


@dataclass(frozen=True)
class PrometheusQuery:
    """Mapping from one Prometheus query to one context key."""

    context_key: str
    query: str
    reducer: Union[str, Reducer] = "first"


class PrometheusHTTPClient:
    """Small Prometheus HTTP API client for instant queries.

    Parameters
    ----------
    base_url:
        Prometheus base URL, for example ``http://prom:9090``.
    transport:
        Optional injectable ``transport(url, timeout) -> text``. Tests and
        offline demos use this to avoid real network calls.
    """

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 5.0,
        transport: Optional[Transport] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = float(timeout)
        self.transport = transport or self._default_transport

    def instant_query(self, query: str, *, ts: Optional[float] = None) -> List[MetricPoint]:
        params: Dict[str, str] = {"query": query}
        if ts is not None:
            params["time"] = str(float(ts))
        url = f"{self.base_url}/api/v1/query?{urllib.parse.urlencode(params)}"
        payload = json.loads(self.transport(url, self.timeout))
        if payload.get("status") != "success":
            raise ValueError(f"Prometheus query failed: {payload!r}")
        data = payload.get("data", {})
        result_type = data.get("resultType")
        result = data.get("result")
        if result_type == "scalar":
            timestamp, value = result
            return [MetricPoint(name=query, value=float(value), timestamp=float(timestamp))]
        if result_type == "vector":
            points: List[MetricPoint] = []
            for item in result:
                timestamp, value = item["value"]
                labels = {str(k): str(v) for k, v in item.get("metric", {}).items()}
                name = labels.get("__name__", query)
                points.append(
                    MetricPoint(
                        name=name,
                        value=float(value),
                        timestamp=float(timestamp),
                        labels=labels,
                    )
                )
            return points
        raise ValueError(f"unsupported Prometheus resultType: {result_type!r}")

    @staticmethod
    def _default_transport(url: str, timeout: float) -> str:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.read().decode("utf-8")


class PrometheusContextReader:
    """Read a set of Prometheus queries into an audit context dict."""

    def __init__(self, client: PrometheusHTTPClient, queries: Sequence[PrometheusQuery]) -> None:
        if not queries:
            raise ValueError("queries must not be empty")
        self.client = client
        self.queries = list(queries)

    def read_context(self, *, ts: Optional[float] = None) -> Dict[str, float]:
        context: Dict[str, float] = {}
        for spec in self.queries:
            points = self.client.instant_query(spec.query, ts=ts)
            context[spec.context_key] = reduce_points(points, spec.reducer)
        return context


class OpenTelemetryJSONMetricReader:
    """Extract scalar metrics from OTLP JSON exports.

    The reader accepts either an already-decoded mapping or a JSON string.
    It supports ``gauge`` and ``sum`` metrics with numeric datapoints.
    Multiple datapoints with the same metric name are reduced using the
    configured reducer.
    """

    def __init__(self, *, reducer: Union[str, Reducer] = "sum") -> None:
        self.reducer = reducer

    def read_context(self, payload: Union[str, Mapping[str, Any]]) -> Dict[str, float]:
        data = json.loads(payload) if isinstance(payload, str) else payload
        grouped: Dict[str, List[MetricPoint]] = {}
        for metric in self._iter_metrics(data):
            name = str(metric.get("name", ""))
            if not name:
                continue
            for point in self._metric_points(metric):
                grouped.setdefault(name, []).append(point)
        return {name: reduce_points(points, self.reducer) for name, points in grouped.items()}

    def _iter_metrics(self, data: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
        for resource in data.get("resourceMetrics", []):
            for scope in resource.get("scopeMetrics", []):
                for metric in scope.get("metrics", []):
                    yield metric

    def _metric_points(self, metric: Mapping[str, Any]) -> Iterable[MetricPoint]:
        name = str(metric.get("name", ""))
        body = metric.get("gauge") or metric.get("sum") or {}
        for point in body.get("dataPoints", []):
            value = _point_value(point)
            if value is None:
                continue
            labels = _point_attributes(point)
            timestamp = _point_timestamp(point)
            yield MetricPoint(name=name, value=value, timestamp=timestamp, labels=labels)


def _point_value(point: Mapping[str, Any]) -> Optional[float]:
    for key in ("asDouble", "doubleValue", "asInt", "intValue", "value"):
        if key in point:
            return float(point[key])
    return None


def _point_attributes(point: Mapping[str, Any]) -> Dict[str, str]:
    labels: Dict[str, str] = {}
    for attr in point.get("attributes", []):
        key = str(attr.get("key", ""))
        value = attr.get("value", {})
        if not key:
            continue
        if isinstance(value, Mapping):
            raw = next(iter(value.values()), "")
        else:
            raw = value
        labels[key] = str(raw)
    return labels


def _point_timestamp(point: Mapping[str, Any]) -> Optional[float]:
    for key in ("timeUnixNano", "startTimeUnixNano"):
        if key in point:
            return float(point[key]) / 1_000_000_000.0
    return None


__all__ = [
    "MetricPoint",
    "PrometheusQuery",
    "PrometheusHTTPClient",
    "PrometheusContextReader",
    "OpenTelemetryJSONMetricReader",
    "reduce_points",
]
