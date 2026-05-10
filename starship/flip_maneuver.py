"""Belly-flop → Landing-flip manoeuvre — §7.

Equations from ``image-5`` / ``image-6`` / ``image-7``::

    τ_net = Σ_i (l_i × T_i) + τ_RCS
    I · α = τ_net − ω × J ω                   (Euler, §3)

A full flip inverts the booster's pitch angle from ~90° (belly-down, in
aerodynamic descent) to ~0° (engine-down, ready to land) within a
handful of seconds. The planner produces a bang-bang reference
quaternion / angular velocity for the MPC to track.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

import numpy as np

from .quaternion import Quaternion, integrate_quaternion
from .types import Thruster, ThrusterBank


# ---------------------------------------------------------------------------
# Belly-flop reference
# ---------------------------------------------------------------------------

def bellyflop_reference(altitude: float,
                        flip_start_alt: float = 500.0,
                        flip_end_alt: float = 150.0
                        ) -> np.ndarray:
    """Return a reference quaternion for the current altitude.

    Above ``flip_start_alt`` the booster is still in aerodynamic belly
    flop (pitch ≈ 90° about the body x-axis). Between start and end the
    pitch linearly interpolates to 0° (vertical). Below ``flip_end_alt``
    the reference is a vertical tail-down attitude.
    """
    if altitude >= flip_start_alt:
        return Quaternion.from_axis_angle([1.0, 0.0, 0.0], np.pi / 2).as_array()
    if altitude <= flip_end_alt:
        return Quaternion.identity().as_array()
    # Linear blend in angle
    denom = max(flip_start_alt - flip_end_alt, 1e-6)
    frac = (altitude - flip_end_alt) / denom
    angle = frac * (np.pi / 2)
    return Quaternion.from_axis_angle([1.0, 0.0, 0.0], angle).as_array()


# ---------------------------------------------------------------------------
# Torque synthesis
# ---------------------------------------------------------------------------

def net_torque(bank: ThrusterBank, thrusts: np.ndarray,
               rcs_torque: np.ndarray = None) -> np.ndarray:
    """Return the net body-frame torque produced by thrusters + RCS.

    ``thrusts`` has shape ``(N,)``; each scalar is multiplied by the
    corresponding thruster's ``direction`` vector.
    """
    if rcs_torque is None:
        rcs_torque = np.zeros(3)
    tau = np.asarray(rcs_torque, dtype=float).reshape(3).copy()
    for th, mag in zip(bank.thrusters, thrusts):
        direction = th.direction / (np.linalg.norm(th.direction) + 1e-12)
        force = mag * direction
        tau += np.cross(th.position, force)
    return tau


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------

@dataclass
class FlipPlanner:
    """Plan a minimum-time bang-bang flip using Euler's equation α = τ/I."""

    I_xx: float = 1.0e8
    tau_max: float = 6.0e7        # [N·m]
    theta_start: float = np.pi / 2
    theta_end: float = 0.0

    def plan(self, dt: float = 0.1, max_T: float = 10.0
             ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return time, θ_ref(t), ω_ref(t) for a bang-bang flip.

        The booster first accelerates with +τ_max, then decelerates with
        −τ_max so that the final angular velocity is zero at θ_end.
        """
        dtheta = self.theta_start - self.theta_end
        # For bang-bang with zero-end-velocity : Δθ = τ·T²/(4I)
        T = 2.0 * np.sqrt(abs(dtheta) * self.I_xx / self.tau_max)
        T = min(T, max_T)
        N = int(np.ceil(T / dt))
        t = np.linspace(0.0, T, N + 1)
        theta = np.zeros_like(t)
        omega = np.zeros_like(t)
        mid = T / 2.0
        alpha_mag = self.tau_max / self.I_xx
        direction = -1.0 if dtheta > 0 else 1.0
        for i, tk in enumerate(t):
            if tk < mid:
                omega[i] = direction * alpha_mag * tk
                theta[i] = self.theta_start + 0.5 * direction * alpha_mag * tk * tk
            else:
                s = tk - mid
                omega[i] = direction * alpha_mag * (mid - s)
                theta[i] = self.theta_start + \
                    0.5 * direction * alpha_mag * mid * mid + \
                    direction * alpha_mag * mid * s - \
                    0.5 * direction * alpha_mag * s * s
        return t, theta, omega
