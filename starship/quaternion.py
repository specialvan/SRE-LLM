"""Unit-quaternion algebra for SO(3) — §3.

Convention : ``q = [w, x, y, z]`` with ``w`` scalar. The quaternion
rotates a body-frame vector to the inertial frame via

    v_inertial = q ⊗ [0, v_body] ⊗ q*

Matches ``scipy.spatial.transform.Rotation.from_quat([x, y, z, w])`` up
to coordinate order.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np


# ---------------------------------------------------------------------------
# Omega matrix used in q̇ = ½ Ω(ω) q
# ---------------------------------------------------------------------------

def omega_matrix(w: Sequence[float]) -> np.ndarray:
    """Return the 4×4 skew-like matrix Ω(ω).

    Defined so that ``q̇ = 0.5 · Ω(ω) · q`` where ``q = [w, x, y, z]``.
    """
    wx, wy, wz = float(w[0]), float(w[1]), float(w[2])
    return np.array([
        [0.0, -wx, -wy, -wz],
        [wx,  0.0,  wz, -wy],
        [wy, -wz,  0.0,  wx],
        [wz,  wy, -wx,  0.0],
    ])


# ---------------------------------------------------------------------------
# Quaternion dataclass
# ---------------------------------------------------------------------------

@dataclass
class Quaternion:
    w: float = 1.0
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    # ---- construction --------------------------------------------------
    @classmethod
    def identity(cls) -> "Quaternion":
        return cls(1.0, 0.0, 0.0, 0.0)

    @classmethod
    def from_array(cls, a: Sequence[float]) -> "Quaternion":
        return cls(float(a[0]), float(a[1]), float(a[2]), float(a[3]))

    @classmethod
    def from_axis_angle(cls, axis: Sequence[float], angle: float
                        ) -> "Quaternion":
        axis = np.asarray(axis, dtype=float)
        n = np.linalg.norm(axis)
        if n < 1e-12:
            return cls.identity()
        axis = axis / n
        half = 0.5 * angle
        s = np.sin(half)
        return cls(float(np.cos(half)),
                   float(axis[0] * s),
                   float(axis[1] * s),
                   float(axis[2] * s))

    # ---- conversion ----------------------------------------------------
    def as_array(self) -> np.ndarray:
        return np.array([self.w, self.x, self.y, self.z], dtype=float)

    def normalized(self) -> "Quaternion":
        a = self.as_array()
        n = float(np.linalg.norm(a))
        if n < 1e-12:
            return Quaternion.identity()
        return Quaternion.from_array(a / n)

    def conj(self) -> "Quaternion":
        return Quaternion(self.w, -self.x, -self.y, -self.z)

    def to_matrix(self) -> np.ndarray:
        """3×3 rotation matrix body→inertial."""
        w, x, y, z = self.w, self.x, self.y, self.z
        return np.array([
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w),     2 * (x * z + y * w)],
            [2 * (x * y + z * w),     1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w),     2 * (y * z + x * w),     1 - 2 * (x * x + y * y)],
        ])

    # ---- algebra -------------------------------------------------------
    def __mul__(self, other: "Quaternion") -> "Quaternion":
        w1, x1, y1, z1 = self.w, self.x, self.y, self.z
        w2, x2, y2, z2 = other.w, other.x, other.y, other.z
        return Quaternion(
            w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
            w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
        )

    def rotate(self, v: Sequence[float]) -> np.ndarray:
        """Rotate a 3-vector from body to inertial frame."""
        return self.to_matrix() @ np.asarray(v, dtype=float)


# ---------------------------------------------------------------------------
# Integration helper: q_{k+1} = exp(½ ω dt) ⊗ q_k
# ---------------------------------------------------------------------------

def integrate_quaternion(q: np.ndarray, w: np.ndarray, dt: float) -> np.ndarray:
    """Exponential-map quaternion integration; preserves unit norm."""
    wnorm = float(np.linalg.norm(w))
    if wnorm < 1e-8:
        dq = np.array([1.0, 0.5 * w[0] * dt, 0.5 * w[1] * dt, 0.5 * w[2] * dt])
    else:
        half = 0.5 * wnorm * dt
        axis = w / wnorm
        s = np.sin(half)
        dq = np.array([np.cos(half), axis[0] * s, axis[1] * s, axis[2] * s])
    # Quaternion product dq ⊗ q
    out = (Quaternion.from_array(dq) * Quaternion.from_array(q)).as_array()
    return out / (np.linalg.norm(out) + 1e-12)
