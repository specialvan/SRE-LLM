"""Common data types for the Starship recovery pipeline.

Sources: §3 (state), §4 (thruster constraints), §8 (thruster bank).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Sequence

import numpy as np


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

G0_EARTH: float = 9.80665                   # m/s^2 — used in Isp
GRAVITY_EARTH: np.ndarray = np.array([0.0, 0.0, -G0_EARTH])


# ---------------------------------------------------------------------------
# Vehicle state (§3)
# ---------------------------------------------------------------------------

@dataclass
class State6DOF:
    """6-DoF rigid-body state plus mass — 13-d.

    Layout :
        r (3,)   position in inertial frame [m]
        v (3,)   velocity in inertial frame [m/s]
        q (4,)   attitude as unit quaternion [w, x, y, z], body→inertial
        w (3,)   angular velocity in body frame [rad/s]
        m (1,)   mass [kg]
    """
    r: np.ndarray = field(default_factory=lambda: np.zeros(3))
    v: np.ndarray = field(default_factory=lambda: np.zeros(3))
    q: np.ndarray = field(default_factory=lambda: np.array([1.0, 0.0, 0.0, 0.0]))
    w: np.ndarray = field(default_factory=lambda: np.zeros(3))
    m: float = 200_000.0    # kg — Super Heavy empty-ish

    # ---- serialisation -------------------------------------------------
    def to_vec(self) -> np.ndarray:
        return np.concatenate([self.r, self.v, self.q, self.w,
                                np.array([self.m])])

    @classmethod
    def from_vec(cls, v: np.ndarray) -> "State6DOF":
        v = np.asarray(v, dtype=float)
        return cls(r=v[0:3].copy(), v=v[3:6].copy(),
                   q=v[6:10].copy(), w=v[10:13].copy(),
                   m=float(v[13]) if v.size > 13 else 200_000.0)

    def copy(self) -> "State6DOF":
        return State6DOF(self.r.copy(), self.v.copy(), self.q.copy(),
                         self.w.copy(), float(self.m))


# ---------------------------------------------------------------------------
# Vehicle & thruster parameters (§4, §8)
# ---------------------------------------------------------------------------

@dataclass
class VehicleParams:
    """Static parameters of a Super-Heavy-like booster.

    These numbers are order-of-magnitude only and meant to produce
    physically plausible simulations, not match real SpaceX values.
    """
    dry_mass: float = 160_000.0             # kg
    wet_mass: float = 2_000_000.0           # kg (fully fuelled)
    length: float = 71.0                    # m
    radius: float = 4.5                     # m
    Isp: float = 330.0                      # s
    # inertia about body axes (x,y,z) — thin rod approximation
    inertia: np.ndarray = field(default_factory=lambda: np.diag(
        [1.0e8, 1.0e8, 5.0e6]
    ))


@dataclass
class Thruster:
    """Single thruster (e.g. one Raptor engine).

    Everything is in the *body* frame; positive z is up along the vehicle.
    The nominal thrust direction is usually ``[0, 0, 1]`` (pointing down
    when the booster is belly-up), gimballing is modelled by varying
    ``direction`` at call time.
    """
    position: np.ndarray           # (3,) body-frame attachment point
    direction: np.ndarray          # (3,) nominal thrust axis, unit vector
    T_min: float                   # N — non-zero minimum throttle
    T_max: float                   # N
    theta_max_deg: float = 15.0    # max gimbal half-angle

    def theta_max_rad(self) -> float:
        return np.deg2rad(self.theta_max_deg)


@dataclass
class ThrusterBank:
    """A set of thrusters — Super Heavy uses 3 Raptors for landing burn."""
    thrusters: List[Thruster]

    def __iter__(self):
        return iter(self.thrusters)

    def __len__(self) -> int:
        return len(self.thrusters)

    def __getitem__(self, idx: int) -> Thruster:
        return self.thrusters[idx]

    # Build the 6×N wrench-to-force/torque geometry matrix used for
    # allocation (§8). For each thruster column i:
    #     A[:, i] = [d_i; r_i × d_i]  where d_i is the unit thrust axis.
    def geometry_matrix(self) -> np.ndarray:
        cols = []
        for t in self.thrusters:
            d = t.direction / (np.linalg.norm(t.direction) + 1e-12)
            cols.append(np.concatenate([d, np.cross(t.position, d)]))
        return np.stack(cols, axis=1)


def _default_bank() -> ThrusterBank:
    """Three Raptor engines arranged 120° around the booster axis."""
    angle_offset = 2.0 * np.pi / 3.0
    radius = 3.2  # m from booster centreline
    thrusters: List[Thruster] = []
    for i in range(3):
        th = i * angle_offset
        pos = np.array([radius * np.cos(th), radius * np.sin(th), 0.0])
        thrusters.append(Thruster(
            position=pos,
            direction=np.array([0.0, 0.0, 1.0]),   # thrust up in body frame
            T_min=0.4e6,   # 40% throttle
            T_max=2.3e6,   # ~230 tf per Raptor
            theta_max_deg=15.0,
        ))
    return ThrusterBank(thrusters)


DEFAULT_STARSHIP: VehicleParams = VehicleParams()
