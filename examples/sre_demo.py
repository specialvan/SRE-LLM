"""SRE self-iteration demo.

Runs the :class:`SelfIterationPipeline` through a synthetic sequence of
release observations, then asks for a decision on a new candidate set.

Run as ``python -m examples.sre_demo`` from the ``gan/`` directory.
"""
from __future__ import annotations

import json
from pathlib import Path

from gan_matchmaking.core import AppConfig, MetricsRegistry
from gan_matchmaking.sre import (
    ReleaseCandidate,
    ReleaseContext,
    SelfIterationPipeline,
    Service,
)


def main() -> None:
    pipeline = SelfIterationPipeline(config=AppConfig(seed=42),
                                     metrics=MetricsRegistry())

    # Register three services with different tiers.
    api = Service(id="payments-api", mu=0.997, sigma=0.005, tier="critical")
    worker = Service(id="billing-worker", mu=0.985, sigma=0.015, tier="standard")
    experiment = Service(id="fraud-lab", mu=0.92, sigma=0.04, tier="experiment")
    for s in (api, worker, experiment):
        pipeline.register_service(s)

    # Replay 40 recent releases — mostly successes, with the experiment
    # service doing worse.
    history = [
        ("payments-api", True), ("payments-api", True),
        ("payments-api", False), ("payments-api", True), ("payments-api", True),
        ("billing-worker", True), ("billing-worker", True),
        ("billing-worker", True), ("billing-worker", False),
        ("fraud-lab", False), ("fraud-lab", True), ("fraud-lab", False),
    ] * 4
    for sid, ok in history:
        pipeline.observe_release(sid, success=ok)

    # Build a realistic decision context for the critical payments-api.
    candidates = [
        ReleaseCandidate(
            id="canary-5pct",
            service_id=api.id,
            strategy="canary",
            canary_fraction=0.05,
            rollback_budget_seconds=300,
            expected_success=0.996,
            notes="5% canary, standard ramp",
        ),
        ReleaseCandidate(
            id="canary-25pct",
            service_id=api.id,
            strategy="canary",
            canary_fraction=0.25,
            rollback_budget_seconds=600,
            expected_success=0.990,
        ),
        ReleaseCandidate(
            id="full-rollout",
            service_id=api.id,
            strategy="full",
            canary_fraction=0.0,
            rollback_budget_seconds=600,
            expected_success=0.994,
        ),
    ]
    telemetry = {
        "error_rate_p99": 0.004,
        "latency_p99_ms": 137.0,
        "throughput_rps": 4200.0,
        "memory_rss_mb": 512.0,
    }
    ctx = ReleaseContext(
        service=api,
        candidates=candidates,
        telemetry=telemetry,
        dependencies=["billing-worker"],
        error_budget_remaining=0.72,
    )

    decision = pipeline.decide(ctx)

    print("=== SRE decision ===")
    print(json.dumps(decision.to_dict(), indent=2, ensure_ascii=False))

    # Dump the prom-format metric snapshot so reviewers see what the pipeline
    # emits as Prometheus scrape content.
    print("\n=== metrics snapshot (Prometheus exposition) ===")
    print(pipeline.metrics.export_prometheus())

    out_path = Path(__file__).with_name("sre_trace.jsonl")
    out_path.write_text(json.dumps(decision.to_dict(), ensure_ascii=False) + "\n",
                        encoding="utf-8")
    print(f"\nTrace written to {out_path}")


if __name__ == "__main__":
    main()
