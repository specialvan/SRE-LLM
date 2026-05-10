"""Latency benchmark for :meth:`SelfIterationPipeline.decide`.

Run as::

    python -m bench.latency --iterations 2000
    python -m bench.latency --quick            # fast smoke for CI

Outputs a JSON report to stdout so CI can store / diff it.

SLO target
----------
p50 < 5 ms, p99 < 25 ms on a single commodity core. The script asserts
against a relaxed threshold by default; override with ``--p99-ms``.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from typing import List

from gan_matchmaking.core import AppConfig, MetricsRegistry
from gan_matchmaking.sre import (
    ReleaseCandidate,
    ReleaseContext,
    SelfIterationPipeline,
    Service,
)


def _build_ctx() -> ReleaseContext:
    svc = Service(id="svc-bench", mu=0.99, sigma=0.02, tier="standard")
    cands = [
        ReleaseCandidate(id=f"c{i}", service_id="svc-bench",
                         strategy="canary",
                         canary_fraction=0.05 + 0.05 * (i % 3),
                         rollback_budget_seconds=180,
                         expected_success=0.99 - 0.005 * (i % 4))
        for i in range(5)
    ]
    telemetry = {"error_rate_p99": 0.002,
                 "latency_p99_ms": 120.0,
                 "throughput_rps": 4800.0,
                 "memory_rss_mb": 512.0}
    return ReleaseContext(service=svc, candidates=cands,
                           telemetry=telemetry,
                           dependencies=["dep-a", "dep-b"],
                           error_budget_remaining=0.8)


def _run(iterations: int) -> List[float]:
    pipeline = SelfIterationPipeline(config=AppConfig(seed=0),
                                     metrics=MetricsRegistry())
    ctx = _build_ctx()
    # Warm-up.
    for _ in range(10):
        pipeline.decide(ctx)
    samples_ms: List[float] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        pipeline.decide(ctx)
        samples_ms.append((time.perf_counter() - t0) * 1000.0)
    return samples_ms


def _summarise(samples_ms: List[float]) -> dict:
    s = sorted(samples_ms)
    p = lambda q: s[int(min(len(s) - 1, max(0, round(q * (len(s) - 1)))))]
    return {
        "n": len(s),
        "min_ms": s[0],
        "p50_ms": p(0.50),
        "p90_ms": p(0.90),
        "p95_ms": p(0.95),
        "p99_ms": p(0.99),
        "max_ms": s[-1],
        "mean_ms": statistics.fmean(s),
        "stdev_ms": statistics.pstdev(s),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=2000)
    parser.add_argument("--quick", action="store_true",
                         help="use 200 iterations, skip SLO assert.")
    parser.add_argument("--p99-ms", type=float, default=50.0)
    args = parser.parse_args(argv)

    iters = 200 if args.quick else args.iterations
    samples = _run(iters)
    report = _summarise(samples)
    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")

    if not args.quick and report["p99_ms"] > args.p99_ms:
        print(f"PERF REGRESSION: p99={report['p99_ms']:.2f} ms > {args.p99_ms} ms",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
