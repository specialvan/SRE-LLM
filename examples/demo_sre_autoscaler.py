"""End-to-end SRE demo: hierarchical autoscaler driven by Attention-Residual primitives.

Scenario
--------
A global service runs in two regions (``east`` / ``west``), each with its own
local autoscaler. Every region fuses three signals into a replica-delta
recommendation:

    slo_violation  — P99 latency vs SLO target
    queue_depth    — pending requests
    error_budget   — remaining error budget (must-attend, floor=0.25)

A global controller then merges the regions' recommendations, weighted by how
much each region matters to the SLA at this moment. On top of that we run a
fast / slow decoupled loop: the fast loop responds every second; the slow loop
only kicks in every 10 seconds and enforces capacity planning priors.

The goal is not to "win" on a benchmark; it is to *demonstrate the primitives
in action* and produce a useful audit trail.

Run with::

    python -m examples.demo_sre_autoscaler
"""

from __future__ import annotations

import numpy as np

from attention_residuals.sre_control import (
    AuditTrail,
    BlockSpec,
    BudgetGate,
    DecoupledControlLoop,
    HierarchicalBlockController,
    MustAttendRegistry,
    SignalSpec,
    WeightedConvexCombiner,
)


# ---------------------------------------------------------------------------
# 1. Register "must-attend" signals at the fleet level.
# ---------------------------------------------------------------------------

registry = MustAttendRegistry()
registry.register("error_budget", 0.25)   # never ignore budget burn
registry.register("security_alert", 0.0)  # registered but not floored here


def _fmt_vec(v) -> str:
    if v is None:
        return "n/a"
    return "[" + ", ".join(f"{x:.2f}" for x in v) + "]"


def make_local_combiner() -> WeightedConvexCombiner:
    signals = [
        SignalSpec("slo_violation"),
        SignalSpec("queue_depth"),
        registry.spec("error_budget"),    # floor=0.25 enforced
    ]
    return WeightedConvexCombiner(signals, query_dim=3, temperature=0.8)


# ---------------------------------------------------------------------------
# 2. Build the hierarchical controller (one block per region).
# ---------------------------------------------------------------------------

east = BlockSpec(
    name="east",
    local_combiner=make_local_combiner(),
    block_key=np.array([1.0, 0.0]),
)
west = BlockSpec(
    name="west",
    local_combiner=make_local_combiner(),
    block_key=np.array([0.0, 1.0]),
)
hier = HierarchicalBlockController([east, west], global_query_dim=2)


# ---------------------------------------------------------------------------
# 3. Fast / slow decoupled outer loop.
# ---------------------------------------------------------------------------

fast_loop = WeightedConvexCombiner(
    [SignalSpec("p99"), SignalSpec("rps")],
    query_dim=2, temperature=0.5,
)
slow_loop = WeightedConvexCombiner(
    [SignalSpec("budget_trend"), SignalSpec("forecast")],
    query_dim=2, temperature=1.5,
)
outer = DecoupledControlLoop(fast_loop, slow_loop, slow_period=10, alpha=0.4)


# ---------------------------------------------------------------------------
# 4. Budget gate: never drain more than 50% of replicas.
# ---------------------------------------------------------------------------

gate = BudgetGate(n_gates=2, budget_floor=0.5)


# ---------------------------------------------------------------------------
# 5. Simulate 30 ticks of traffic.
# ---------------------------------------------------------------------------

def synth_signals(tick: int, region: str) -> tuple[np.ndarray, list[np.ndarray]]:
    """Produce a query and a list of per-signal proposed replica deltas.

    Delta semantics: positive ⇒ scale up, negative ⇒ scale down.
    """
    t = tick / 30.0
    bias = 0.0 if region == "east" else 0.3        # west is currently hotter
    slo_hot = max(0.0, np.sin(4 * t) + bias)        # oscillating SLO violation
    queue   = max(0.0, np.cos(3 * t) + bias)
    budget  = 0.6 if tick < 15 else 0.15            # budget burns out mid-run
    query = np.array([slo_hot, queue, 1.0 - budget])
    values = [
        np.array([+4.0 * slo_hot]),       # scale up proportional to SLO pain
        np.array([+2.0 * queue]),         # scale up if queues are deep
        np.array([+6.0 * (1.0 - budget)]),# scale up hard when budget runs low
    ]
    return query, values


trail = AuditTrail()

print(f"{'tick':>4}  {'region':>6}  {'local_a (slo,q,budget)':<28}  "
      f"{'global_a (E,W)':<20}  {'replicas Δ':>10}")
for tick in range(30):
    # --- per-block local signals
    q_east, v_east = synth_signals(tick, "east")
    q_west, v_west = synth_signals(tick, "west")

    # Global query: weight the region by current heat (sum of its query vec).
    heat_east = q_east.sum()
    heat_west = q_west.sum()
    global_q = np.array([heat_east, heat_west])
    global_q = global_q / (global_q.sum() + 1e-9)

    block_action, info = hier.step(
        per_block_queries=[q_east, q_west],
        per_block_values=[v_east, v_west],
        global_query=global_q,
    )

    # --- outer fast/slow loop ---
    fast_q = np.array([max(heat_east, heat_west), tick / 30.0])
    slow_q = np.array([1.0 - 0.6 if tick < 15 else 1.0 - 0.15, tick / 30.0])
    fast_vals = [np.array([block_action.item()]), np.array([0.5 * block_action.item()])]
    slow_vals = [np.array([+3.0]),                np.array([+1.0])]
    merged, outer_info = outer.step(fast_q, fast_vals, slow_q, slow_vals)

    # --- budget gate drains
    drain_gates = gate.gates()

    # --- audit for each region
    for region, combiner, q, v in [
        ("east", east.local_combiner, q_east, v_east),
        ("west", west.local_combiner, q_west, v_west),
    ]:
        # Re-use the weights already stored on the combiner.
        w = combiner.last_weights()
        if w is None:
            continue
        # Action from this region's local combiner (already computed inside hier.step).
        local_action = (w[:, None] * np.stack(v, axis=0)).sum(axis=0)
        trail.record(combiner, local_action, context={
            "tick": float(tick),
            "region": 0.0 if region == "east" else 1.0,
            "heat": float(q.sum()),
        })

    local_e = hier.blocks[0].local_combiner.last_weights()
    local_w = hier.blocks[1].local_combiner.last_weights()
    global_a = info["global_weights"]
    print(
        f"{tick:>4}  {'east':>6}  "
        f"{_fmt_vec(local_e):<28}  {_fmt_vec(global_a):<20}  "
        f"{merged.item():>+10.2f}"
    )
    if tick % 10 == 9:
        print(
            f"{tick:>4}  {'west':>6}  {_fmt_vec(local_w):<28}  "
            f"{'(same global)':<20}  gates={drain_gates.round(3).tolist()}"
        )


print(f"\nAudit records: {len(trail)}")
print("First three records (JSON-ish):")
for rec in list(trail)[:3]:
    print("  ", rec.as_dict())
