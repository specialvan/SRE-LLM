"""§3 6-DoF rigid-body dynamics — before vs after.

Illustrates *why* you need the full quaternion formulation instead of
Euler-angle small-angle kinematics.

Baseline : integrate Euler-angle kinematics `q̇_euler = ω` naïvely.
After    : integrate with the quaternion kinematics `q̇ = ½ Ω(ω) q` and
           the exponential-map update from ``starship.quaternion``.

Test scenario : a booster rotating with ω = [0.1, 0.1, 0.0] rad/s for
5 s.  The "ground truth" is obtained with ``scipy.spatial.transform``.

Metrics compared :
    - rotation angle RMSE vs ground truth
    - norm of attitude vector (|q| − 1)  — quaternion drift
    - final pointing error of the body z-axis
"""

from __future__ import annotations

import numpy as np
from scipy.spatial.transform import Rotation

from starship.quaternion import Quaternion, integrate_quaternion
from analysis._common import HAS_MPL, save_fig, summary_banner


def ground_truth(w: np.ndarray, ts: np.ndarray) -> np.ndarray:
    """Analytical rotation for constant angular velocity."""
    rots = [Rotation.from_rotvec(w * t) for t in ts]
    return np.stack([r.as_matrix() for r in rots])


def naive_euler_integration(w: np.ndarray, ts: np.ndarray) -> np.ndarray:
    """Integrate attitude as if ω were the *Euler-angle rate* directly.

    This is only correct for infinitesimally small rotations — perfect
    baseline to demonstrate what the full quaternion buys you.
    """
    dt = ts[1] - ts[0]
    euler = np.zeros(3)
    mats = []
    for _ in ts:
        mats.append(Rotation.from_euler("xyz", euler).as_matrix())
        euler = euler + w * dt
    return np.stack(mats)


def quat_integration(w: np.ndarray, ts: np.ndarray) -> np.ndarray:
    dt = ts[1] - ts[0]
    q = np.array([1.0, 0.0, 0.0, 0.0])
    mats = []
    for _ in ts:
        mats.append(Quaternion.from_array(q).to_matrix())
        q = integrate_quaternion(q, w, dt)
    return np.stack(mats), q


def _angle_rmse(R_est: np.ndarray, R_truth: np.ndarray) -> float:
    angles = []
    for Re, Rt in zip(R_est, R_truth):
        R_rel = Rt.T @ Re
        # clamp for numerical safety
        trace = np.clip((np.trace(R_rel) - 1.0) / 2.0, -1.0, 1.0)
        angles.append(np.arccos(trace))
    return float(np.sqrt(np.mean(np.square(angles))))


def main() -> dict:
    w = np.array([0.1, 0.1, 0.0])
    ts = np.linspace(0, 5.0, 101)

    R_truth = ground_truth(w, ts)

    R_naive = naive_euler_integration(w, ts)
    R_quat, q_final = quat_integration(w, ts)

    before_metrics = {
        "angle_rmse_rad": _angle_rmse(R_naive, R_truth),
        "final_body_z_err": float(np.linalg.norm(
            R_naive[-1] @ np.array([0, 0, 1]) - R_truth[-1] @ np.array([0, 0, 1]))),
    }
    after_metrics = {
        "angle_rmse_rad": _angle_rmse(R_quat, R_truth),
        "final_body_z_err": float(np.linalg.norm(
            R_quat[-1] @ np.array([0, 0, 1]) - R_truth[-1] @ np.array([0, 0, 1]))),
        "quat_norm_drift": float(abs(np.linalg.norm(q_final) - 1.0)),
    }
    before_metrics["quat_norm_drift"] = 0.0

    banner = summary_banner("§3 6-DoF Rigid-Body Dynamics",
                             before_metrics, after_metrics)
    print(banner)

    if HAS_MPL:
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(7, 4))
        # plot per-sample angle error
        err_naive = np.array([
            np.arccos(np.clip((np.trace(Rt.T @ Re) - 1) / 2, -1, 1))
            for Re, Rt in zip(R_naive, R_truth)
        ])
        err_quat = np.array([
            np.arccos(np.clip((np.trace(Rt.T @ Re) - 1) / 2, -1, 1))
            for Re, Rt in zip(R_quat, R_truth)
        ])
        ax.plot(ts, np.rad2deg(err_naive), label="baseline (Euler integration)")
        ax.plot(ts, np.rad2deg(err_quat),  label="quaternion q̇ = ½Ω(ω)q")
        ax.set_xlabel("t [s]"); ax.set_ylabel("attitude error [°]")
        ax.set_title("§3 attitude error growth")
        ax.legend(); ax.grid(True, alpha=0.3)
        save_fig(fig, "s03_rigid_body")
        plt.close(fig)

    return {"before": before_metrics, "after": after_metrics, "banner": banner}


if __name__ == "__main__":
    main()
