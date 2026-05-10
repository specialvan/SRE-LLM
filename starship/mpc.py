"""Linear quadratic MPC with receding horizon — §6.

Implements the cost and constraint structure from ``image-3`` / ``image-4``::

    min  J = Σ_{k=0}^{N-1} (x_kᵀ Q x_k + u_kᵀ R u_k) + x_NᵀP x_N
    s.t. x_{k+1} = A_d x_k + B_d u_k
         u_min ≤ u_k ≤ u_max
         x_0 = x_now                         (given)

The horizon is folded into a dense QP ``min ½ Uᵀ H U + g^T U`` with
``U = [u_0, …, u_{N-1}]``. The resulting QP is solved with SciPy's
``quadprog``-compatible ``minimize(method="SLSQP")`` if no fast QP solver
is available. If ``scipy.optimize.nnls``-style bounds are enough we fall
back to a clipped projected-gradient solver, which is plenty fast for
demo-scale systems.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

import numpy as np
from scipy.linalg import expm, solve
from scipy.optimize import minimize


# ---------------------------------------------------------------------------
# Continuous → discrete
# ---------------------------------------------------------------------------

@dataclass
class LinearDiscretizer:
    """Zero-order-hold discretisation of (A, B)."""
    A: np.ndarray
    B: np.ndarray

    def zoh(self, dt: float) -> Tuple[np.ndarray, np.ndarray]:
        n = self.A.shape[0]
        m = self.B.shape[1]
        big = np.zeros((n + m, n + m))
        big[:n, :n] = self.A
        big[:n, n:] = self.B
        M = expm(big * dt)
        Ad = M[:n, :n]
        Bd = M[:n, n:]
        return Ad, Bd


# ---------------------------------------------------------------------------
# Quadratic MPC
# ---------------------------------------------------------------------------

@dataclass
class QuadraticMPC:
    """Dense-form QP MPC for linear systems.

    Stores cost matrices ``Q, R, P``, discrete dynamics ``(A_d, B_d)``,
    bounds ``u_min, u_max`` and horizon ``N``.
    """
    A: np.ndarray
    B: np.ndarray
    Q: np.ndarray
    R: np.ndarray
    P: np.ndarray
    N: int = 20
    u_min: Optional[np.ndarray] = None
    u_max: Optional[np.ndarray] = None

    # state tracked between calls
    _U_prev: Optional[np.ndarray] = field(default=None, init=False, repr=False)

    # ------------------------------------------------------------------
    def _prediction_matrices(self) -> Tuple[np.ndarray, np.ndarray]:
        """Build stacked matrices so that X = F x0 + G U.

        ``X`` stacks x_1 .. x_N, ``U`` stacks u_0 .. u_{N-1}.
        """
        n = self.A.shape[0]
        m = self.B.shape[1]
        N = self.N
        F = np.zeros((N * n, n))
        G = np.zeros((N * n, N * m))
        An = np.eye(n)
        for i in range(N):
            An = self.A @ An
            F[i * n:(i + 1) * n, :] = An
            for j in range(i + 1):
                Apow = np.linalg.matrix_power(self.A, i - j)
                G[i * n:(i + 1) * n, j * m:(j + 1) * m] = Apow @ self.B
        return F, G

    # ------------------------------------------------------------------
    def _cost_matrices(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Return (H, f0, F, G) such that J = ½ Uᵀ H U + (f0 x0)ᵀ U + const.

        The returned ``f0`` has shape ``(n_u*N, n_x)`` so the gradient at
        a given ``x0`` is ``f0 @ x0``.
        """
        F, G = self._prediction_matrices()
        N = self.N
        n = self.A.shape[0]
        m = self.B.shape[1]

        # block-diag Q (size N-1 times) + P for terminal
        Qbar = np.zeros((N * n, N * n))
        for i in range(N - 1):
            Qbar[i * n:(i + 1) * n, i * n:(i + 1) * n] = self.Q
        Qbar[(N - 1) * n:, (N - 1) * n:] = self.P
        Rbar = np.zeros((N * m, N * m))
        for i in range(N):
            Rbar[i * m:(i + 1) * m, i * m:(i + 1) * m] = self.R

        H = 2 * (G.T @ Qbar @ G + Rbar)
        f0 = 2 * (G.T @ Qbar @ F)                 # gradient = f0 @ x0
        H = 0.5 * (H + H.T)                        # symmetrise
        return H, f0, F, G

    # ------------------------------------------------------------------
    def solve(self, x0: np.ndarray,
              warm_start: Optional[np.ndarray] = None,
              max_iter: int = 200,
              tol: float = 1e-8) -> np.ndarray:
        """Solve the dense box-constrained QP and return ``U`` of length ``N·m``.

        Uses ``scipy.optimize.minimize(method='L-BFGS-B')`` which natively
        supports element-wise bounds and is very fast on quadratic
        objectives with analytical gradient.
        """
        H, f0, _, _ = self._cost_matrices()
        m = self.B.shape[1]
        N = self.N

        g = f0 @ np.asarray(x0, dtype=float)
        U0 = warm_start.copy() if warm_start is not None else np.zeros(N * m)

        umin = np.tile(self.u_min if self.u_min is not None
                        else -np.inf * np.ones(m), N)
        umax = np.tile(self.u_max if self.u_max is not None
                        else np.inf * np.ones(m), N)
        bounds = list(zip(umin, umax))

        def _fun(U: np.ndarray) -> float:
            return float(0.5 * U @ H @ U + g @ U)

        def _jac(U: np.ndarray) -> np.ndarray:
            return H @ U + g

        res = minimize(_fun, U0, jac=_jac, method="L-BFGS-B",
                        bounds=bounds,
                        options={"maxiter": max_iter, "ftol": tol,
                                 "gtol": tol})
        U = res.x
        self._U_prev = U.copy()
        return U

    # ------------------------------------------------------------------
    def step(self, x0: np.ndarray) -> np.ndarray:
        """One MPC step: solve, apply u_0, shift warm start."""
        warm = None
        if self._U_prev is not None:
            m = self.B.shape[1]
            warm = np.concatenate([self._U_prev[m:],
                                    self._U_prev[-m:]])
        U = self.solve(x0, warm_start=warm)
        return U[:self.B.shape[1]]
