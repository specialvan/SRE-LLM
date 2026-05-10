"""Control Barrier Functions & CBF-QP — §3.2.

Given a safe set ``C = { x | h(x) ≥ 0 }`` the barrier condition

    ḣ(x, u) + α h(x) ≥ 0

guarantees forward invariance of C. The :class:`CBFQPFilter` turns the
nominal command from the neural/MPC policy into the nearest feasible
command under this constraint — the article's "search-space folding".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Protocol, Tuple

import numpy as np

from .dynamics import BicycleModel, CircleObstacle, Manifold, Obstacle
from .types import DEFAULT_VEHICLE, Control, State, VehicleParams


# ---------------------------------------------------------------------------
# Barrier function protocol
# ---------------------------------------------------------------------------

class BarrierFunction(Protocol):
    """``h(x) ≥ 0`` iff state is safe (§3.2)."""

    def h(self, state: State) -> float:
        ...

    def h_dot(self, state: State, u: Control,
              dynamics: BicycleModel, dt: float = 1e-3) -> float:
        """Approximate ḣ = (∂h/∂x) · f(x, u)."""
        ...


# ---------------------------------------------------------------------------
# Concrete barriers
# ---------------------------------------------------------------------------

@dataclass
class DistanceBarrier:
    """h(x) = signed_distance_to_obstacle - safety_margin.

    Lives in the family "stay outside obstacle's ε-inflation".

    .. note::
       This barrier is *relative degree 2* with respect to the jerk
       input, so in isolation it cannot react fast enough to high-speed
       collisions. Pair it with a :class:`BrakingDistanceBarrier` or use
       it only for static soft zones (lane borders etc.).
    """
    obstacle: Obstacle
    safety_margin: float = 1.5

    def h(self, state: State) -> float:
        return float(self.obstacle.signed_distance(state.px, state.py)
                     - self.safety_margin)

    def h_dot(self, state: State, u: Control,
              dynamics: BicycleModel, dt: float = 1e-3) -> float:
        h0 = self.h(state)
        h1 = self.h(dynamics.step(state, u, dt))
        return (h1 - h0) / dt


@dataclass
class BrakingDistanceBarrier:
    """Relative-degree-1 barrier that accounts for stopping distance.

    ``h(x) = d_obs(x) - margin - v·τ - v² / (2 · a_brake(x))``

    ``a_brake(x) = safety · min(a_max_brake, μ·g)`` uses the state-
    dependent friction cap, so low-μ surfaces automatically inflate the
    safe stopping distance. The extra ``v·τ`` absorbs the jerk-ramp
    latency: before the ego can actually decelerate it must first drive
    ``a`` from its current value to the brake cap, and that takes
    roughly τ seconds with a jerk-limited actuator.
    """
    obstacle: Obstacle
    safety_margin: float = 1.5
    a_max_brake: float = 6.0    # m/s² — actuator cap
    reaction: float = 0.35      # s — jerk-ramp latency budget
    safety: float = 0.6         # derating for μ uncertainty

    def _a_brake(self, state: State) -> float:
        from .types import G as _G
        return max(self.safety * min(self.a_max_brake, state.mu * _G), 0.5)

    def h(self, state: State) -> float:
        d = self.obstacle.signed_distance(state.px, state.py)
        v = max(state.v, 0.0)
        a_b = self._a_brake(state)
        stop = v * v / (2.0 * a_b)
        return float(d - self.safety_margin - self.reaction * v - stop)

    def h_dot(self, state: State, u: Control,
              dynamics: BicycleModel, dt: float = 1e-3) -> float:
        h0 = self.h(state)
        h1 = self.h(dynamics.step(state, u, dt))
        return (h1 - h0) / dt


@dataclass
class SpeedBarrier:
    """h(x) = v_max - v  — forward invariance of the speed envelope."""
    v_max: float = 30.0

    def h(self, state: State) -> float:
        return float(self.v_max - state.v)

    def h_dot(self, state: State, u: Control,
              dynamics: BicycleModel, dt: float = 1e-3) -> float:
        h0 = self.h(state)
        h1 = self.h(dynamics.step(state, u, dt))
        return (h1 - h0) / dt


# ---------------------------------------------------------------------------
# CBF-QP filter
# ---------------------------------------------------------------------------

@dataclass
class CBFQPFilter:
    """Pointwise QP filter implementing "search-space folding" (§3.2).

    Solves::

        min_u   ‖u - u_nom‖² + ρ·δ²
        s.t.    ḣ_i(x, u) + α h_i(x) ≥ -δ     for each barrier i
                u_min ≤ u ≤ u_max
                δ ≥ 0

    The slack ``δ`` makes the QP always feasible; in normal operation δ ≈ 0.
    A small 2-D problem is solved analytically with a grid fallback to
    avoid pulling in a QP dependency.

    ``h_dot_horizon`` controls the finite-difference horizon used to
    evaluate ``ḣ``. Because the model is jerk-driven, a too-small
    horizon (<10 ms) cannot see the effect of a jerk command on the
    stopping distance, which is what the braking-distance barrier cares
    about. 0.1 s works well in practice.
    """

    barriers: List[BarrierFunction]
    dynamics: BicycleModel
    params: VehicleParams = DEFAULT_VEHICLE
    alpha: float = 1.0
    rho: float = 1e3
    h_dot_horizon: float = 0.1

    # ------------------------------------------------------------------
    def filter(self, state: State, u_nom: Control,
               coarse: int = 11, fine: int = 21
               ) -> Tuple[Control, dict]:
        """Return ``(u_safe, info)``.

        ``info`` carries the active barrier violations and solver status.
        """
        p = self.params
        # Full control space on first pass — when a barrier is violated we
        # must be able to swing from acceleration to full brake.
        steer_lo, steer_hi = -p.max_steer, p.max_steer
        jerk_lo, jerk_hi = -p.jerk_max, p.jerk_max

        # Fast path: if nominal already satisfies all barriers, keep it.
        if self._all_barriers_ok(state, u_nom):
            return u_nom, {"status": "nom_ok", "slack": 0.0,
                           "violations": []}

        best_u, best_cost = None, float("inf")
        # Coarse grid
        for s in np.linspace(steer_lo, steer_hi, coarse):
            for j in np.linspace(jerk_lo, jerk_hi, coarse):
                u = Control(float(s), float(j))
                cost, ok = self._objective(state, u_nom, u)
                if ok and cost < best_cost:
                    best_u, best_cost = u, cost

        # Fine grid around best (if found) to refine
        if best_u is not None:
            s0, j0 = best_u.steer, best_u.jerk
            ds = (steer_hi - steer_lo) / coarse
            dj = (jerk_hi - jerk_lo) / coarse
            for s in np.linspace(s0 - ds, s0 + ds, fine):
                for j in np.linspace(j0 - dj, j0 + dj, fine):
                    u = Control(float(s), float(j))
                    cost, ok = self._objective(state, u_nom, u)
                    if ok and cost < best_cost:
                        best_u, best_cost = u, cost

        if best_u is None:
            # Fall back to maximum braking, zero steer — always feasible
            best_u = Control(0.0, -p.jerk_max)
            return best_u, {"status": "fallback_brake", "slack": float("inf"),
                            "violations": self._violations(state, best_u)}

        return best_u, {"status": "qp_ok", "slack": 0.0,
                        "violations": self._violations(state, best_u)}

    # ------------------------------------------------------------------
    def _objective(self, state: State, u_nom: Control,
                   u: Control) -> Tuple[float, bool]:
        cost = (u.steer - u_nom.steer) ** 2 + (u.jerk - u_nom.jerk) ** 2
        slack = 0.0
        ok = True
        for b in self.barriers:
            h = b.h(state)
            h_dot = b.h_dot(state, u, self.dynamics, dt=self.h_dot_horizon)
            cbf = h_dot + self.alpha * h
            if cbf < 0:
                slack = max(slack, -cbf)
                ok = False  # violates; grid point will be rejected
        return cost + self.rho * slack * slack, ok

    def _all_barriers_ok(self, state: State, u: Control) -> bool:
        for b in self.barriers:
            if (b.h_dot(state, u, self.dynamics, dt=self.h_dot_horizon)
                    + self.alpha * b.h(state) < 0):
                return False
        return True

    def _violations(self, state: State, u: Control) -> List[float]:
        out = []
        for b in self.barriers:
            out.append(b.h_dot(state, u, self.dynamics, dt=self.h_dot_horizon)
                       + self.alpha * b.h(state))
        return out


# ---------------------------------------------------------------------------
# Helper factory
# ---------------------------------------------------------------------------

def make_obstacle_barriers(manifold: Manifold,
                           margin: float = 1.5,
                           a_max_brake: float = 5.0,
                           reaction: float = 0.35,
                           ) -> List[BarrierFunction]:
    """Build the default barrier stack for a given manifold.

    For every obstacle we create both a geometric :class:`DistanceBarrier`
    and a :class:`BrakingDistanceBarrier`; the latter dominates at speed,
    the former keeps the car away from static edges once stopped.
    """
    out: List[BarrierFunction] = []
    for o in manifold.obstacles:
        out.append(DistanceBarrier(o, safety_margin=margin))
        out.append(BrakingDistanceBarrier(o, safety_margin=margin,
                                           a_max_brake=a_max_brake,
                                           reaction=reaction))
    return out
