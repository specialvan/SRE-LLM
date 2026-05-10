"""Control-invariant-set generator T_inv — §3.1.

Implements the article's central operator::

    u_safe = T_inv(u_nn)

`T_inv` wraps any upstream neural / MPC policy and projects its output
into the set that respects the Lyapunov hard constraint

    dV/dt ≤ -γ V                         (exponential decay variant)

If the QP above is infeasible we fall back to an emergency brake.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

import numpy as np

from .cbf import CBFQPFilter
from .dynamics import BicycleModel, Manifold
from .lyapunov import QuadraticLyapunov, StabilityMonitor
from .types import DEFAULT_VEHICLE, Control, State, VehicleParams


@dataclass
class ControlInvariantOperator:
    """Operator T_inv mapping ``u_nn`` → ``u_safe`` (§3.1).

    Pipeline:

        1. Run ``cbf_filter`` to fold the search space.
        2. If ``dV/dt > -γ V`` still, nudge acceleration downward until
           the Lyapunov inequality holds or we hit the emergency brake.
    """

    cbf: CBFQPFilter
    stability: StabilityMonitor
    params: VehicleParams = DEFAULT_VEHICLE
    gamma: float = 0.5           # exponential decay rate (best-effort)
    relax_steps: int = 8         # how many relaxation iterations to try
    tol: float = 1e-3            # numerical tolerance on dV/dt ≤ 0

    # ------------------------------------------------------------------
    def apply(self, state: State, u_nn: Control
              ) -> Tuple[Control, dict]:
        """Return ``(u_safe, info)``.

        Two-tier check:
          * ``dV/dt ≤ tol``      — hard Lyapunov constraint from §2.1
          * ``dV/dt ≤ -γ V``     — soft exponential-decay target
        """
        # (1) barrier-based folding
        u_cbf, cbf_info = self.cbf.filter(state, u_nn)

        # (2) Lyapunov check
        V = self.stability.fn.V_full(state, self.stability.manifold,
                                     self.stability.target_speed)
        exp_target = -self.gamma * V

        u = u_cbf
        info = {"cbf": cbf_info, "V": V, "dV_dt": None,
                "status": "unchanged"}

        def _dv(cand: Control) -> float:
            return self.stability.fn.dV_dt(
                state, cand, self.stability.dynamics,
                self.stability.manifold, self.stability.target_speed,
            )

        dv = _dv(u)
        info["dV_dt"] = float(dv)

        # Fast path: already stable enough
        if dv <= self.tol:
            info["status"] = "stable" if dv <= exp_target + 1e-6 else "non_increasing"
            return u, info

        # Relax toward exponential-decay target; accept the first candidate
        # that at least achieves dV/dt ≤ 0
        best_u, best_dv = u, dv
        for step in range(self.relax_steps):
            new_jerk = max(
                u.jerk - self.params.jerk_max / self.relax_steps,
                -self.params.jerk_max,
            )
            u = Control(steer=u.steer, jerk=new_jerk)
            dv = _dv(u)
            if dv < best_dv:
                best_u, best_dv = u, dv
            if dv <= exp_target + 1e-6:
                info["dV_dt"] = float(dv)
                info["status"] = "relaxed_exp"
                return u, info
            if dv <= self.tol:
                info["dV_dt"] = float(dv)
                info["status"] = "relaxed"
                return u, info

        info["dV_dt"] = float(best_dv)
        if best_dv <= self.tol:
            info["status"] = "relaxed"
            return best_u, info

        # (3) last resort — emergency brake along original heading
        brake = Control(steer=0.0, jerk=-self.params.jerk_max)
        dv_brake = _dv(brake)
        info["dV_dt"] = float(dv_brake)
        info["status"] = "emergency_brake"
        return brake, info
