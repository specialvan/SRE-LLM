"""starship — Starship Super Heavy chopstick-catch recovery pipeline.

Each module maps to one of the 8 mathematical pillars identified from
``DOC/spacex/``:

- ``types``             — basic data structures
- ``quaternion``        — unit-quaternion algebra for SO(3)
- ``rigid_body``        — §3 6-DoF dynamics  q̇, ω̇, ṙ, v̇
- ``lossless_convex``   — §1 Lossless convexification of PDG
- ``scp``               — §2 Successive Convex Programming
- ``thrust_constraints``— §4 pointing cone & magnitude
- ``ekf``               — §5 multi-sensor EKF (radar/IMU/fiducial)
- ``mpc``               — §6 receding-horizon quadratic MPC
- ``flip_maneuver``     — §7 belly-flop → landing-flip
- ``catch_controller``  — §8 tower-arm catch phase
- ``pipeline``          — §5→§6→§8 end-to-end assembly
"""

from .types import (
    G0_EARTH,
    GRAVITY_EARTH,
    State6DOF,
    Thruster,
    ThrusterBank,
    VehicleParams,
    DEFAULT_STARSHIP,
)
from .quaternion import Quaternion, omega_matrix
from .rigid_body import RigidBody
from .thrust_constraints import (
    ConeQPFilter,
    magnitude_bound,
    pointing_cone_constraint,
)
from .ekf import EKF, MultiSensorEKF, RadarMeasurement, IMUMeasurement, FiducialMeasurement
from .mpc import LinearDiscretizer, QuadraticMPC
from .lossless_convex import LosslessPDG
from .scp import SCP, linearize
from .flip_maneuver import FlipPlanner, bellyflop_reference, net_torque
from .catch_controller import CatchController, CatchGeometry, ThrustAllocator
from .pipeline import RecoveryPipeline

__all__ = [
    # types
    "G0_EARTH", "GRAVITY_EARTH", "State6DOF",
    "Thruster", "ThrusterBank", "VehicleParams", "DEFAULT_STARSHIP",
    # quaternion / rigid body
    "Quaternion", "omega_matrix", "RigidBody",
    # thrust constraints
    "ConeQPFilter", "magnitude_bound", "pointing_cone_constraint",
    # EKF
    "EKF", "MultiSensorEKF",
    "RadarMeasurement", "IMUMeasurement", "FiducialMeasurement",
    # MPC
    "LinearDiscretizer", "QuadraticMPC",
    # convex / SCP
    "LosslessPDG", "SCP", "linearize",
    # flip
    "FlipPlanner", "bellyflop_reference", "net_torque",
    # catch
    "CatchController", "CatchGeometry", "ThrustAllocator",
    # pipeline
    "RecoveryPipeline",
]

__version__ = "0.1.0"
