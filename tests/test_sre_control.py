"""Tests for the SRE control primitives distilled from Attention Residuals."""

from __future__ import annotations

import numpy as np
import pytest

from attention_residuals.sre_control import (
    AuditTrail,
    BlockSpec,
    BudgetGate,
    DecoupledControlLoop,
    HierarchicalBlockController,
    MustAttendRegistry,
    SignalSpec,
    WeightedConvexCombiner,
    _project_to_simplex_with_bounds,
)


# ---------------------------------------------------------------------------
# Primitive 1 · WeightedConvexCombiner
# ---------------------------------------------------------------------------

def test_combiner_weights_sum_to_one():
    signals = [SignalSpec("slo"), SignalSpec("queue"), SignalSpec("cost")]
    c = WeightedConvexCombiner(signals, query_dim=4)
    q = np.ones(4)
    values = [np.array([1.0]), np.array([-1.0]), np.array([0.0])]
    _, w = c.combine(q, values)
    assert np.isclose(w.sum(), 1.0, atol=1e-6)
    # Weights must sit inside their (default) [0, 1] bounds.
    assert np.all(w >= 0) and np.all(w <= 1)


def test_combiner_respects_floor():
    """Must-attend: a signal with floor=0.3 must receive at least 30% weight."""
    signals = [
        SignalSpec("slo"),
        SignalSpec("budget_burn", floor=0.3),
        SignalSpec("cost"),
    ]
    c = WeightedConvexCombiner(signals, query_dim=3)
    # Provide a query that, without the floor, would drown the budget signal.
    c.W_K = np.array([[10.0, 0.0, 0.0],
                      [0.0, 0.0, 0.0],
                      [10.0, 0.0, 0.0]])
    q = np.array([1.0, 0.0, 0.0])
    values = [np.array([0.0]), np.array([0.0]), np.array([0.0])]
    _, w = c.combine(q, values)
    assert np.isclose(w.sum(), 1.0, atol=1e-6)
    assert w[1] >= 0.3 - 1e-6, f"budget_burn got {w[1]:.3f}, expected ≥ 0.3"


def test_combiner_respects_ceiling():
    signals = [
        SignalSpec("aggressive", ceiling=0.4),
        SignalSpec("conservative"),
    ]
    c = WeightedConvexCombiner(signals, query_dim=2)
    c.W_K = np.array([[10.0, 0.0], [-10.0, 0.0]])
    q = np.array([1.0, 0.0])
    _, w = c.combine(q, [np.array([1.0]), np.array([0.0])])
    assert w[0] <= 0.4 + 1e-6
    assert np.isclose(w.sum(), 1.0, atol=1e-6)


def test_combiner_infeasible_floors_raise():
    """If floors sum to > 1, no convex combination exists."""
    with pytest.raises(ValueError):
        WeightedConvexCombiner(
            [SignalSpec("a", floor=0.6), SignalSpec("b", floor=0.6)],
            query_dim=1,
        )


def test_simplex_projection_boundary_cases():
    # Over-ceiling input → must clip.
    out = _project_to_simplex_with_bounds(
        np.array([1.2, -0.2]),
        floors=np.array([0.0, 0.0]),
        ceilings=np.array([1.0, 1.0]),
    )
    assert np.isclose(out.sum(), 1.0)
    assert np.all(out >= 0) and np.all(out <= 1)


# ---------------------------------------------------------------------------
# Primitive 2 · AuditTrail
# ---------------------------------------------------------------------------

def test_audit_trail_records_and_serializes():
    signals = [SignalSpec("slo"), SignalSpec("cost")]
    c = WeightedConvexCombiner(signals, query_dim=2)
    trail = AuditTrail()
    action, _ = c.combine(np.ones(2), [np.array([1.0]), np.array([0.0])])
    rec = trail.record(c, action, context={"qps": 1000.0})
    assert rec.step == 0
    assert rec.signal_names == ["slo", "cost"]
    text = trail.to_jsonl()
    assert "slo" in text and "cost" in text
    assert len(trail) == 1


def test_audit_requires_prior_combine():
    signals = [SignalSpec("a")]
    c = WeightedConvexCombiner(signals, query_dim=1)
    trail = AuditTrail()
    with pytest.raises(RuntimeError):
        trail.record(c, np.array([0.0]))


# ---------------------------------------------------------------------------
# Primitive 3 · DecoupledControlLoop
# ---------------------------------------------------------------------------

