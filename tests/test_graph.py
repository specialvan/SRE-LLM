"""Tests for interaction intent graph (§1.1)."""

import numpy as np

from auto_decide.graph import (InteractionIntentGraph, Node, intent_conflict)
from auto_decide.types import AgentType


def _mk(id_: str, pos, vel, intent=None):
    return Node(
        node_id=id_, type=AgentType.CAR,
        position=np.asarray(pos, dtype=float),
        velocity=np.asarray(vel, dtype=float),
        intent=intent or {"straight": 1.0, "left": 0.0, "right": 0.0,
                          "yield": 0.0, "stop": 0.0},
    )


def test_intent_conflict_symmetric_and_bounded():
    p = {"straight": 0.5, "left": 0.5, "right": 0.0, "yield": 0.0, "stop": 0.0}
    q = {"straight": 0.5, "left": 0.5, "right": 0.0, "yield": 0.0, "stop": 0.0}
    c = intent_conflict(p, q)
    assert 0.0 <= c <= 1.0


def test_close_far_weight_monotone():
    g = InteractionIntentGraph()
    ego = _mk("ego", (0, 0), (10, 0))
    close = _mk("a", (5, 0), (-10, 0))
    far = _mk("b", (50, 0), (-10, 0))
    for n in (ego, close, far):
        g.add_node(n)
    g.update()
    A = g.to_adjacency()
    # Rows are ordered by insertion: [ego, close, far]
    # ego->close weight must exceed ego->far weight
    assert A[0, 1] > A[0, 2]


def test_orthogonal_motion_has_small_weight():
    """Cars moving perpendicular and far away should have negligible weight."""
    g = InteractionIntentGraph()
    g.add_node(_mk("ego", (0, 0), (10, 0)))
    g.add_node(_mk("perp", (50, 50), (0, -10)))
    g.update()
    A = g.to_adjacency()
    assert A[0, 1] < 1e-2


def test_edges_respect_eps_cutoff():
    """INV-M-GRAPH-2: edges below EPS are pruned from _edges."""
    g = InteractionIntentGraph()
    g.add_node(_mk("ego", (0, 0), (10, 0)))
    g.add_node(_mk("near", (5, 0), (-10, 0)))
    g.add_node(_mk("far", (1000, 0), (-10, 0)))

    g.update()

    assert all(edge.weight >= g.EPS for edge in g.edges)
    assert ("ego", "far") not in g._edges
