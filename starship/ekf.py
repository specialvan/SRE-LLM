"""Extended Kalman Filter with multi-sensor fusion — §5.

Implements the classic EKF update from ``image-1``/``image-10``/``image-19``::

    x̂_{k|k−1} = f(x̂_{k−1|k−1}, u)
    P_{k|k−1} = F P_{k−1|k−1} F^T + Q
    y_k       = z_k − h(x̂_{k|k−1})
    S_k       = H P H^T + R
    K_k       = P H^T S_k^{-1}
    x̂_{k|k}  = x̂_{k|k−1} + K_k · y_k
    P_{k|k}   = (I − K_k H) P_{k|k−1}

This file ships three measurement models:
  * :class:`RadarMeasurement`     — tower-side radar (range / az / el)
  * :class:`IMUMeasurement`       — strap-down IMU (angular rate + specific force)
  * :class:`FiducialMeasurement`  — pinhole camera on tower-side AprilTag
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence, Tuple

import numpy as np


# ---------------------------------------------------------------------------
# Base EKF
# ---------------------------------------------------------------------------

@dataclass
class EKF:
    """Single-state EKF.

    ``state_dim`` is generic — this object does not assume the 13-d
    Starship layout, so the same class powers the simple test cases.
    """
    x: np.ndarray                      # state estimate, shape (n,)
    P: np.ndarray                      # covariance, shape (n, n)
    process_noise: np.ndarray          # Q, shape (n, n)
    f: Callable[[np.ndarray, np.ndarray, float], np.ndarray]
    F_jac: Optional[Callable[[np.ndarray, np.ndarray, float], np.ndarray]] = None

    # ------------------------------------------------------------------
    def predict(self, u: np.ndarray, dt: float) -> None:
        F = self._jac_F(self.x, u, dt)
        self.x = self.f(self.x, u, dt)
        self.P = F @ self.P @ F.T + self.process_noise

    # ------------------------------------------------------------------
    def update(self, z: np.ndarray,
               h: Callable[[np.ndarray], np.ndarray],
               H: Callable[[np.ndarray], np.ndarray],
               R: np.ndarray) -> None:
        y = np.asarray(z, dtype=float) - h(self.x)
        H_mat = H(self.x)
        S = H_mat @ self.P @ H_mat.T + R
        K = np.linalg.solve(S.T, (self.P @ H_mat.T).T).T
        self.x = self.x + K @ y
        I = np.eye(self.P.shape[0])
        self.P = (I - K @ H_mat) @ self.P

    # ------------------------------------------------------------------
    def _jac_F(self, x: np.ndarray, u: np.ndarray, dt: float) -> np.ndarray:
        if self.F_jac is not None:
            return self.F_jac(x, u, dt)
        # numerical Jacobian
        eps = 1e-6
        n = x.size
        F = np.zeros((n, n))
        fx = self.f(x, u, dt)
        for i in range(n):
            xp = x.copy()
            xp[i] += eps
            F[:, i] = (self.f(xp, u, dt) - fx) / eps
        return F


# ---------------------------------------------------------------------------
# Measurement models
# ---------------------------------------------------------------------------

@dataclass
class RadarMeasurement:
    """Range / azimuth / elevation from a ground radar at ``tower``.

    State layout : first three entries of ``x`` are inertial (r_x, r_y, r_z).
    """
    tower: np.ndarray = field(default_factory=lambda: np.zeros(3))
    R: np.ndarray = field(default_factory=lambda: np.diag([1.0, 1e-4, 1e-4]))

    def h(self, x: np.ndarray) -> np.ndarray:
        d = x[0:3] - self.tower
        rng = float(np.linalg.norm(d))
        az = float(np.arctan2(d[1], d[0]))
        el = float(np.arctan2(d[2], np.hypot(d[0], d[1]) + 1e-9))
        return np.array([rng, az, el])

    def H(self, x: np.ndarray) -> np.ndarray:
        n = x.size
        H = np.zeros((3, n))
        dx, dy, dz = x[0] - self.tower[0], x[1] - self.tower[1], x[2] - self.tower[2]
        rng = np.sqrt(dx * dx + dy * dy + dz * dz) + 1e-9
        rxy2 = dx * dx + dy * dy + 1e-12
        rxy = np.sqrt(rxy2)
        H[0, 0:3] = [dx / rng, dy / rng, dz / rng]                   # d range
        H[1, 0:3] = [-dy / rxy2, dx / rxy2, 0.0]                      # d az
        H[2, 0:3] = [-dx * dz / (rxy * rng * rng),
                     -dy * dz / (rxy * rng * rng),
                     rxy / (rng * rng)]                              # d el
        return H


@dataclass
class IMUMeasurement:
    """Strap-down IMU : angular velocity (body) and specific force.

    Assumes state layout ``[r(3), v(3), q(4), w(3), ...]``.
    """
    gravity: np.ndarray = field(default_factory=lambda: np.array([0, 0, -9.80665]))
    R: np.ndarray = field(default_factory=lambda: np.diag(
        [1e-4, 1e-4, 1e-4, 1e-2, 1e-2, 1e-2]))

    def h(self, x: np.ndarray) -> np.ndarray:
        # The IMU reports (ω_body, v̇_body − R^T g).  Here, as a light-weight
        # measurement, we assume v is almost constant, so a_body ≈ R^T(-g).
        q = x[6:10]
        w = x[10:13]
        from .quaternion import Quaternion
        R = Quaternion.from_array(q).to_matrix()
        a_body = R.T @ (-self.gravity)
        return np.concatenate([w, a_body])

    def H(self, x: np.ndarray) -> np.ndarray:
        # numerical Jacobian — good enough for prototyping
        n = x.size
        H = np.zeros((6, n))
        eps = 1e-5
        hx = self.h(x)
        for i in range(n):
            xp = x.copy(); xp[i] += eps
            H[:, i] = (self.h(xp) - hx) / eps
        return H


@dataclass
class FiducialMeasurement:
    """Pinhole-camera projection of a tower-mounted marker.

    Given a marker at inertial position ``P`` and a camera at the booster
    at inertial position ``r_cam = r + R(q) · c_body``, the pixel location
    is::

        z = π( K · R(q)^T · (P − r) )
    """
    marker_world: np.ndarray
    K: np.ndarray = field(default_factory=lambda: np.array(
        [[800., 0., 320.], [0., 800., 240.], [0., 0., 1.]]))
    R: np.ndarray = field(default_factory=lambda: np.diag([2.0, 2.0]))

    def h(self, x: np.ndarray) -> np.ndarray:
        from .quaternion import Quaternion
        r = x[0:3]
        q = x[6:10]
        Rmat = Quaternion.from_array(q).to_matrix()
        p_body = Rmat.T @ (self.marker_world - r)
        # Camera along body z+ :
        z_cam = p_body[2] if abs(p_body[2]) > 1e-3 else 1e-3
        u = self.K[0, 0] * p_body[0] / z_cam + self.K[0, 2]
        v = self.K[1, 1] * p_body[1] / z_cam + self.K[1, 2]
        return np.array([u, v])

    def H(self, x: np.ndarray) -> np.ndarray:
        n = x.size
        H = np.zeros((2, n))
        eps = 1e-5
        hx = self.h(x)
        for i in range(n):
            xp = x.copy(); xp[i] += eps
            H[:, i] = (self.h(xp) - hx) / eps
        return H


# ---------------------------------------------------------------------------
# Multi-sensor wrapper
# ---------------------------------------------------------------------------

class MultiSensorEKF:
    """Thin wrapper that sequences sensor updates.

    ``step(dt, sensor_stream)`` expects a list of ``(measurement_obj, z)``
    pairs — missing sensors simply pass ``None``.
    """

    def __init__(self, ekf: EKF) -> None:
        self.ekf = ekf

    def step(self, u: np.ndarray, dt: float,
             measurements: Sequence[Tuple[object, np.ndarray]]) -> np.ndarray:
        self.ekf.predict(u, dt)
        for sensor, z in measurements:
            if z is None:
                continue
            self.ekf.update(z, sensor.h, sensor.H, sensor.R)
        return self.ekf.x.copy()
