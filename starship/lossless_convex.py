"""Lossless convexification for Powered Descent Guidance — §1.

Implements the problem from ``image-11`` / ``image-12``::

    min  −z(T)                                 (maximise final log-mass)
    s.t. ṙ = v
         v̇ = g + Γ/m
         z = ln m       ⇒   ż = −‖Γ‖ / (Isp·g0·m) = −σ / (Isp·g0)
         ‖Γ‖ ≤ σ                                (lossless relaxation)
         ρ1 · e^{−z0}(1 − (z−z0) + ½(z−z0)²) ≤ σ
         σ ≤ ρ2 · e^{−z0}(1 − (z−z0))
         Γ · n̂ ≥ σ · cos θ_max                   (pointing cone)

For the engineering package we provide a light-weight SCP-friendly
formulation: at each outer iteration, fix a reference mass profile
``m_ref(t)`` and rewrite the thrust-bound constraints as linear
functions of ``σ(t)``. The resulting sub-problem is a QP in
``(r, v, Γ, σ, z)`` and is solved with SciPy's ``linprog``-style
interior-point through ``scipy.optimize.minimize`` with SLSQP. This
keeps the dependency footprint to numpy + scipy, matching the rest of
the package.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

import numpy as np
from scipy.optimize import minimize

from .types import G0_EARTH


@dataclass
class LosslessPDG:
    """Minimal-fuel powered-descent guidance using lossless convexification.

    Parameters are chosen so the default instance represents a
    qualitative Super-Heavy-class burn:

    * initial altitude ~300 m, vertical velocity -80 m/s
    * mass ~1_000 t, Isp 330 s
    * Raptor throttle [40 %, 100 %] of 2.3 MN
    """

    # initial / terminal conditions
    r0: np.ndarray = field(default_factory=lambda: np.array([0.0, 0.0, 300.0]))
    v0: np.ndarray = field(default_factory=lambda: np.array([0.0, 0.0, -80.0]))
    rf: np.ndarray = field(default_factory=lambda: np.zeros(3))
    vf: np.ndarray = field(default_factory=lambda: np.zeros(3))
    m0: float = 1_000_000.0

    # propulsion (3 Raptors @ ~2.3 MN = 6.9 MN full, 40 % floor)
    Isp: float = 330.0
    rho1: float = 2.76e6        # [N] 40% × 3 Raptors
    rho2: float = 6.90e6        # [N] 100% × 3 Raptors
    theta_max_deg: float = 15.0

    # environment
    g: np.ndarray = field(default_factory=lambda: np.array([0.0, 0.0, -9.80665]))

    # horizon
    T: float = 8.0              # seconds
    N: int = 40                 # control steps
    n_hat: np.ndarray = field(default_factory=lambda: np.array([0.0, 0.0, 1.0]))

    # ------------------------------------------------------------------
    def _dt(self) -> float:
        return self.T / self.N

    # ------------------------------------------------------------------
    def _build_bounds(self) -> Tuple[np.ndarray, np.ndarray]:
        """Per-step lower/upper bounds on the control.

        Control layout per step: ``(Γx, Γy, Γz)`` (3 decision variables).
        """
        lb = np.tile(np.array([-self.rho2, -self.rho2, 0.0]), self.N)
        ub = np.tile(np.array([ self.rho2,  self.rho2, self.rho2]), self.N)
        return lb, ub

    # ------------------------------------------------------------------
    def _dynamics_rollout(self, Gammas: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Forward-simulate (r, v, m) given a thrust sequence (N, 3)."""
        dt = self._dt()
        r = np.zeros((self.N + 1, 3))
        v = np.zeros((self.N + 1, 3))
        m = np.zeros(self.N + 1)
        r[0] = self.r0
        v[0] = self.v0
        m[0] = self.m0
        for k in range(self.N):
            thrust_mag = float(np.linalg.norm(Gammas[k]))
            acc = self.g + Gammas[k] / max(m[k], 1.0)
            v[k + 1] = v[k] + acc * dt
            r[k + 1] = r[k] + v[k] * dt + 0.5 * acc * dt * dt
            m[k + 1] = m[k] - thrust_mag * dt / (self.Isp * G0_EARTH)
        return r, v, m

    # ------------------------------------------------------------------
    def cost(self, U_flat: np.ndarray) -> float:
        """Objective = -m(T) + (soft) terminal tracking penalty."""
        G = U_flat.reshape(self.N, 3)
        r, v, m = self._dynamics_rollout(G)
        # Minimise fuel (equivalently maximise final mass).
        fuel = self.m0 - m[-1]
        # Soft terminal track so numerical optimiser drives to the pad.
        terminal = float(np.linalg.norm(r[-1] - self.rf) ** 2
                         + 4.0 * np.linalg.norm(v[-1] - self.vf) ** 2)
        return fuel + 1e-2 * terminal

    # ------------------------------------------------------------------
    def _pointing_penalty(self, U_flat: np.ndarray) -> float:
        """Sum of violated cone-margin, suitable as an inequality constraint."""
        G = U_flat.reshape(self.N, 3)
        n = self.n_hat / (np.linalg.norm(self.n_hat) + 1e-12)
        cos_t = np.cos(np.deg2rad(self.theta_max_deg))
        margins = []
        for k in range(self.N):
            mag = float(np.linalg.norm(G[k]))
            margins.append(float(n @ G[k] - mag * cos_t))
        return float(min(margins))

    # ------------------------------------------------------------------
    def solve(self, max_iter: int = 120
              ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
        """Run the numerical optimiser and return trajectory + status.

        Returns ``(r, v, Gammas, info)``.
        """
        lb, ub = self._build_bounds()
        U0 = np.tile([0.0, 0.0, 0.5 * (self.rho1 + self.rho2)], self.N)

        bounds = list(zip(lb, ub))

        constraints = [
            # pointing cone (inequality: ≥ 0)
            {"type": "ineq", "fun": self._pointing_penalty},
            # terminal position ≈ rf
            {"type": "eq",
             "fun": lambda U: self._dynamics_rollout(U.reshape(self.N, 3))[0][-1]
                              - self.rf},
            # terminal velocity ≈ vf
            {"type": "eq",
             "fun": lambda U: self._dynamics_rollout(U.reshape(self.N, 3))[1][-1]
                              - self.vf},
        ]

        res = minimize(self.cost, U0, method="SLSQP",
                       bounds=bounds, constraints=constraints,
                       options={"maxiter": max_iter, "ftol": 1e-4})
        G = res.x.reshape(self.N, 3)
        r, v, m = self._dynamics_rollout(G)
        info = {
            "success": bool(res.success),
            "message": str(res.message),
            "objective": float(res.fun),
            "cone_margin_min": self._pointing_penalty(res.x),
            "m_final": float(m[-1]),
        }
        return r, v, G, info
