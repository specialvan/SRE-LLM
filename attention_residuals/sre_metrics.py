"""Metric-source adapters for the SRE control-plane demos.

The previous rounds gave us audit replay and temporal credit, but the
demo contexts were still synthetic dictionaries. This module is the thin
adapter layer that turns production-shaped metrics into those contexts:

* Prometheus instant-query JSON -> ``{context_key: value}``
* OpenTelemetry OTLP JSON export -> ``{metric_name: value}``

The implementation deliberately uses only the Python standard library so
it can be embedded in control-plane jobs without adding a new runtime
dependency. Tests inject fake HTTP transports; no network is required.

Invariant I-12 (see docs/V2_Knowledge/state.json): readers only extract
numbers from payloads. They must never emit control actions or mutate
caller state.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union


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

    Histogram support (opt-in, additive)
    ------------------------------------
    ``histogram`` metrics are ignored by default so existing callers see
    unchanged behaviour. Pass ``histogram_quantiles`` to expand a histogram
    into synthetic scalar context keys named ``<metric>__p50`` / ``p95`` /
    ``p99`` etc. (the double-underscore keeps the derived name grep-able and
    avoids colliding with OTel attribute-encoded colons).

    Pass ``histogram_extras`` with any subset of ``("avg", "count", "sum")``
    to additionally emit ``<metric>__avg``, ``<metric>__count``, ``<metric>__sum``.

    Histogram datapoints are combined **before** quantile extraction: bucket
    counts are summed element-wise across datapoints that share the same
    ``explicitBounds``. Mismatched bounds raise ``ValueError`` — there is no
    safe way to merge histograms with different boundaries and we refuse
    rather than silently produce a wrong quantile.
    """

    _VALID_EXTRAS = ("avg", "count", "sum")

    def __init__(
        self,
        *,
        reducer: Union[str, Reducer] = "sum",
        histogram_quantiles: Sequence[float] = (),
        histogram_extras: Sequence[str] = (),
    ) -> None:
        self.reducer = reducer
        self.histogram_quantiles = tuple(float(q) for q in histogram_quantiles)
        for q in self.histogram_quantiles:
            if not (0.0 < q < 1.0):
                raise ValueError(
                    f"histogram_quantiles must be in (0, 1); got {q!r}"
                )
        self.histogram_extras = tuple(str(x) for x in histogram_extras)
        for x in self.histogram_extras:
            if x not in self._VALID_EXTRAS:
                raise ValueError(
                    f"histogram_extras must be subset of {self._VALID_EXTRAS}; got {x!r}"
                )

    def read_context(self, payload: Union[str, Mapping[str, Any]]) -> Dict[str, float]:
        data = json.loads(payload) if isinstance(payload, str) else payload
        grouped: Dict[str, List[MetricPoint]] = {}
        histograms: Dict[str, List[Mapping[str, Any]]] = {}
        for metric in self._iter_metrics(data):
            name = str(metric.get("name", ""))
            if not name:
                continue
            if "histogram" in metric:
                histograms.setdefault(name, []).extend(
                    metric.get("histogram", {}).get("dataPoints", [])
                )
                continue
            for point in self._metric_points(metric):
                grouped.setdefault(name, []).append(point)

        context: Dict[str, float] = {
            name: reduce_points(points, self.reducer)
            for name, points in grouped.items()
        }
        if self.histogram_quantiles or self.histogram_extras:
            for name, points in histograms.items():
                context.update(self._expand_histogram(name, points))
        return context

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

    def _expand_histogram(
        self,
        name: str,
        points: Sequence[Mapping[str, Any]],
    ) -> Dict[str, float]:
        if not points:
            return {}
        merged_counts: Optional[List[float]] = None
        merged_bounds: Optional[Tuple[float, ...]] = None
        total_sum = 0.0
        total_count = 0.0
        for point in points:
            bucket_counts = point.get("bucketCounts")
            explicit_bounds = point.get("explicitBounds")
            if bucket_counts is None or explicit_bounds is None:
                # Skip malformed datapoints rather than raising — OTel allows
                # exemplars-only points without bucket data.
                continue
            counts = [float(c) for c in bucket_counts]
            bounds = tuple(float(b) for b in explicit_bounds)
            if len(counts) != len(bounds) + 1:
                raise ValueError(
                    f"histogram {name!r}: bucketCounts has len {len(counts)}"
                    f" but explicitBounds has len {len(bounds)} (expect +1)"
                )
            if merged_counts is None:
                merged_counts = counts
                merged_bounds = bounds
            else:
                if bounds != merged_bounds:
                    raise ValueError(
                        f"histogram {name!r}: cannot merge datapoints with"
                        " different explicitBounds; pre-aggregate upstream"
                    )
                merged_counts = [a + b for a, b in zip(merged_counts, counts)]
            total_sum += float(point.get("sum", 0.0))
            total_count += float(point.get("count", sum(counts)))
        if merged_counts is None or merged_bounds is None:
            return {}
        out: Dict[str, float] = {}
        for q in self.histogram_quantiles:
            out[f"{name}__p{int(round(q * 100))}"] = quantile_from_histogram(
                merged_counts, merged_bounds, q
            )
        if "avg" in self.histogram_extras:
            out[f"{name}__avg"] = total_sum / total_count if total_count > 0 else 0.0
        if "count" in self.histogram_extras:
            out[f"{name}__count"] = total_count
        if "sum" in self.histogram_extras:
            out[f"{name}__sum"] = total_sum
        return out


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


