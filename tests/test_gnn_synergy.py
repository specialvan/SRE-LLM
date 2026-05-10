"""Tests for the synergy graph / GNN (§5)."""
from __future__ import annotations

import numpy as np

from gan_matchmaking import SynergyGNN, SynergyGraph


def test_graph_accumulates_wins_together():
    g = SynergyGraph()
    g.add_match(["a", "b", "c"], win=True)
    g.add_match(["a", "b"], win=True)
    g.add_match(["a", "b"], win=False)
    key_ab = ("a", "b")
    assert g.co_play[key_ab] == 3
    assert g.wins_together[key_ab] == 2


def test_gnn_forward_shape():
    g = SynergyGraph()
    g.add_match(["a", "b", "c"], win=True)
    g.add_match(["b", "c", "d"], win=False)
    nodes, A = g.adjacency()
    feats = np.random.default_rng(0).normal(size=(len(nodes), 4))
    gnn = SynergyGNN(hidden_dim=8, layers=2, seed=1)
    h = gnn.forward(feats, A)
    assert h.shape == (len(nodes), 8)
    assert np.all(h >= 0.0)  # ReLU on final layer.
