"""Chopstick-catch controller — §8.

The final leg of the recovery pipeline (``image``, ``image-8``,
``image-9``). The booster is below ~150 m AGL, roughly vertical and
descending at a few m/s. Three Raptors still fire on reduced throttle;
the tower arms close once the booster is inside a sub-metre window.

Key equations (from the article)::

    T_total(t) = Σ_i T_i · (1 + w_off,i(t)) + w_att · τ_demand
             ≈  A(geometry) · thrust_cmd                  # over-determined LS

This module ships:

* :class:`CatchGeometry`  — tower frame, arm-gap profile vs altitude
* :class:`ThrustAllocator` — bounded least-squares allocation to thrusters
* :class:`CatchController`— outer loop wiring attitude/position errors to
                           thrust demands
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

import numpy as np
from scipy.optimize import lsq_linear

from .types import State6DOF, Thruster, ThrusterBank


# ---------------------------------------------------------------------------
# Tower geometry
# ---------------------------------------------------------------------------

@dataclass
class CatchGeometry:
    """Tower / chopstick geometry and target capture window."""

    tower_position: np.ndarray = field(default_factory=lambda: np.zeros(3))
    catch_altitude: float = 80.0           # nominal arm-meeting altitude [m]
    max_lateral_error: float = 2.0         # [m] at catch altitude
    far_field_error: float = 20.0          # [m] above flip end
    flip_end_alt: float = 150.0

    def lateral_window(self, altitude: float) -> float:
        """Allowable lateral error (m) as a function of altitude.

        Linearly tightens from ``far_field_error`` (at ``flip_end_alt``)
        down to ``max_lateral_error`` (at ``catch_altitude``). Below
        ``catch_altitude`` the tolerance freezes.
        """
        if altitude >= self.flip_end_alt:
            return self.far_field_error
        if altitude <= self.catch_altitude:
            return self.max_lateral_error
        frac = (altitude - self.catch_altitude) / (self.flip_end_alt - self.catch_altitude)
        return self.max_lateral_error + frac * (self.far_field_error - self.max_lateral_error)


# ---------------------------------------------------------------------------
# Thrust allocation : min ‖A t − wrench‖² s.t. t_min ≤ t ≤ t_max
# ---------------------------------------------------------------------------

@dataclass
class ThrustAllocator:
    """Map a 6-D wrench (force, torque) demand to per-thruster magnitudes.

    Column `i` of `A` is `[d_i;  l_i × d_i]` (see §8).
    """
    bank: ThrusterBank

    def allocate(self, force_demand: np.ndarray,
                 torque_demand: np.ndarray
                 ) -> Tuple[np.ndarray, float]:
        A = self.bank.geometry_matrix()
        b = np.concatenate([np.asarray(force_demand, dtype=float),
                            np.asarray(torque_demand, dtype=float)])
        lb = np.array([t.T_min for t in self.bank])
        ub = np.array([t.T_max for t in self.bank])
        res = lsq_linear(A, b, bounds=(lb, ub))
        return res.x, float(np.linalg.norm(A @ res.x - b))


# ---------------------------------------------------------------------------
# Outer-loop controller
# ---------------------------------------------------------------------------

@dataclass
class CatchController:
    """PD outer loop + LS inner allocation.

    The outer loop turns ``(state_est, state_ref)`` into a 6-D wrench
    demand; the allocator distributes it across the thruster bank. The
    interface is deliberately minimal so the same object plugs into the
    :class:`~starship.pipeline.RecoveryPipeline`.
    """

    geometry: CatchGeometry
    bank: ThrusterBank
    kp_pos: float = 0.8
    kd_pos: float = 1.4
    kp_att: float = 2.0
    kd_att: float = 4.0
    mass: float = 200_000.0
    gravity: np.ndarray = field(default_factory=lambda: np.array([0, 0, -9.80665]))
    _allocator: ThrustAllocator = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._allocator = ThrustAllocator(self.bank)

    # ------------------------------------------------------------------
    def step(self, state: State6DOF,
             target_position: np.ndarray,
             target_velocity: np.ndarray,
             target_axis_body: np.ndarray = np.array([0.0, 0.0, 1.0])
             ) -> Tuple[np.ndarray, dict]:
        """Compute per-thruster commands for the catch phase."""
        # Position → vertical + horizontal force demand
        e_pos = target_position - state.r
        e_vel = target_velocity - state.v
        accel_cmd = self.kp_pos * e_pos + self.kd_pos * e_vel - self.gravity
        force_demand = self.mass * accel_cmd

        # Attitude : keep body z aligned with target_axis (usually vertical)
        # compute body-z in inertial frame
        from .quaternion import Quaternion
        R = Quaternion.from_array(state.q).to_matrix()
        body_z_inertial = R @ np.array([0.0, 0.0, 1.0])
        target_axis_inertial = np.asarray(target_axis_body, dtype=float)
        # Small-angle control torque from cross-product error
        torque_demand = (self.kp_att * np.cross(body_z_inertial,
                                                target_axis_inertial)
                         - self.kd_att * state.w)

        # Transform force demand to body frame for thrust allocation
        force_body = R.T @ force_demand
        thrusts, residual = self._allocator.allocate(force_body, torque_demand)

        info = {
            "lateral_window": float(self.geometry.lateral_window(state.r[2])),
            "lateral_error": float(np.hypot(e_pos[0], e_pos[1])),
            "altitude": float(state.r[2]),
            "alloc_residual": residual,
            "thrusts": thrusts.tolist(),
        }
        return thrusts, info