def test_decoupled_loop_slow_loop_ticks_at_period():
    fast = WeightedConvexCombiner(
        [SignalSpec("p99"), SignalSpec("qps")],
        query_dim=2,
    )
    slow = WeightedConvexCombiner(
        [SignalSpec("budget"), SignalSpec("trend")],
        query_dim=2,
    )
    loop = DecoupledControlLoop(fast, slow, slow_period=3, alpha=0.5)
    fast_q = np.ones(2)
    slow_q = np.ones(2)
    fast_vals = [np.array([1.0]), np.array([-1.0])]
    slow_vals = [np.array([2.0]), np.array([0.0])]
    # First call → slow must fire.
    _, info = loop.step(fast_q, fast_vals, slow_q, slow_vals)
    first_slow = info["slow_action"]
    # Second & third call → slow reuses cached result.
    for _ in range(2):
        _, info = loop.step(fast_q, fast_vals, slow_q, slow_vals)
        assert np.allclose(info["slow_action"], first_slow)
    # Fourth call → slow fires again (tick=3 % 3 == 0).
    _, info = loop.step(fast_q, fast_vals, slow_q, slow_vals)
    assert np.allclose(info["slow_action"], first_slow)   # deterministic inputs

    # Both loops expose their own weights independently.
    assert info["fast_weights"] is not None
    assert info["slow_weights"] is not None


# ---------------------------------------------------------------------------
# Primitive 4 · HierarchicalBlockController
# ---------------------------------------------------------------------------

def test_hierarchical_controller_runs_end_to_end():
    # Two blocks (e.g. AZ-east / AZ-west), each with its own local policy.
    def _mk_block(name: str, key: np.ndarray) -> BlockSpec:
        local = WeightedConvexCombiner(
            [SignalSpec("slo"), SignalSpec("cost")], query_dim=2,
        )
        return BlockSpec(name=name, local_combiner=local, block_key=key)

    blocks = [
        _mk_block("east", np.array([1.0, 0.0])),
        _mk_block("west", np.array([0.0, 1.0])),
    ]
    ctrl = HierarchicalBlockController(blocks, global_query_dim=2)
    action, info = ctrl.step(
        per_block_queries=[np.ones(2), np.ones(2)],
        per_block_values=[
            [np.array([1.0]), np.array([-1.0])],
            [np.array([1.0]), np.array([-1.0])],
        ],
        global_query=np.array([0.7, 0.3]),
    )
    assert action.shape == (1,)
    assert info["block_actions"].shape == (2, 1)
    assert np.isclose(info["global_weights"].sum(), 1.0, atol=1e-6)
    # The global query projects more onto the east block key → east wins.
    assert info["global_weights"][0] > info["global_weights"][1]


def test_hierarchical_block_key_shape_mismatch_raises():
    def _mk(name: str, key: np.ndarray) -> BlockSpec:
        local = WeightedConvexCombiner([SignalSpec("x")], query_dim=1)
        return BlockSpec(name=name, local_combiner=local, block_key=key)

    bad = [_mk("a", np.array([1.0, 2.0]))]       # key is 2-dim
    with pytest.raises(ValueError):
        HierarchicalBlockController(bad, global_query_dim=1)   # ← expected 1-dim


# ---------------------------------------------------------------------------
# Primitive 5 · BudgetGate
# ---------------------------------------------------------------------------

def test_budget_gate_enforces_floor():
    gate = BudgetGate(n_gates=4, budget_floor=0.5,
                      init_logits=[-5.0, -5.0, -5.0, -5.0])  # all near-closed
    g = gate.gates()
    assert g.sum() >= 0.5 * 4 - 1e-6
    assert np.all(g <= 1.0)


def test_budget_gate_all_open_by_default():
    gate = BudgetGate(n_gates=3)
    g = gate.gates()
    # Default logits 4.6 → σ ≈ 0.99.
    assert np.all(g > 0.98)


def test_budget_gate_logit_update():
    gate = BudgetGate(n_gates=2, budget_floor=0.0, init_logits=[0.0, 0.0])
    assert np.allclose(gate.gates(), [0.5, 0.5])
    gate.update_logits(np.array([2.0, -2.0]))
    g = gate.gates()
    assert g[0] > g[1]


# ---------------------------------------------------------------------------
# Primitive 6 · MustAttendRegistry
# ---------------------------------------------------------------------------

def test_must_attend_registry_floor_propagates():
    reg = MustAttendRegistry()
    reg.register("budget_burn", 0.2)
    reg.register("security_alert", 0.1)
    s = reg.spec("budget_burn")
    assert s.floor == 0.2
    assert reg.total_floor() == pytest.approx(0.3)
    # Unknown signals get floor=0 — no penalty for not registering.
    assert reg.spec("cost").floor == 0.0
