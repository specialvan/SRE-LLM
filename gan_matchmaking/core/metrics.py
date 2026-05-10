"""In-process metrics registry with a Prometheus-style surface.

Why not prometheus_client
-------------------------
We want the package to stay dependency-free. The registry here implements
just enough of the Prometheus data model to:

- collect counters / gauges / histograms from any module,
- snapshot for unit tests,
- export to the standard text exposition format for sidecars that scrape us.

Thread safety
-------------
All mutating operations take a per-registry :class:`threading.Lock`. The
metric primitives store plain ``float`` / ``int`` samples so there is no
per-sample lock contention for callers on the hot path.
"""
from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


LabelTuple = Tuple[Tuple[str, str], ...]


def _norm_labels(labels: Optional[Dict[str, str]]) -> LabelTuple:
    if not labels:
        return ()
    return tuple(sorted((str(k), str(v)) for k, v in labels.items()))


class _MetricBase:
    def __init__(self, name: str, description: str, label_names: Sequence[str] = ()):
        self.name = name
        self.description = description
        self.label_names = tuple(label_names)
        self._lock = threading.Lock()

    def _check(self, labels: Optional[Dict[str, str]]) -> LabelTuple:
        keys = set(labels or {})
        expected = set(self.label_names)
        if keys != expected:
            raise ValueError(
                f"metric {self.name!r} expects labels {sorted(expected)} "
                f"but got {sorted(keys)}"
            )
        return _norm_labels(labels)


