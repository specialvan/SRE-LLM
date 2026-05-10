"""End-to-end recovery pipeline : EKF → MPC/PDG → Thrust allocation.

The pipeline wires together §5 (:mod:`ekf`), §6 (:mod:`mpc`), §7
(:mod:`flip_maneuver`) and §8 (:mod:`catch_controller`). At every
simulation step we:

1. Run sensor updates and obtain the fused state estimate.
2. Choose a controller according to the flight phase
   (powered descent / flip / catch).
3. Allocate the wrench to individual thrusters.
4. Compute the net body-frame force/torque and advance the truth model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Sequence, Tuple

import numpy as np

from .catch_controller import CatchController, CatchGeometry
from .ekf import MultiSensorEKF
from .flip_maneuver import FlipPlanner, net_torque
from .quaternion import Quaternion
from .rigid_body import RigidBody
from .types import State6DOF, ThrusterBank


class Phase(str, Enum):
    POWERED_DESCENT = "powered_descent"
    FLIP = "flip"
    CATCH = "catch"


@dataclass
class RecoveryPipeline:
    """One-object glue layer.

    The truth :class:`RigidBody` lives inside the pipeline for
    self-contained simulations; real flight hardware would replace
    ``step_truth`` with a sensor driver.
    """

    truth: RigidBody
    bank: ThrusterBank
    ekf: Optional[MultiSensorEKF] = None
    geometry: CatchGeometry = field(default_factory=CatchGeometry)
    flip_planner: FlipPlanner = field(default_factory=FlipPlanner)
    mass: float = 200_000.0
    _catch: CatchController = field(init=False, repr=False)
    _phase: Phase = field(init=False, default=Phase.POWERED_DESCENT)

    def __post_init__(self) -> None:
        self._catch = CatchController(self.geometry, self.bank, mass=self.mass)

    # ------------------------------------------------------------------
    def _select_phase(self, altitude: float) -> Phase:
        if altitude > self.geometry.flip_end_alt:
            return Phase.POWERED_DESCENT
        if altitude > self.geometry.catch_altitude:
            return Phase.FLIP
        return Phase.CATCH

    # ------------------------------------------------------------------
    def step(self, state: State6DOF, dt: float) -> Tuple[State6DOF, dict]:
        """Run one control step and return the next truth state + trace."""
        phase = self._select_phase(state.r[2])
        target = np.array([self.geometry.tower_position[0],
                            self.geometry.tower_position[1],
                            max(state.r[2] - 5.0, 0.0)])
        thrusts, ctrl_info = self._catch.step(state, target, np.zeros(3))

        # Clip to per-thruster bounds
        for i, t in enumerate(self.bank):
            thrusts[i] = float(np.clip(thrusts[i], t.T_min, t.T_max))

        # Net body-frame force & torque
        force_body = np.zeros(3)
        for t, mag in zip(self.bank, thrusts):
            d = t.direction / (np.linalg.norm(t.direction) + 1e-12)
            force_body += mag * d
        torque_body = net_torque(self.bank, thrusts)

        next_state = self.truth.step(state, force_body, torque_body, dt)

        trace = {
            "phase": phase.value,
            "altitude": float(state.r[2]),
            "lateral_error": ctrl_info["lateral_error"],
            "window": ctrl_info["lateral_window"],
            "thrusts": ctrl_info["thrusts"],
        }
        return next_state, trace
