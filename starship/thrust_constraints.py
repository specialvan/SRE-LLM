"""Thrust pointing and magnitude constraints — §4.

Equations from ``image-17`` / ``image-18``::

    ‖u‖ ≤ T_max                   (thrust magnitude)
    n̂ᵀ u ≥ ‖u‖ · cos θ_max        (pointing cone)

For downstream use we provide
  * a callable ``pointing_cone_constraint`` returning ≥0 when the cone is
    respected (suitable as a scipy.optimize inequality),
  * a closed-form :class:`ConeQPFilter` which projects an arbitrary
    ``u_nom`` onto the feasible set (cone ∩ ball).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence, Tuple

import numpy as np


# ---------------------------------------------------------------------------
# Constraint primitives
# ---------------------------------------------------------------------------

def magnitude_bound(u: Sequence[float], T_max: float) -> float:
    """Return ``T_max − ‖u‖`` (non-negative when feasible)."""
    return float(T_max - np.linalg.norm(u))


def pointing_cone_constraint(u: Sequence[float],
                             n_hat: Sequence[float],
                             theta_max: float) -> float:
    """Return ``n̂ᵀ u − ‖u‖ cos θ_max`` (≥ 0 when feasible).

    ``theta_max`` is in radians.
    """
    u = np.asarray(u, dtype=float)
    n_hat = np.asarray(n_hat, dtype=float)
    n_hat = n_hat / (np.linalg.norm(n_hat) + 1e-12)
    return float(n_hat @ u - np.linalg.norm(u) * np.cos(theta_max))


# ---------------------------------------------------------------------------
# Closed-form projection onto cone ∩ ball
# ---------------------------------------------------------------------------

@dataclass
class ConeQPFilter:
    """Safety filter matching §3.1 of DOC/自动驾驶.md but for thrust.

    Given a desired ``u_nom``, compute

        u⋆ = argmin ½ ‖u − u_nom‖²
             s.t.  ‖u‖ ≤ T_max
                   n̂ᵀ u ≥ ‖u‖ cos θ_max

    The combined set is convex (intersection of a ball and a rotated
    Lorentz cone through the origin) so the projection has a closed
    form: first handle the cone, then scale to the ball.
    """
    n_hat: np.ndarray
    theta_max: float = np.deg2rad(15.0)
    T_max: float = 2.3e6
    T_min: float = 0.0

    # ------------------------------------------------------------------
    def _cone_project(self, u: np.ndarray) -> np.ndarray:
        """Project a vector onto the pointing cone {u : u·n ≥ |u| cos θ}.

        Uses the closed form for the standard second-order cone after
        rewriting the problem in (t, x) coordinates where ``t = u·n``
        is the along-axis component and ``x`` is perpendicular.

        The pointing cone is equivalent to ``|x| ≤ t · tan θ``, i.e. an
        ice-cream cone with half-angle θ around the ``+n`` axis.
        """
        n = self.n_hat / (np.linalg.norm(self.n_hat) + 1e-12)
        t0 = float(n @ u)
        x0 = u - t0 * n
        xnorm = float(np.linalg.norm(x0))
        tan_t = float(np.tan(self.theta_max))

        # Case A: already inside the cone.
        if xnorm <= t0 * tan_t + 1e-12:
            return u

        # Case B: in the opposite (polar) cone — closest point is origin.
        # The polar of `|x| ≤ t·tan θ` is `t ≤ -|x|·tan(π/2 − θ)` i.e.
        # `t·tan θ ≤ −|x|`, equivalently `t ≤ −|x|/tan θ` (for tan θ > 0).
        if t0 * tan_t <= -xnorm - 1e-12:
            return np.zeros_like(u)

        # Case C: project onto the lateral surface |x| = t·tan θ.
        # Closed-form projection onto the cone `|x| ≤ α·t` with α=tan θ:
        #     t⋆ = (t0 + α · |x0|) / (1 + α²)
        #     x⋆ = α · t⋆ · x0 / |x0|
        alpha = tan_t
        t_star = (t0 + alpha * xnorm) / (1.0 + alpha * alpha)
        if t_star < 0:
            return np.zeros_like(u)
        x_star = (alpha * t_star) * (x0 / max(xnorm, 1e-12))
        return t_star * n + x_star

    # ------------------------------------------------------------------
    def filter(self, u_nom: Sequence[float]) -> np.ndarray:
        """Project ``u_nom`` onto the feasible cone ∩ ball set."""
        u = np.asarray(u_nom, dtype=float).reshape(3)
        u = self._cone_project(u)

        # Scale to ball [T_min, T_max] along its own direction.
        mag = float(np.linalg.norm(u))
        if mag < 1e-12:
            return np.zeros(3)
        if mag > self.T_max:
            u = u * (self.T_max / mag)
            mag = self.T_max
        if 0.0 < mag < self.T_min:
            u = u * (self.T_min / mag)
        return u

    # ------------------------------------------------------------------
    # convenient scalar margin, useful for the EKF/MPC traces
    def cone_margin(self, u: Sequence[float]) -> float:
        return pointing_cone_constraint(u, self.n_hat, self.theta_max)


# ---------------------------------------------------------------------------
# cone constraint assembler for a scipy QP
# ---------------------------------------------------------------------------

def cone_constraint_for_minimize(n_hat: np.ndarray, theta_max: float
                                 ) -> Callable[[np.ndarray], float]:
    """Return a callable ``g(u) ≥ 0`` consumable by ``scipy.optimize``."""
    n = n_hat / (np.linalg.norm(n_hat) + 1e-12)
    cos_t = float(np.cos(theta_max))

    def _g(u: np.ndarray) -> float:
        u = np.asarray(u, dtype=float)
        return float(n @ u - np.linalg.norm(u) * cos_t)

    return _g
