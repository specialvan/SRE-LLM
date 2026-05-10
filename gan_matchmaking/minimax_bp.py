"""§9 Minimax BP (Ban/Pick) game — Nash equilibrium of a two-player zero-sum game.

Article formula (image-8.png):

    min_{y in Y} max_{x in X} U(x, y) = max_{x in X} min_{y in Y} U(x, y)

We implement:

- ``zero_sum_nash(U)``: solve the row player's equilibrium of a zero-sum game
  with payoff matrix ``U`` using linear programming (scipy.optimize.linprog).
- ``BPSession``: a minimalist Ban / Pick state machine that repeatedly asks
  ``zero_sum_nash`` for a mixed strategy on the remaining pool.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

import numpy as np
from scipy.optimize import linprog


def zero_sum_nash(U: np.ndarray) -> Tuple[np.ndarray, np.ndarray, float]:
    """Return ``(x*, y*, v)`` for payoff matrix ``U`` (row player is maximiser).

    Formulation (row player's LP):

        max v
        s.t.  U^T x >= v * 1
              1^T x = 1, x >= 0

    Equivalent LP in standard form with variables ``[x (m,), v]``:

        min  -v
        s.t. [-U^T, 1_m] · [x; v]  <= 0        (U^T x >= v)
              1^T x = 1, x >= 0, v free
    """
    U = np.asarray(U, dtype=float)
    m, n = U.shape

    # Shift so all payoffs > 0 (standard trick that doesn't change Nash).
    shift = 1.0 - U.min() if U.min() <= 0 else 0.0
    Us = U + shift

    # Row player LP: maximise v, subject to sum_i x_i * Us[i, j] >= v for all j.
    # Variables: [x_1..x_m, v]. Length = m+1.
    c = np.zeros(m + 1)
    c[-1] = -1.0  # minimise -v.

    # Inequality: -Us^T x + v <= 0  →  A_ub = [-Us^T, 1], b_ub = 0.
    A_ub = np.hstack([-Us.T, np.ones((n, 1))])
    b_ub = np.zeros(n)

    # Equality: sum_i x_i = 1.
    A_eq = np.zeros((1, m + 1))
    A_eq[0, :m] = 1.0
    b_eq = np.array([1.0])

    bounds = [(0.0, None)] * m + [(None, None)]  # v free.
    res = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq,
                  bounds=bounds, method="highs")
    if not res.success:
        raise RuntimeError(f"LP failed: {res.message}")
    x = np.clip(res.x[:m], 0.0, None)
    if x.sum() > 0:
        x /= x.sum()
    v = -res.fun - shift  # undo shift.

    # Column player LP: minimise v', subject to Us x <= v' for each row. Dual view.
    c2 = np.zeros(n + 1)
    c2[-1] = 1.0
    A_ub2 = np.hstack([Us, -np.ones((m, 1))])
    b_ub2 = np.zeros(m)
    A_eq2 = np.zeros((1, n + 1))
    A_eq2[0, :n] = 1.0
    b_eq2 = np.array([1.0])
    bounds2 = [(0.0, None)] * n + [(None, None)]
    res2 = linprog(c2, A_ub=A_ub2, b_ub=b_ub2, A_eq=A_eq2, b_eq=b_eq2,
                   bounds=bounds2, method="highs")
    if not res2.success:
        raise RuntimeError(f"LP failed (col): {res2.message}")
    y = np.clip(res2.x[:n], 0.0, None)
    if y.sum() > 0:
        y /= y.sum()
    return x, y, v


@dataclass
class BPSession:
    """A tiny BP state machine for the Ban/Pick phase of a team game."""
    payoff_fn: "callable[[int, int], float]"  # type: ignore[assignment]
    pool: List[str] = field(default_factory=list)
    history: List[Tuple[str, int, int]] = field(default_factory=list)
    # history entries: (phase, row_pick_idx, col_pick_idx)

    def _payoff_matrix(self) -> np.ndarray:
        n = len(self.pool)
        U = np.zeros((n, n))
        for i in range(n):
            for j in range(n):
                U[i, j] = self.payoff_fn(i, j)
        return U

    def nash_step(self, phase: str = "pick") -> Tuple[np.ndarray, np.ndarray, float]:
        """Compute a mixed-strategy equilibrium on the remaining pool."""
        if len(self.pool) == 0:
            raise RuntimeError("pool is empty")
        U = self._payoff_matrix()
        x, y, v = zero_sum_nash(U)
        return x, y, v

    def apply_choice(self, phase: str, row_idx: int, col_idx: int) -> None:
        """Consume two items from the pool (indices into current pool)."""
        self.history.append((phase, row_idx, col_idx))
        # Remove from right to left to keep indices valid.
        for idx in sorted({row_idx, col_idx}, reverse=True):
            if 0 <= idx < len(self.pool):
                self.pool.pop(idx)
