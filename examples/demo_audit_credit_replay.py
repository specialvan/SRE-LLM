"""Replay AuditTrail JSONL into TemporalCreditAssigner.

This is the bridge from synthetic in-process demos to production-shaped
logs: the controller writes audit JSONL, and a later post-mortem job
replays those lines into temporal credit attribution.

Run with::

    python -m examples.demo_audit_credit_replay
"""

from __future__ import annotations

import numpy as np

from attention_residuals.sre_control import AuditTrail, SignalSpec, WeightedConvexCombiner
from attention_residuals.sre_math import (
    AuditCreditReplay,
    MetricLossMapper,
    MetricLossSpec,
    TemporalCreditAssigner,
)


def main() -> None:
    combiner = WeightedConvexCombiner(
        [SignalSpec("controller"), SignalSpec("traffic")],
        query_dim=2,
        rng_seed=0,
    )
    combiner.W_K = np.array([
        [1.0, 0.0],
        [0.0, 1.0],
    ])
    trail = AuditTrail()

    for tick in range(30):
        if tick < 15:
            query = np.array([0.1, 2.0])
            ctx = {"controller_error": 0.1, "traffic_spike": 3.0}
        else:
            query = np.array([2.0, 0.1])
            ctx = {"controller_error": 4.0, "traffic_spike": 0.2}
        action, _ = combiner.combine(
            query,
            [np.array([2.0]), np.array([1.0])],
        )
        ctx["tick"] = float(tick)
        trail.record(combiner, action, context=ctx)

    jsonl = trail.to_jsonl()
    tca = TemporalCreditAssigner(decay=0.92)
    replay = AuditCreditReplay(
        tca,
        MetricLossMapper({
            "controller": MetricLossSpec("controller_error", mode="raw"),
            "traffic": MetricLossSpec("traffic_spike", mode="raw"),
        }),
    )
    count = replay.replay_jsonl(jsonl)
    blamed = tca.attribute(incident_tick=29, window=12, top_k=6)

    print("=" * 78)
    print("Audit JSONL -> TemporalCreditAssigner replay")
    print("=" * 78)
    print(f"Audit records replayed: {count}")
    print(f"JSONL bytes          : {len(jsonl.encode('utf-8'))}")
    print()
    print(f"{'rank':>4} {'tick':>4} {'signal':>12} {'weight':>8} {'loss':>8} {'score':>8}")
    for i, entry in enumerate(blamed, start=1):
        print(
            f"{i:>4} {entry.tick:>4} {entry.signal_name:>12} "
            f"{entry.weight:>8.3f} {entry.loss:>8.3f} {entry.score:>8.3f}"
        )

    print()
    print("Reading: the replay job reconstructs blame from audit logs only.")


if __name__ == "__main__":
    main()
