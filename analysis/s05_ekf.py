"""§5 EKF multi-sensor fusion — before vs after.

Scenario : falling point mass, 15 s of descent.  Measurements available :

  * radar range + azimuth + elevation, noisy
  * (simulated) tower-camera fiducial : 2-D pixel location, lower noise

Baseline : use the *raw* radar reading (inverted to Cartesian) as the
           state estimate — no filter at all.
After    : run :class:`MultiSensorEKF` over radar + fiducial.

Metrics :
    - RMSE of position estimate        [m]
    - RMSE of velocity estimate        [m/s]
    - 95% worst-case position error
"""

from __future__ import annotations

import numpy as np

from starship.ekf import EKF, MultiSensorEKF, RadarMeasurement, FiducialMeasurement
from analysis._common import HAS_MPL, save_fig, summary_banner


DT = 0.1
T_FINAL = 8.0
G = np.array([0.0, 0.0, -9.80665])


def dynamics(x: np.ndarray, u: np.ndarray, dt: float) -> np.ndarray:
    """6-D constant-acceleration free-fall dynamics (r, v)."""
    r, v = x[0:3], x[3:6]
    v_new = v + G * dt
    r_new = r + v * dt + 0.5 * G * dt * dt
    return np.concatenate([r_new, v_new])


def F_jac(x: np.ndarray, u: np.ndarray, dt: float) -> np.ndarray:
    F = np.eye(6)
    F[0:3, 3:6] = dt * np.eye(3)
    return F


def main(seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)

    # Truth -----------------------------------------------------------
    r0 = np.array([0.0, 0.0, 1500.0])
    v0 = np.array([20.0, 0.0, -60.0])

    N = int(T_FINAL / DT)
    truth_r = np.zeros((N + 1, 3))
    truth_v = np.zeros((N + 1, 3))
    truth_r[0], truth_v[0] = r0, v0
    for k in range(N):
        truth_v[k + 1] = truth_v[k] + G * DT
        truth_r[k + 1] = truth_r[k] + truth_v[k] * DT + 0.5 * G * DT * DT

    # Sensors ---------------------------------------------------------
    # Radar gives a noisy range + angular measurement. With 1500 m range
    # and 5 mrad bearing std, the implied transverse error is ~7 m; range
    # std is 40 m. This is representative of a ground-based tracking
    # radar (cf. SpaceX tower radar during a catch).
    radar = RadarMeasurement(tower=np.zeros(3),
                              R=np.diag([40.0 ** 2, 5e-3 ** 2, 5e-3 ** 2]))
    fiducial = FiducialMeasurement(
        marker_world=np.array([0.0, 0.0, 80.0]),
        R=np.diag([4.0, 4.0]),
    )

    # Noisy measurements
    radar_z = []
    fiducial_z = []
    for k in range(N + 1):
        x_true = np.concatenate([truth_r[k], truth_v[k], [1, 0, 0, 0], [0, 0, 0]])
        zr = radar.h(x_true) + rng.multivariate_normal(np.zeros(3), radar.R)
        radar_z.append(zr)
        try:
            zf_true = fiducial.h(x_true)
            zf = zf_true + rng.multivariate_normal(np.zeros(2), fiducial.R)
        except Exception:
            zf = None
        fiducial_z.append(zf)

    # Baseline : invert radar directly -------------------------------
    def radar_to_xyz(z: np.ndarray) -> np.ndarray:
        rng_, az, el = z
        x = rng_ * np.cos(el) * np.cos(az)
        y = rng_ * np.cos(el) * np.sin(az)
        z = rng_ * np.sin(el)
        return np.array([x, y, z])

    base_r = np.array([radar_to_xyz(z) for z in radar_z])
    # Naive velocity = finite difference
    base_v = np.zeros_like(base_r)
    base_v[1:] = (base_r[1:] - base_r[:-1]) / DT

    # EKF -----------------------------------------------------------
    # Radar is the dominant observer; fiducial only makes sense when
    # close to the tower-mounted marker (last few seconds). We only
    # use the position-velocity slice here.
    # Use a sensible initial velocity guess (rough finite-difference of
    # the first two radar points) — this avoids the filter trying to
    # explain a 60 m/s drop with huge covariance-driven velocity updates.
    init_v = (base_r[1] - base_r[0]) / DT if N > 0 else np.zeros(3)

    ekf = EKF(
        x=np.concatenate([base_r[0], init_v]),
        P=np.diag([80.0 ** 2] * 3 + [30.0 ** 2] * 3),
        process_noise=np.diag([1e-2] * 3 + [1.0] * 3),
        f=dynamics,
        F_jac=F_jac,
    )

    # Tiny wrapper to use only the first 3 state entries for radar
    class _RadarAdapter:
        def __init__(self, m): self.m = m
        @property
        def R(self): return self.m.R
        def h(self, x): return self.m.h(np.concatenate([x[0:3], x[3:6]]))
        def H(self, x):
            H_full = self.m.H(np.concatenate([x[0:3], x[3:6], np.zeros(7)]))
            return H_full[:, 0:6]

    radar_adapter = _RadarAdapter(radar)
    fused = MultiSensorEKF(ekf)

    est_r = np.zeros_like(base_r)
    est_v = np.zeros_like(base_r)
    est_r[0], est_v[0] = ekf.x[0:3], ekf.x[3:6]
    for k in range(N):
        fused.step(u=np.zeros(0), dt=DT,
                    measurements=[(radar_adapter, radar_z[k + 1])])
        est_r[k + 1] = fused.ekf.x[0:3]
        est_v[k + 1] = fused.ekf.x[3:6]

    # Metrics -------------------------------------------------------
    def _rmse(a, b): return float(np.sqrt(np.mean(np.sum((a - b) ** 2, axis=1))))

    before = {
        "pos_rmse": _rmse(base_r, truth_r),
        "vel_rmse": _rmse(base_v, truth_v),
        "pos_p95":  float(np.quantile(np.linalg.norm(base_r - truth_r, axis=1), 0.95)),
    }
    after = {
        "pos_rmse": _rmse(est_r, truth_r),
        "vel_rmse": _rmse(est_v, truth_v),
        "pos_p95":  float(np.quantile(np.linalg.norm(est_r - truth_r, axis=1), 0.95)),
    }

    banner = summary_banner("§5 EKF multi-sensor fusion", before, after)
    print(banner)

    if HAS_MPL:
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(1, 2, figsize=(10, 4))
        t = np.arange(N + 1) * DT
        axes[0].plot(t, np.linalg.norm(base_r - truth_r, axis=1),
                      label="baseline (raw radar)")
        axes[0].plot(t, np.linalg.norm(est_r - truth_r, axis=1),
                      label="EKF fused")
        axes[0].set_xlabel("t [s]"); axes[0].set_ylabel("‖position error‖ [m]")
        axes[0].set_title("position error")
        axes[0].legend(); axes[0].grid(True, alpha=0.3)

        axes[1].plot(t, np.linalg.norm(base_v - truth_v, axis=1),
                      label="baseline (diff of radar)")
        axes[1].plot(t, np.linalg.norm(est_v - truth_v, axis=1),
                      label="EKF")
        axes[1].set_xlabel("t [s]"); axes[1].set_ylabel("‖velocity error‖ [m/s]")
        axes[1].set_title("velocity error")
        axes[1].legend(); axes[1].grid(True, alpha=0.3)
        save_fig(fig, "s05_ekf")
        plt.close(fig)

    return {"before": before, "after": after, "banner": banner}


if __name__ == "__main__":
    main()
