"""Tests for :mod:`gan_matchmaking.core.metrics`."""
from __future__ import annotations

import math

import pytest

from gan_matchmaking.core.metrics import (
    Counter,
    Gauge,
    Histogram,
    MetricsRegistry,
)


def test_counter_monotonic():
    c = Counter("hits", "doc", label_names=("kind",))
    c.inc(2.5, labels={"kind": "ok"})
    c.inc(1.0, labels={"kind": "ok"})
    assert c.value(labels={"kind": "ok"}) == pytest.approx(3.5)


def test_counter_rejects_negative():
    c = Counter("hits", "doc")
    with pytest.raises(ValueError):
        c.inc(-1.0)


def test_counter_rejects_wrong_labels():
    c = Counter("hits", "doc", label_names=("kind",))
    with pytest.raises(ValueError):
        c.inc(labels={"other": "x"})


def test_gauge_nan_rejected():
    g = Gauge("temp", "doc")
    with pytest.raises(ValueError):
        g.set(math.nan)


def test_histogram_buckets_are_cumulative():
    h = Histogram("latency", "doc", buckets=(0.1, 1.0))
    for v in (0.05, 0.5, 0.9, 1.5):
        h.observe(v)
    snap = h.snapshot()[tuple()]
    assert snap["count"] == 4
    # 0.1 bucket: only 0.05 ≤ 0.1
    assert snap["buckets"][0.1] == 1
    # 1.0 bucket: 0.05, 0.5, 0.9 all ≤ 1.0
    assert snap["buckets"][1.0] == 3
    # +Inf bucket: all four.
    assert snap["buckets"][math.inf] == 4


def test_registry_dedup_and_prometheus_export():
    reg = MetricsRegistry()
    c1 = reg.counter("req_total", "total")
    c2 = reg.counter("req_total", "total")
    assert c1 is c2

    c1.inc(3)
    g = reg.gauge("queue_depth", "doc")
    g.set(7)
    text = reg.export_prometheus()
    assert "# HELP req_total total" in text
    assert "req_total 3" in text
    assert "queue_depth 7" in text


def test_registry_rejects_type_conflict():
    reg = MetricsRegistry()
    reg.counter("x", "doc")
    with pytest.raises(ValueError):
        reg.gauge("x", "doc")
