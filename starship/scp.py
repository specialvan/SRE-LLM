"""Successive Convex Programming — §2.

Linearise the nonlinear dynamics around a reference trajectory and solve
a trust-region-constrained convex sub-problem at every iteration::

    δẋ = A(t) δx + B(t) δu
    ‖δx‖_∞ ≤ η_x
    ‖δu‖_∞ ≤ η_u
    → repeat until ‖x^{k+1} − x^k‖ < ε

The iterate itself is driven by any convex sub-solver — we expose a
clean API (``linearize`` + ``SCP`` class) so the caller can plug in
CVXPY, OSQP or our ``QuadraticMPC``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

import numpy as np


# ---------------------------------------------------------------------------
# Numerical linearisation
# ---------------------------------------------------------------------------

def linearize(f: Callable[[np.ndarray, np.ndarray], np.ndarray],
              x_ref: np.ndarray, u_ref: np.ndarray,
              eps: float = 1e-5
              ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Finite-difference Jacobians A = ∂f/∂x, B = ∂f/∂u and residual c.

    ``f`` is a continuous-time dynamics callable, ``x_ref`` and ``u_ref``
    are the reference state/input. The returned ``c`` is the residual
    ``f(x_ref, u_ref) − A x_ref − B u_ref`` so the linear model reads
    ``f_lin(x, u) = A x + B u + c``.
    """
    x0 = np.asarray(x_ref, dtype=float)
    u0 = np.asarray(u_ref, dtype=float)
    n = x0.size
    m = u0.size
    f0 = np.asarray(f(x0, u0), dtype=float)

    A = np.zeros((n, n))
    for i in range(n):
        xp = x0.copy(); xp[i] += eps
        A[:, i] = (f(xp, u0) - f0) / eps

    B = np.zeros((n, m))
    for i in range(m):
        up = u0.copy(); up[i] += eps
        B[:, i] = (f(x0, up) - f0) / eps

    c = f0 - A @ x0 - B @ u0
    return A, B, c


# ---------------------------------------------------------------------------
# SCP loop
# ---------------------------------------------------------------------------

@dataclass
class SCP:
    """Trust-region SCP driver.

    ``sub_solver`` takes a *linear* model ``(A, B, c)`` and the previous
    reference trajectory, and returns the optimised ``(x_traj, u_traj)``.
    """
    f: Callable[[np.ndarray, np.ndarray], np.ndarray]
    sub_solver: Callable[[np.ndarray, np.ndarray, np.ndarray,
                          np.ndarray, np.ndarray, float, float],
                         Tuple[np.ndarray, np.ndarray]]
    eta_x: float = 10.0
    eta_u: float = 2.0
    eps: float = 1e-3
    max_iter: int = 8
    history: List[float] = field(default_factory=list, init=False)

    # ------------------------------------------------------------------
    def iterate(self, x_traj0: np.ndarray, u_traj0: np.ndarray
                ) -> Tuple[np.ndarray, np.ndarray, dict]:
        """Run SCP starting from the given reference trajectory.

        Shapes : ``x_traj0 (N+1, n)``, ``u_traj0 (N, m)``.
        Returns optimised ``(x_traj, u_traj)`` and a summary dict.
        """
        x_ref = x_traj0.copy()
        u_ref = u_traj0.copy()
        self.history = []

        for k in range(self.max_iter):
            # Linearise around the last time-step as a representative point.
            N = u_ref.shape[0]
            mid = N // 2
            A, B, c = linearize(self.f, x_ref[mid], u_ref[mid])

            x_new, u_new = self.sub_solver(
                x_ref, u_ref, A, B, c, self.eta_x, self.eta_u)
            diff = float(np.linalg.norm(x_new - x_ref))
            self.history.append(diff)
            x_ref, u_ref = x_new, u_new

            # Shrink trust region aggressively when converging.
            if diff < self.eps:
                break
            self.eta_x *= 0.85
            self.eta_u *= 0.85

        info = {
            "iters": len(self.history),
            "final_diff": self.history[-1] if self.history else 0.0,
            "converged": bool(self.history and self.history[-1] < self.eps),
            "history": list(self.history),
        }
        return x_ref, u_ref, info
