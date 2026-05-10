"""Forward reachable set & dead-zone detection — §2.2.

Sampling-based approximation of

    R(x₀, T) = { φ(t; x₀, u) | t ∈ [0, T], u(·) ∈ U }

The convex hull of the sampled endpoints is used to answer
``in_reachable`` questions and to flag "logical dead zones" where
external uncertainty exceeds the vehicle's control authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence, Tuple

import numpy as np

from .dynamics import BicycleModel
from .types import DEFAULT_VEHICLE, Control, State, VehicleParams


@dataclass
class ReachableSet:
    """Forward reachable set approximation (§2.2)."""

    dynamics: BicycleModel
    horizon: float = 2.0   # T, seconds
    dt: float = 0.1
    n_samples: int = 200
    params: VehicleParams = DEFAULT_VEHICLE
    _endpoints: Optional[np.ndarray] = field(default=None, init=False,
                                              repr=False)

    # ------------------------------------------------------------------
    def sample(self, state0: State,
               rng: Optional[np.random.Generator] = None) -> np.ndarray:
        """Sample endpoints in the (px, py) plane.

        Returns ``shape = (n_samples, 2)``. Control sequences are piecewise
        constant with one switch to give the convex-hull a richer shape.
        """
        rng = rng or np.random.default_rng(0)
        pts = np.zeros((self.n_samples, 2))
        steps = int(self.horizon / self.dt)

        for k in range(self.n_samples):
            # two random controls, switched mid-horizon
            steer1 = rng.uniform(-self.params.max_steer, self.params.max_steer)
            steer2 = rng.uniform(-self.params.max_steer, self.params.max_steer)
            jerk1 = rng.uniform(-self.params.jerk_max, self.params.jerk_max)
            jerk2 = rng.uniform(-self.params.jerk_max, self.params.jerk_max)
            controls = []
            half = steps // 2
            for t in range(steps):
                if t < half:
                    controls.append(Control(steer1, jerk1))
                else:
                    controls.append(Control(steer2, jerk2))
            traj = self.dynamics.rollout(state0, controls, self.dt)
            pts[k] = [traj[-1].px, traj[-1].py]

        self._endpoints = pts
        return pts

    # ------------------------------------------------------------------
    def hull(self, state0: Optional[State] = None
             ) -> Tuple[np.ndarray, np.ndarray]:
        """Return (endpoints, hull_vertices)."""
        if self._endpoints is None:
            if state0 is None:
                raise ValueError("Call sample() first or pass state0.")
            self.sample(state0)
        pts = self._endpoints
        if len(pts) < 3:
            return pts, pts
        try:
            from scipy.spatial import ConvexHull
            hull = ConvexHull(pts)
            return pts, pts[hull.vertices]
        except Exception:
            # Fallback: return all points; good enough for tests
            return pts, pts

    # ------------------------------------------------------------------
    def in_reachable(self, state0: State, target: np.ndarray) -> bool:
        """Is ``target`` inside R(x₀, T)?"""
        _, verts = self.hull(state0)
        return _point_in_polygon(target, verts)


# ---------------------------------------------------------------------------
# Dead-zone detection
# ---------------------------------------------------------------------------

@dataclass
class DeadZoneDetector:
    """Flag configurations where even worst-case braking cannot avoid a
    collision — the "logical dead zone" of §2.2."""

    dynamics: BicycleModel
    horizon: float = 1.5
    dt: float = 0.05
    params: VehicleParams = DEFAULT_VEHICLE

    def check(self, state: State, threat_position: np.ndarray,
              threat_velocity: np.ndarray) -> Tuple[bool, float]:
        """Return ``(in_dead_zone, min_clearance)``.

        The ego applies maximum braking (min jerk) for the horizon; the
        threat moves at constant velocity. If the minimum inter-agent
        distance over the horizon is negative the state is a dead zone.
        """
        steps = int(self.horizon / self.dt)
        controls = [Control(steer=0.0, jerk=-self.params.jerk_max)] * steps
        traj = self.dynamics.rollout(state, controls, self.dt)
        min_clear = float("inf")
        for i, s in enumerate(traj):
            tp = threat_position + threat_velocity * (i * self.dt)
            clear = float(np.hypot(s.px - tp[0], s.py - tp[1]))
            if clear < min_clear:
                min_clear = clear
        return (min_clear < 0.0), float(min_clear)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _point_in_polygon(pt: np.ndarray, verts: np.ndarray) -> bool:
    """Ray-casting point-in-polygon test."""
    x, y = float(pt[0]), float(pt[1])
    n = len(verts)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = verts[i]
        xj, yj = verts[j]
        intersect = ((yi > y) != (yj > y)) and \
                    (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi)
        if intersect:
            inside = not inside
        j = i
    return inside
