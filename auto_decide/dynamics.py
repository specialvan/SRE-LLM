"""Continuous layer — §1.2.

Nonlinear manifold of the ego vehicle plus obstacles that carve out
"void" regions. Dynamics use a kinematic bicycle model extended with a
jerk-driven acceleration channel so that the friction constraint
|a| ≤ μ·g is handled smoothly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Protocol, Sequence

import numpy as np

from .types import (DEFAULT_VEHICLE, G, Control, State, VehicleParams)


# ---------------------------------------------------------------------------
# Obstacles & manifold
# ---------------------------------------------------------------------------

class Obstacle(Protocol):
    """Static or dynamic obstacle carving a void in state space (§1.2)."""

    def signed_distance(self, px: float, py: float) -> float:
        """Positive outside, zero on boundary, negative inside."""
        ...


@dataclass
class CircleObstacle:
    """Circular obstacle — the simplest nontrivial ``void`` region."""
    cx: float
    cy: float
    radius: float

    def signed_distance(self, px: float, py: float) -> float:
        return float(np.hypot(px - self.cx, py - self.cy) - self.radius)


@dataclass
class RectObstacle:
    """Axis-aligned rectangular obstacle."""
    cx: float
    cy: float
    half_w: float
    half_h: float

    def signed_distance(self, px: float, py: float) -> float:
        dx = max(abs(px - self.cx) - self.half_w, 0.0)
        dy = max(abs(py - self.cy) - self.half_h, 0.0)
        outside = float(np.hypot(dx, dy))
        inside = min(
            max(abs(px - self.cx) - self.half_w, abs(py - self.cy) - self.half_h),
            0.0,
        )
        return outside + inside


@dataclass
class Manifold:
    """The feasible part of state space — article §1.2.

    ``is_feasible`` checks that the state is (a) outside every obstacle and
    (b) within the speed / friction envelope.
    """
    obstacles: List[Obstacle]
    params: VehicleParams = DEFAULT_VEHICLE

    def is_feasible(self, state: State) -> bool:
        if state.v < -0.01 or state.v > self.params.v_max * 1.05:
            return False
        if abs(state.a) > state.mu * G + 1e-3:
            return False
        for obs in self.obstacles:
            if obs.signed_distance(state.px, state.py) < 0:
                return False
        return True

    def min_distance(self, state: State) -> float:
        if not self.obstacles:
            return float("inf")
        return min(o.signed_distance(state.px, state.py) for o in self.obstacles)


# ---------------------------------------------------------------------------
# Bicycle model: ẋ = f(x, u)
# ---------------------------------------------------------------------------

class BicycleModel:
    """Kinematic bicycle with jerk-driven acceleration.

    State  : x  = [px, py, psi, v, a, mu]
    Input  : u  = [steer, jerk]
    Output : ẋ = f(x, u)          — the continuous dynamics of §1.2

    The friction constraint |a| ≤ μ·g is enforced *at integration time*:
    if the commanded ``a`` would violate it, ``a_dot`` is clamped so the
    envelope is never crossed (the article's "tyre envelope on the
    manifold").
    """

    def __init__(self, params: VehicleParams = DEFAULT_VEHICLE) -> None:
        self.params = params

    # ------------------------------------------------------------------
    def f(self, state: State, u: Control) -> np.ndarray:
        """Return dx/dt — shape (6,)."""
        p = self.params
        steer = np.clip(u.steer, -p.max_steer, p.max_steer)
        jerk = np.clip(u.jerk, -p.jerk_max, p.jerk_max)

        # Friction envelope — clip jerk so that |a| stays ≤ μ·g
        a_cap = state.mu * G
        if state.a >= a_cap and jerk > 0:
            jerk = 0.0
        elif state.a <= -a_cap and jerk < 0:
            jerk = 0.0

        px_dot = state.v * np.cos(state.psi)
        py_dot = state.v * np.sin(state.psi)
        psi_dot = state.v / p.wheelbase * np.tan(steer)
        v_dot = state.a
        a_dot = jerk
        mu_dot = 0.0
        return np.array([px_dot, py_dot, psi_dot, v_dot, a_dot, mu_dot])

    # ------------------------------------------------------------------
    def step(self, state: State, u: Control, dt: float) -> State:
        """RK4 forward integration of f for one step of ``dt`` seconds."""
        x0 = state.to_vec()

        def _eval(xv: np.ndarray) -> np.ndarray:
            return self.f(State.from_vec(xv), u)

        k1 = _eval(x0)
        k2 = _eval(x0 + 0.5 * dt * k1)
        k3 = _eval(x0 + 0.5 * dt * k2)
        k4 = _eval(x0 + dt * k3)
        x1 = x0 + dt * (k1 + 2 * k2 + 2 * k3 + k4) / 6.0

        # Post-step clamp: enforce friction envelope
        a_cap = x1[5] * G
        x1[4] = float(np.clip(x1[4], -a_cap, a_cap))
        x1[3] = float(max(0.0, min(x1[3], self.params.v_max)))  # speed ≥ 0
        return State.from_vec(x1)

    # ------------------------------------------------------------------
    def rollout(self, state: State, controls: Sequence[Control],
                dt: float) -> List[State]:
        """Roll the dynamics forward for a list of controls."""
        trajectory = [state]
        cur = state
        for u in controls:
            cur = self.step(cur, u, dt)
            trajectory.append(cur)
        return trajectory
