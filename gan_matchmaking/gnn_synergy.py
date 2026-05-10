"""§5 GNN team-synergy graph.

Article formula (image-4.png), one layer of message passing:

    h_i^{l+1} = ReLU( W^{l} h_i^{l} + sum_{j in N(i)} W^{l}_{ij} h_j^{l} )

We implement a lightweight numpy GNN:

- ``SynergyGraph`` accumulates historical co-play and win statistics.
- ``SynergyGNN`` runs a 2-layer message-passing forward pass on the adjacency
  derived from the graph, producing node embeddings ``h_i``.
- ``synergy_score(i, j) = <h_i, h_j>`` estimates how well two players play
  together relative to the population average.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Tuple

import numpy as np


def _relu(x: np.ndarray) -> np.ndarray:
    return np.maximum(x, 0.0)


@dataclass
class SynergyGraph:
    # co_play[(i, j)] = number of matches they were on the same team together.
    co_play: Dict[Tuple[str, str], int] = field(default_factory=dict)
    # wins_together[(i, j)] = number of those matches they won together.
    wins_together: Dict[Tuple[str, str], int] = field(default_factory=dict)
    players: List[str] = field(default_factory=list)

    def _key(self, a: str, b: str) -> Tuple[str, str]:
        return (a, b) if a < b else (b, a)

    def add_match(self, team: Iterable[str], win: bool) -> None:
        """Record one match for the given team (list of player ids)."""
        team = list(team)
        for i, a in enumerate(team):
            if a not in self.players:
                self.players.append(a)
            for b in team[i + 1:]:
                if b not in self.players:
                    self.players.append(b)
                key = self._key(a, b)
                self.co_play[key] = self.co_play.get(key, 0) + 1
                if win:
                    self.wins_together[key] = self.wins_together.get(key, 0) + 1

    def adjacency(self, min_games: int = 1) -> Tuple[List[str], np.ndarray]:
        """Return ``(nodes, A)`` where ``A[i,j]`` is the synergy weight.

        Weight uses a Wilson-like shrinkage around 0.5 win rate so that pairs
        with few co-play games contribute less:

            w_ij = (wins_together + 1) / (co_play + 2) - 0.5
        """
        nodes = list(self.players)
        idx = {n: i for i, n in enumerate(nodes)}
        n = len(nodes)
        A = np.zeros((n, n), dtype=float)
        for (a, b), games in self.co_play.items():
            if games < min_games:
                continue
            wins = self.wins_together.get((a, b), 0)
            w = (wins + 1.0) / (games + 2.0) - 0.5
            A[idx[a], idx[b]] = w
            A[idx[b], idx[a]] = w
        return nodes, A


@dataclass
class SynergyGNN:
    hidden_dim: int = 8
    layers: int = 2
    seed: int = 42

    def __post_init__(self) -> None:
        self._rng = np.random.default_rng(self.seed)
        self._W: List[np.ndarray] = []
        self._U: List[np.ndarray] = []

    def _init_weights(self, in_dim: int) -> None:
        self._W = []
        self._U = []
        d_in = in_dim
        for _ in range(self.layers):
            # Xavier-ish init.
            scale_w = np.sqrt(2.0 / (d_in + self.hidden_dim))
            scale_u = np.sqrt(2.0 / (d_in + self.hidden_dim))
            self._W.append(self._rng.normal(0.0, scale_w, size=(d_in, self.hidden_dim)))
            self._U.append(self._rng.normal(0.0, scale_u, size=(d_in, self.hidden_dim)))
            d_in = self.hidden_dim

    def forward(self, features: np.ndarray, adj: np.ndarray) -> np.ndarray:
        """Run message passing.

        - ``features``: ``(N, d0)`` initial node features.
        - ``adj``: ``(N, N)`` weighted (possibly signed) adjacency.
        """
        if features.ndim != 2:
            raise ValueError("features must be (N, d)")
        h = np.asarray(features, dtype=float)
        if not self._W:
            self._init_weights(h.shape[1])
        for W, U in zip(self._W, self._U):
            msg = adj @ h
            h = _relu(h @ W + msg @ U)
        return h

    def synergy_score(self, h: np.ndarray, i: int, j: int) -> float:
        """Inner-product synergy between node ``i`` and node ``j``."""
        return float(np.dot(h[i], h[j]))