class Counter(_MetricBase):
    """Monotonically increasing float counter."""

    def __init__(self, name: str, description: str, label_names: Sequence[str] = ()):
        super().__init__(name, description, label_names)
        self._values: Dict[LabelTuple, float] = {}

    def inc(self, amount: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        if amount < 0:
            raise ValueError("Counter.inc amount must be >= 0")
        key = self._check(labels)
        with self._lock:
            self._values[key] = self._values.get(key, 0.0) + amount

    def value(self, labels: Optional[Dict[str, str]] = None) -> float:
        key = self._check(labels)
        with self._lock:
            return self._values.get(key, 0.0)

    def snapshot(self) -> Dict[LabelTuple, float]:
        with self._lock:
            return dict(self._values)


class Gauge(_MetricBase):
    """Arbitrary float gauge."""

    def __init__(self, name: str, description: str, label_names: Sequence[str] = ()):
        super().__init__(name, description, label_names)
        self._values: Dict[LabelTuple, float] = {}

    def set(self, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        if math.isnan(value):
            raise ValueError("Gauge.set received NaN")
        key = self._check(labels)
        with self._lock:
            self._values[key] = float(value)

    def inc(self, amount: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        key = self._check(labels)
        with self._lock:
            self._values[key] = self._values.get(key, 0.0) + amount

    def value(self, labels: Optional[Dict[str, str]] = None) -> float:
        key = self._check(labels)
        with self._lock:
            return self._values.get(key, 0.0)

    def snapshot(self) -> Dict[LabelTuple, float]:
        with self._lock:
            return dict(self._values)


@dataclass
class _HistBucket:
    count: int = 0
    sum: float = 0.0
    buckets: Dict[float, int] = field(default_factory=dict)


class Histogram(_MetricBase):
    """Cumulative histogram (Prometheus-style).

    The ``buckets`` parameter is in *upper bounds*; a final ``+Inf`` bucket is
    appended automatically.
    """

    _DEFAULT = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

    def __init__(
        self,
        name: str,
        description: str,
        label_names: Sequence[str] = (),
        buckets: Sequence[float] = _DEFAULT,
    ):
        super().__init__(name, description, label_names)
        if not buckets:
            raise ValueError("buckets must be non-empty")
        sorted_buckets = tuple(sorted(float(b) for b in buckets))
        self.buckets = sorted_buckets + (math.inf,)
        self._values: Dict[LabelTuple, _HistBucket] = {}

    def observe(self, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        if math.isnan(value):
            raise ValueError("Histogram.observe received NaN")
        key = self._check(labels)
        with self._lock:
            bucket = self._values.setdefault(key, _HistBucket(buckets={b: 0 for b in self.buckets}))
            bucket.count += 1
            bucket.sum += float(value)
            for upper in self.buckets:
                if value <= upper:
                    bucket.buckets[upper] += 1

    def snapshot(self) -> Dict[LabelTuple, Dict[str, float]]:
        with self._lock:
            out: Dict[LabelTuple, Dict[str, float]] = {}
            for k, b in self._values.items():
                out[k] = {
                    "count": b.count,
                    "sum": b.sum,
                    "buckets": dict(b.buckets),
                }
            return out


class MetricsRegistry:
    """Process-wide container for metrics."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._metrics: Dict[str, _MetricBase] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------
    def counter(self, name: str, description: str,
                label_names: Sequence[str] = ()) -> Counter:
        return self._register(Counter(name, description, label_names))

    def gauge(self, name: str, description: str,
              label_names: Sequence[str] = ()) -> Gauge:
        return self._register(Gauge(name, description, label_names))

    def histogram(self, name: str, description: str,
                  label_names: Sequence[str] = (),
                  buckets: Optional[Sequence[float]] = None) -> Histogram:
        if buckets is None:
            hist = Histogram(name, description, label_names)
        else:
            hist = Histogram(name, description, label_names, buckets)
        return self._register(hist)

    def _register(self, metric):
        with self._lock:
            if metric.name in self._metrics:
                existing = self._metrics[metric.name]
                if type(existing) is not type(metric):
                    raise ValueError(
                        f"metric {metric.name!r} already registered with a different type"
                    )
                return existing
            self._metrics[metric.name] = metric
            return metric

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------
    def get(self, name: str) -> Optional[_MetricBase]:
        with self._lock:
            return self._metrics.get(name)

    def snapshot(self) -> Dict[str, Dict]:
        with self._lock:
            metrics = list(self._metrics.items())
        out: Dict[str, Dict] = {}
        for name, m in metrics:
            if isinstance(m, Histogram):
                out[name] = {"type": "histogram", "samples": m.snapshot()}
            elif isinstance(m, Gauge):
                out[name] = {"type": "gauge", "samples": m.snapshot()}
            else:
                out[name] = {"type": "counter", "samples": m.snapshot()}
        return out

    # ------------------------------------------------------------------
    # Exposition
    # ------------------------------------------------------------------
    def export_prometheus(self) -> str:
        """Render all metrics in Prometheus text exposition format."""
        lines: List[str] = []
        with self._lock:
            metrics = list(self._metrics.items())
        for name, m in metrics:
            lines.append(f"# HELP {name} {m.description}")
            if isinstance(m, Counter):
                lines.append(f"# TYPE {name} counter")
                for labels, value in m.snapshot().items():
                    lines.append(f"{name}{_labels_str(labels)} {value}")
            elif isinstance(m, Gauge):
                lines.append(f"# TYPE {name} gauge")
                for labels, value in m.snapshot().items():
                    lines.append(f"{name}{_labels_str(labels)} {value}")
            elif isinstance(m, Histogram):
                lines.append(f"# TYPE {name} histogram")
                for labels, payload in m.snapshot().items():
                    for upper in m.buckets:
                        label_le = labels + (("le", _fmt_bucket(upper)),)
                        lines.append(
                            f"{name}_bucket{_labels_str(label_le)} {payload['buckets'][upper]}"
                        )
                    lines.append(f"{name}_count{_labels_str(labels)} {payload['count']}")
                    lines.append(f"{name}_sum{_labels_str(labels)} {payload['sum']}")
        return "\n".join(lines) + ("\n" if lines else "")


def _labels_str(labels: LabelTuple) -> str:
    if not labels:
        return ""
    inner = ",".join(f'{k}="{v}"' for k, v in labels)
    return "{" + inner + "}"


def _fmt_bucket(upper: float) -> str:
    if math.isinf(upper):
        return "+Inf"
    return repr(upper)


# Default process-global registry. Tests instantiate their own for isolation.
default_registry = MetricsRegistry()
