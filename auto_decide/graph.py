"""Interaction Intent Graph — §1.1.

Implements the discrete layer of the decision system::

    G_I = (V_I, E_I)

where ``V_I`` are traffic participants (vehicles, pedestrians, bikes,
static obstacles) and ``E_I`` are *intent-weighted* directed edges whose
weights describe how strongly one participant's behaviour influences
another.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional, Tuple

import numpy as np

from .types import AgentType


# ---------------------------------------------------------------------------
# Nodes & edges
# ---------------------------------------------------------------------------

@dataclass
class Node:
    """A node of G_I (§1.1).

    ``intent`` is a categorical probability distribution over high-level
    maneuvers (straight / left / right / yield / stop). Intents feed the
    conflict term of the edge weight; an unknown upstream can just leave
    it uniform.
    """
    node_id: str
    type: AgentType
    position: np.ndarray                # shape (2,) — (x, y) in meters
    velocity: np.ndarray                # shape (2,) — (vx, vy) in m/s
    intent: Dict[str, float] = field(default_factory=lambda: {
        "straight": 1.0, "left": 0.0, "right": 0.0, "yield": 0.0, "stop": 0.0
    })

    def as_array(self) -> np.ndarray:
        return np.concatenate([self.position, self.velocity])


@dataclass
class Edge:
    """Directed, weighted edge with intent semantics."""
    src: str
    dst: str
    weight: float                       # ∈ [0, 1], cf. §1.1
    conflict_type: str = "generic"      # e.g. "merge", "cross", "follow"


# ---------------------------------------------------------------------------
# Intent conflict priors
# ---------------------------------------------------------------------------

_CONFLICT_TABLE: Mapping[Tuple[str, str], float] = {
    ("straight", "left"): 0.7,
    ("left", "straight"): 0.7,
    ("straight", "right"): 0.3,
    ("right", "straight"): 0.3,
    ("left", "left"): 0.4,
    ("right", "right"): 0.4,
    ("left", "right"): 0.2,
    ("right", "left"): 0.2,
    ("straight", "straight"): 0.2,
    ("stop", "straight"): 0.05,
    ("yield", "straight"): 0.05,
}


def intent_conflict(p_i: Mapping[str, float], p_j: Mapping[str, float]) -> float:
    """Expected conflict probability given two intent distributions.

    Computes ``E_{a~p_i, b~p_j}[C(a, b)]`` where C is a hand-crafted
    conflict table. Returns a value in [0, 1].
    """
    total = 0.0
    for a, pa in p_i.items():
        for b, pb in p_j.items():
            total += pa * pb * _CONFLICT_TABLE.get((a, b), 0.1)
    return float(min(max(total, 0.0), 1.0))


# ---------------------------------------------------------------------------
# The graph itself
# ---------------------------------------------------------------------------

class InteractionIntentGraph:
    """Time-varying directed graph of interacting agents (§1.1).

    The weight on an edge (i → j) is::

        w_ij = g(d_ij) · heading_penalty(i, j) · intent_conflict(p_i, p_j)

    with ``g(d) = exp(-d / d0)`` a distance kernel.
    """

    #: distance scale (meters) above which coupling decays
    D0: float = 15.0
    #: ignore edges weaker than this for downstream consumers
    EPS: float = 1e-3

    def __init__(self) -> None:
        self._nodes: Dict[str, Node] = {}
        self._edges: Dict[Tuple[str, str], Edge] = {}

    # ---- CRUD -------------------------------------------------------------
    def add_node(self, node: Node) -> None:
        self._nodes[node.node_id] = node

    def remove_node(self, node_id: str) -> None:
        self._nodes.pop(node_id, None)
        self._edges = {k: v for k, v in self._edges.items()
                       if node_id not in k}

    def add_edge(self, edge: Edge) -> None:
        self._edges[(edge.src, edge.dst)] = edge

    # ---- accessors --------------------------------------------------------
    @property
    def nodes(self) -> Iterable[Node]:
        return self._nodes.values()

    @property
    def edges(self) -> Iterable[Edge]:
        return self._edges.values()

    def neighbors(self, node_id: str) -> List[Node]:
        return [self._nodes[dst] for (src, dst) in self._edges
                if src == node_id and dst in self._nodes]

    def to_adjacency(self) -> np.ndarray:
        """Return a dense adjacency matrix ordered by insertion."""
        ids = list(self._nodes)
        n = len(ids)
        idx = {nid: i for i, nid in enumerate(ids)}
        A = np.zeros((n, n), dtype=float)
        for (s, d), e in self._edges.items():
            if s in idx and d in idx:
                A[idx[s], idx[d]] = e.weight
        return A

    # ---- update rule ------------------------------------------------------
    def update(self, dt: float = 0.0) -> None:
        """Refresh edge weights from current geometry.

        ``dt`` is accepted for API symmetry — the weight depends on current
        geometry only, but callers may pre-advance node states before
        calling :meth:`update`.
        """
        self._edges.clear()
        node_list = list(self._nodes.values())
        for i, ni in enumerate(node_list):
            for j, nj in enumerate(node_list):
                if i == j:
                    continue
                w = self._edge_weight(ni, nj)
                if w >= self.EPS:
                    self.add_edge(Edge(ni.node_id, nj.node_id, w))

    # ---- weight kernel ----------------------------------------------------
    @classmethod
    def _edge_weight(cls, i: Node, j: Node) -> float:
        d = float(np.linalg.norm(i.position - j.position))
        dist_kernel = np.exp(-d / cls.D0)

        # heading alignment: edges pointing toward each other matter more
        vi, vj = i.velocity, j.velocity
        rel = j.position - i.position
        rnorm = np.linalg.norm(rel)
        if rnorm < 1e-6 or np.linalg.norm(vi) < 1e-6:
            heading = 0.5
        else:
            cos_theta = float(np.dot(vi, rel) / (np.linalg.norm(vi) * rnorm))
            # Map [-1, 1] to [0, 1]; approaching (cos>0) gets higher penalty.
            heading = 0.5 * (cos_theta + 1.0)

        conflict = intent_conflict(i.intent, j.intent)
        return float(dist_kernel * heading * conflict)
