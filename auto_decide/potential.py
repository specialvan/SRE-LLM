"""Potential field & constrained gradient flow — §1.3.

Encodes the paper's view of autonomous driving as

    ẋ = -∇Φ(x)

with Φ a composite potential mixing goal-tracking, collision risk and
traffic rules. The flow is *constrained* because the resulting gradient
must be projected back onto the feasible tangent space (the "non-
cooperative game projection" in §1.3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence

import numpy as np

from .dynamics import Manifold
from .graph import InteractionIntentGraph
from .types import State


# ---------------------------------------------------------------------------
# Potential terms
# ---------------------------------------------------------------------------

def goal_potential(state: State, goal: np.ndarray,
                   weight: float = 1.0) -> float:
    """Attractive term — quadratic well at the goal position."""
    d = np.array([state.px - goal[0], state.py - goal[1]])
    return 0.5 * weight * float(d @ d)


def obstacle_potential(state: State, manifold: Manifold,
                       safety_radius: float = 2.5,
                       weight: float = 10.0) -> float:
    """Repulsive term — smooth barrier-like potential near obstacles."""
    if not manifold.obstacles:
        return 0.0
    total = 0.0
    for obs in manifold.obstacles:
        d = obs.signed_distance(state.px, state.py)
        if d < safety_radius:
            # 1/d^2 blows up too hard; use (safety/d - 1)^2 for smoothness
            clip = max(d, 0.05)
            total += weight * (safety_radius / clip - 1.0) ** 2
    return float(total)


def interaction_potential(state: State,
                          graph: InteractionIntentGraph,
                          ego_id: str = "ego",
                          weight: float = 5.0) -> float:
    """Repulsive term weighted by the intent-graph edge w_ij (§1.1/§1.3).

    For each neighbour j with edge weight w_ij we add ``w_ij / d_ij``.
    """
    total = 0.0
    for edge in graph.edges:
        if edge.src != ego_id:
            continue
        # Look up the neighbour node
        for node in graph.nodes:
            if node.node_id == edge.dst:
                d = float(np.hypot(state.px - node.position[0],
                                    state.py - node.position[1]))
                total += edge.weight / max(d, 0.5)
                break
    return float(weight * total)


# ---------------------------------------------------------------------------
# Composite potential field
# ---------------------------------------------------------------------------

@dataclass
class PotentialField:
    """Composite Φ(x) from §1.3.

    Components can be swapped or reweighted without touching the rest of
    the planner — that mirrors the article's claim that the structure is
    what matters, not the exact statistical fit.
    """
    goal: np.ndarray = field(default_factory=lambda: np.zeros(2))
    w_goal: float = 1.0
    w_obs: float = 10.0
    w_interact: float = 5.0
    safety_radius: float = 2.5

    # ----- value -------------------------------------------------------
    def value(self, state: State, manifold: Manifold,
              graph: Optional[InteractionIntentGraph] = None,
              ego_id: str = "ego") -> float:
        phi = goal_potential(state, self.goal, self.w_goal)
        phi += obstacle_potential(state, manifold, self.safety_radius,
                                   self.w_obs)
        if graph is not None:
            phi += interaction_potential(state, graph, ego_id,
                                          self.w_interact)
        return float(phi)

    # ----- gradient (numerical, in position only) ----------------------
    def grad_xy(self, state: State, manifold: Manifold,
                graph: Optional[InteractionIntentGraph] = None,
                ego_id: str = "ego", eps: float = 1e-3) -> np.ndarray:
        """Return ∂Φ/∂(px, py) at ``state`` (2-d vector)."""
        def _eval(px: float, py: float) -> float:
            perturbed = State(px=px, py=py, psi=state.psi, v=state.v,
                              a=state.a, mu=state.mu)
            return self.value(perturbed, manifold, graph, ego_id)

        base = _eval(state.px, state.py)
        gx = (_eval(state.px + eps, state.py) - base) / eps
        gy = (_eval(state.px, state.py + eps) - base) / eps
        return np.array([gx, gy])

    # ----- constrained flow direction ----------------------------------
    def flow_direction(self, state: State, manifold: Manifold,
                       graph: Optional[InteractionIntentGraph] = None,
                       ego_id: str = "ego") -> np.ndarray:
        """Return the desired ẋ direction in the (px, py) plane.

        This is the article's ``ẋ = -∇Φ``; the downstream CBF filter plays
        the role of the "projection onto the feasible tangent space".
        """
        g = self.grad_xy(state, manifold, graph, ego_id)
        direction = -g
        norm = np.linalg.norm(direction)
        return direction / norm if norm > 1e-6 else direction
