"""6-DoF rigid-body dynamics on SO(3) — §3.

Implements the equations from `image-15` / `image-16`::

    ṙ = v
    v̇ = g + (1/m) · R(q) · F_body
    q̇ = ½ · Ω(ω) · q
    ω̇ = J⁻¹ · (τ − ω × J ω)
    ṁ = −‖F_body‖ / (Isp · g0)    (optional mass depletion)

Integration uses RK4 with an explicit quaternion re-normalisation step.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple

import numpy as np

from .quaternion import Quaternion, integrate_quaternion, omega_matrix
from .types import (DEFAULT_STARSHIP, G0_EARTH, GRAVITY_EARTH,
                     State6DOF, VehicleParams)


@dataclass
class RigidBody:
    """Six-degree-of-freedom rigid body with an optional mass model."""
    params: VehicleParams = field(default_factory=lambda: DEFAULT_STARSHIP)
    gravity: np.ndarray = field(default_factory=lambda: GRAVITY_EARTH.copy())
    deplete_mass: bool = False

    # ------------------------------------------------------------------
    def f(self, state: State6DOF,
          force_body: np.ndarray, torque_body: np.ndarray) -> np.ndarray:
        """Return dstate/dt as a 14-vector.

        Layout matches :meth:`State6DOF.to_vec`.
        """
        force_body = np.asarray(force_body, dtype=float).reshape(3)
        torque_body = np.asarray(torque_body, dtype=float).reshape(3)

        q = state.q / (np.linalg.norm(state.q) + 1e-12)
        R = Quaternion.from_array(q).to_matrix()

        # Linear dynamics in inertial frame
        rdot = state.v
        vdot = self.gravity + (1.0 / max(state.m, 1.0)) * (R @ force_body)

        # Attitude kinematics
        qdot = 0.5 * omega_matrix(state.w) @ q

        # Rotational dynamics (Euler's equation)
        J = self.params.inertia
        omega = state.w
        wdot = np.linalg.solve(J, torque_body - np.cross(omega, J @ omega))

        mdot = -float(np.linalg.norm(force_body)) / (self.params.Isp * G0_EARTH) \
            if self.deplete_mass else 0.0

        return np.concatenate([rdot, vdot, qdot, wdot, np.array([mdot])])

    # ------------------------------------------------------------------
    def step(self, state: State6DOF,
             force_body: np.ndarray, torque_body: np.ndarray,
             dt: float) -> State6DOF:
        """RK4 with quaternion-preserving attitude step."""
        x0 = state.to_vec()

        def _f(xv: np.ndarray) -> np.ndarray:
            return self.f(State6DOF.from_vec(xv), force_body, torque_body)

        k1 = _f(x0)
        k2 = _f(x0 + 0.5 * dt * k1)
        k3 = _f(x0 + 0.5 * dt * k2)
        k4 = _f(x0 + dt * k3)
        x1 = x0 + dt * (k1 + 2 * k2 + 2 * k3 + k4) / 6.0

        # Use exponential quaternion integration for the attitude slot to
        # avoid monotone drift off the unit sphere.
        q_new = integrate_quaternion(state.q, state.w, dt)
        x1[6:10] = q_new

        if not self.deplete_mass:
            x1[13] = state.m

        return State6DOF.from_vec(x1)

    # ------------------------------------------------------------------
    def rollout(self, state0: State6DOF,
                forces: np.ndarray, torques: np.ndarray,
                dt: float) -> Tuple[np.ndarray, ...]:
        """Roll out the dynamics for sequences of forces/torques.

        Returns a tuple of state arrays (r, v, q, w, m) each with leading
        time axis.
        """
        N = len(forces)
        rs = np.zeros((N + 1, 3))
        vs = np.zeros((N + 1, 3))
        qs = np.zeros((N + 1, 4))
        ws = np.zeros((N + 1, 3))
        ms = np.zeros((N + 1,))
        rs[0], vs[0], qs[0], ws[0], ms[0] = (state0.r, state0.v,
                                              state0.q, state0.w, state0.m)
        s = state0
        for k in range(N):
            s = self.step(s, forces[k], torques[k], dt)
            rs[k + 1], vs[k + 1] = s.r, s.v
            qs[k + 1], ws[k + 1] = s.q, s.w
            ms[k + 1] = s.m
        return rs, vs, qs, ws, ms
