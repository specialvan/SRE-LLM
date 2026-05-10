"""Lyapunov stability — §2.1.

The paper's "physical red line":

    dV(x)/dt ≤ 0

must hold along every trajectory produced by the planner. This module
gives a default quadratic Lyapunov candidate plus a monitor that the
downstream ``ControlInvariantOperator`` can query.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, Tuple

import numpy as np

from .dynamics import BicycleModel, Manifold
from .types import Control, State


class LyapunovFn(Protocol):
    """Lyapunov function protocol (§2.1)."""

    def V(self, state: State, target_speed: float) -> float:
        ...

    def dV_dt(self, state: State, u: Control,
              dynamics: BicycleModel, manifold: Manifold,
              target_speed: float, dt: float = 0.01) -> float:
        ...


# ---------------------------------------------------------------------------
# Default implementation
# ---------------------------------------------------------------------------

@dataclass
class QuadraticLyapunov:
    """A minimal Lyapunov candidate focused on velocity tracking.

    ``V(x) = 0.5 q_v (v - v*)²``

    Pure stability / tracking term — safety (distance) is handled by
    control-barrier functions, mirroring the article's separation
    between "stability hard constraint" and "safety hard constraint".
    """
    q_v: float = 1.0
    eps: float = 0.2

    # ------------------------------------------------------------------
    def V(self, state: State, target_speed: float) -> float:
        dv = state.v - target_speed
        return 0.5 * self.q_v * dv * dv

    def V_full(self, state: State, manifold: Manifold,
               target_speed: float) -> float:
        """Alias of :meth:`V` — kept for backward compatibility.

        ``manifold`` is accepted but not used: the distance term lives in
        the CBF, not in V.
        """
        return self.V(state, target_speed)

    # ------------------------------------------------------------------
    def dV_dt(self, state: State, u: Control,
              dynamics: BicycleModel, manifold: Manifold,
              target_speed: float, dt: float = 0.01) -> float:
        """Finite-difference approximation of dV/dt along ẋ = f(x, u)."""
        v0 = self.V_full(state, manifold, target_speed)
        s1 = dynamics.step(state, u, dt)
        v1 = self.V_full(s1, manifold, target_speed)
        return (v1 - v0) / dt


# ---------------------------------------------------------------------------
# Monitor
# ---------------------------------------------------------------------------

@dataclass
class StabilityMonitor:
    """Observability wrapper around a :class:`LyapunovFn`.

    Returns structured traces so the planner can emit Prometheus-style
    metrics (see PR-2.1-02).
    """
    fn: QuadraticLyapunov
    dynamics: BicycleModel
    manifold: Manifold
    target_speed: float = 15.0

    def check(self, state: State, u: Control,
              dt: float = 0.01, tol: float = 1e-6) -> Tuple[bool, float]:
        """Return ``(is_stable, dV_dt)``.

        ``is_stable`` is ``True`` whenever ``dV/dt ≤ tol`` — i.e. the
        Lyapunov function is non-increasing up to a small numerical
        tolerance.
        """
        dv = self.fn.dV_dt(state, u, self.dynamics, self.manifold,
                           self.target_speed, dt)
        return (dv <= tol), float(dv)

    # ------------------------------------------------------------------
    def metrics(self, state: State, u: Control,
                dt: float = 0.01) -> dict:
        v = self.fn.V_full(state, self.manifold, self.target_speed)
        stable, dv = self.check(state, u, dt)
        return {
            "V": float(v),
            "dV_dt": dv,
            "stable": bool(stable),
            "min_dist": float(self.manifold.min_distance(state)),
        }
