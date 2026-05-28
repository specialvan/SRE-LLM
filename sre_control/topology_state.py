"""§3 Rigid-body adapter — service topology as a manifold state.

SRE problem
-----------
A live service isn't just scalar metrics; it's a *structured* state —
version rollout progress, consistent-hash ring position, leader
rotation angle in a Raft cluster, routing-table delta vs a reference.
Stuffing these into ℝ^n and doing EMAs causes silent artefacts:

* Angular / cyclic quantities wrap (a 359° shift looks like −1°, not
  +359°).
* Version rollout has an oriented direction; "halfway rolled out" isn't
  a simple average of two versions.

The same math that keeps 6-DoF attitude drift bounded on the Starship
booster — unit quaternions on SO(3) + exponential-map updates —
applies here:

    topology state    ~ (position ∈ ℝ^n, rotation ∈ SO(3))
    rotation update   ~ q_{k+1} = exp(½·ω·dt) ⊗ q_k
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from starship.quaternion import Quaternion, integrate_quaternion

from .exceptions import AdapterInputError
from .events import make_event


@dataclass
class TopologyState:
    """Thin wrapper that exposes a quaternion as a "topology rotation".

    Typical usage:

    * ``position`` — continuous resource state (CPU %, QPS, latency)
    * ``q`` — unit quaternion encoding an angular topology (ring
       position on a consistent-hash circle, Raft term direction,
       blue/green split angle, etc.)
    * ``omega`` — angular velocity of the topology in rad/s

    The ``step`` method advances the state using the same
    ``integrate_quaternion`` call from the booster stack, guaranteeing
    unit-norm invariance (no drift into invalid topologies).
    """

    position: np.ndarray = field(default_factory=lambda: np.zeros(3))
    q: np.ndarray = field(default_factory=lambda: np.array([1, 0, 0, 0.0]))
    omega: np.ndarray = field(default_factory=lambda: np.zeros(3))

    # ------------------------------------------------------------------
    def step(self, velocity: Sequence[float],
             angular_velocity: Sequence[float], dt: float) -> dict:
        """Advance (position, q) by one dt using the quaternion exp-map."""
        if isinstance(dt, bool):
            raise AdapterInputError('dt must be positive and finite')
        dt = float(dt)
        if not np.isfinite(dt) or dt <= 0.0:
            raise AdapterInputError('dt must be positive and finite')
        velocity_arr = np.asarray(velocity, dtype=float)
        if not np.isfinite(velocity_arr).all():
            raise AdapterInputError('non-finite topology velocity')
        angular_velocity_arr = np.asarray(angular_velocity, dtype=float)
        if not np.isfinite(angular_velocity_arr).all():
            raise AdapterInputError('non-finite angular velocity')

        events = []
        local_states = []

        q = np.asarray(self.q, dtype=float)
        q_norm = float(np.linalg.norm(q))
        if not np.isfinite(q_norm) or q_norm < 1e-12:
            self.q = np.array([1.0, 0.0, 0.0, 0.0])
            local_states.append("repair_unit_norm")
            events.append(make_event(
                stage="TopologyState",
                kind="topology_state_repaired",
                detail=(
                    f"input quaternion norm {q_norm:.3e} was invalid "
                    "before integration"
                ),
                safe_action=(
                    "reset the topology quaternion to identity before "
                    "applying the exp-map"
                ),
                input_norm_valid=False,
                quaternion_norm=q_norm if np.isfinite(q_norm) else None,
                repair_action="reset_identity",
            ))
        elif abs(q_norm - 1.0) > 1e-6:
            self.q = q / q_norm
            local_states.append("repair_unit_norm")
            events.append(make_event(
                stage="TopologyState",
                kind="topology_state_repaired",
                detail=(
                    f"input quaternion norm {q_norm:.3e} was normalized "
                    "before integration"
                ),
                safe_action=(
                    "renormalize the topology quaternion before applying "
                    "the exp-map"
                ),
                input_norm_valid=True,
                quaternion_norm=q_norm,
                repair_action="renormalize",
            ))
        else:
            self.q = q

        self.position = self.position + velocity_arr * dt
        self.omega = angular_velocity_arr
        self.q = integrate_quaternion(self.q, self.omega, dt)
        local_states.append("integrate")
        return {
            "q_norm": float(np.linalg.norm(self.q)),
            "local_states": local_states,
            "events": events,
        }

    # ------------------------------------------------------------------
    @property
    def ring_angle_rad(self) -> float:
        """Return the rotation angle about the z-axis.

        Useful for consistent-hash ring interpretation: the angle in
        [-π, π] represents the current shift position on the ring.
        """
        # Rotation angle extracted from the quaternion (any axis).
        w = float(np.clip(self.q[0], -1.0, 1.0))
        # 2 · acos(w) gives the overall rotation magnitude.
        angle = float(2.0 * np.arccos(w)) * (1 if self.q[3] >= 0 else -1)
        return float((angle + np.pi) % (2.0 * np.pi) - np.pi)

    # ------------------------------------------------------------------
    def axis(self) -> np.ndarray:
        """Return the body z-axis in world frame (handy for visualisation)."""
        return Quaternion.from_array(self.q).to_matrix() @ np.array([0, 0, 1.0])

    # ------------------------------------------------------------------
    def distance_to(self, other: "TopologyState") -> float:
        """Geodesic distance between two topology states.

        Position term is Euclidean, rotation term is the SO(3) angular
        distance (this is what you'd minimise when choosing the
        "smallest" ring shift, not an arithmetic difference in degrees).
        """
        dr = float(np.linalg.norm(self.position - other.position))
        dq = abs(float(self.q @ other.q))                 # in [-1, 1]
        dtheta = float(np.arccos(np.clip(2 * dq * dq - 1, -1.0, 1.0)))
        return dr + dtheta
