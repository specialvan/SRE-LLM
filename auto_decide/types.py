"""Common data types shared across the package.

Article reference:
    §1.2 连续层：高维非欧几何相空间
    x = (x, v, a, μ)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np


class AgentType(str, Enum):
    """Types of traffic participants represented as nodes of G_I (§1.1)."""
    CAR = "car"
    PEDESTRIAN = "pedestrian"
    BIKE = "bike"
    STATIC = "static"
    EGO = "ego"


@dataclass
class State:
    """Vehicle state on the nonlinear manifold.

    Corresponds to x = (x, v, a, μ) in §1.2, expanded to the bicycle model:

        [px, py, psi, v, a, mu]

    ``mu`` is the road friction coefficient; the tyre constraint |a| ≤ μ·g
    lives on the manifold and is enforced in :class:`BicycleModel`.
    """
    px: float = 0.0
    py: float = 0.0
    psi: float = 0.0       # heading angle [rad]
    v: float = 0.0         # longitudinal velocity [m/s]
    a: float = 0.0         # longitudinal acceleration [m/s^2]
    mu: float = 1.0        # friction coefficient ∈ (0, 1.2]

    def to_vec(self) -> np.ndarray:
        return np.array([self.px, self.py, self.psi, self.v, self.a, self.mu],
                        dtype=float)

    @classmethod
    def from_vec(cls, v: np.ndarray) -> "State":
        return cls(float(v[0]), float(v[1]), float(v[2]),
                   float(v[3]), float(v[4]), float(v[5]))


@dataclass
class Control:
    """Control input u = (steer, jerk).

    - ``steer``: front-wheel steering angle [rad]
    - ``jerk``:  time derivative of longitudinal acceleration [m/s^3]

    Jerk is preferred over raw acceleration so the resulting commands are
    continuously differentiable, which simplifies barrier-function gradients.
    """
    steer: float = 0.0
    jerk: float = 0.0

    def to_vec(self) -> np.ndarray:
        return np.array([self.steer, self.jerk], dtype=float)

    @classmethod
    def from_vec(cls, v: np.ndarray) -> "Control":
        return cls(float(v[0]), float(v[1]))


# Physical constants
G = 9.81  # gravity [m/s^2]


@dataclass(frozen=True)
class VehicleParams:
    """Static vehicle parameters used by the bicycle model."""
    wheelbase: float = 2.8           # m
    max_steer: float = np.deg2rad(35)
    max_steer_rate: float = np.deg2rad(90)   # rad/s — informational
    a_max: float = 4.0               # m/s^2, comfort bound
    a_min: float = -8.0              # m/s^2, emergency brake
    jerk_max: float = 6.0            # m/s^3
    v_max: float = 35.0              # m/s


DEFAULT_VEHICLE = VehicleParams()