def quantile_from_histogram(
    bucket_counts: Sequence[float],
    explicit_bounds: Sequence[float],
    q: float,
) -> float:
    """Estimate the ``q``-th quantile of a bucketed histogram.

    Follows the Prometheus / OTel convention:

    * ``bucket_counts`` holds the *per-bucket* sample counts (not cumulative).
      ``len(bucket_counts) == len(explicit_bounds) + 1`` — the last entry is
      the ``+Inf`` overflow bucket.
    * ``explicit_bounds`` is strictly increasing and each bound is the
      **inclusive upper edge** of its bucket (e.g. bound ``0.1`` means samples
      with value ≤ 0.1 fall into that bucket).
    * ``q`` must be in ``(0, 1)``.

    The estimate uses linear interpolation within the target bucket, clamped
    to the previous bound from below. When the target bucket is the ``+Inf``
    overflow, the returned value is the last finite bound — we refuse to
    extrapolate beyond observed bounds. When the target bucket is the first
    finite bucket and the previous bound is implicit, interpolation starts at
    ``0.0`` (we don't invent a negative lower edge).
    """

    if not (0.0 < q < 1.0):
        raise ValueError(f"q must be in (0, 1); got {q!r}")
    counts = [float(c) for c in bucket_counts]
    if not counts:
        raise ValueError("bucket_counts must be non-empty")
    bounds = [float(b) for b in explicit_bounds]
    if len(counts) != len(bounds) + 1:
        raise ValueError(
            "len(bucket_counts) must equal len(explicit_bounds) + 1"
        )
    for i in range(1, len(bounds)):
        if bounds[i] <= bounds[i - 1]:
            raise ValueError("explicit_bounds must be strictly increasing")
    total = sum(counts)
    if total <= 0:
        raise ValueError("histogram has zero samples; quantile is undefined")

    target = q * total
    cumulative = 0.0
    for idx, c in enumerate(counts):
        prev = cumulative
        cumulative += c
        if cumulative < target:
            continue
        # Target bucket found.
        if idx == len(bounds):
            # +Inf overflow — refuse to extrapolate beyond observed bounds.
            return bounds[-1] if bounds else 0.0
        upper = bounds[idx]
        lower = bounds[idx - 1] if idx > 0 else 0.0
        if c <= 0 or upper <= lower:
            return upper
        # Linear interpolation: assume samples are uniform within the bucket.
        frac = (target - prev) / c
        return lower + frac * (upper - lower)
    # If we fell through (shouldn't happen after the total>0 guard), return
    # the last finite bound.
    return bounds[-1] if bounds else 0.0


__all__ = [
    "MetricPoint",
    "PrometheusQuery",
    "PrometheusHTTPClient",
    "PrometheusContextReader",
    "OpenTelemetryJSONMetricReader",
    "reduce_points",
    "quantile_from_histogram",
]
