"""§4 Thrust pointing cone — before vs after.

Scenario : a neural/NN controller (here mocked by uniform random
samples) proposes thrust vectors.  Without the cone + magnitude
filter the vehicle would gimbal wildly and overshoot its envelope.

Baseline : accept ``u_nom`` unchanged.
After    : pass through :class:`ConeQPFilter` which projects onto the
           intersection of the Lorentz cone and the ball.

Metrics :
    - fraction of samples violating the cone (before / after)
    - fraction exceeding T_max
    - mean projection cost  ‖u − u_nom‖
"""

from __future__ import annotations

import numpy as np

from starship.thrust_constraints import (ConeQPFilter,
                                         pointing_cone_constraint)
from analysis._common import HAS_MPL, save_fig, summary_banner


def main(n_samples: int = 2000, seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    T_max = 2.3e6
    theta_max = np.deg2rad(15.0)
    n_hat = np.array([0.0, 0.0, 1.0])

    # Random thrust samples inside a larger cube to exercise both
    # violations (magnitude and direction).
    scale = 3.0e6
    U = rng.uniform(-scale, scale, size=(n_samples, 3))
    # Bias toward z+ to mimic "nominal up" commands.
    U[:, 2] += 1.5e6

    filt = ConeQPFilter(n_hat=n_hat, theta_max=theta_max,
                        T_max=T_max, T_min=0.0)

    U_after = np.array([filt.filter(u) for u in U])

    def _cone_violations(U: np.ndarray) -> int:
        return int(np.sum([pointing_cone_constraint(u, n_hat, theta_max) < -1e-4
                           for u in U]))

    def _mag_violations(U: np.ndarray) -> int:
        return int(np.sum(np.linalg.norm(U, axis=1) > T_max + 1e-6))

    before = {
        "cone_violations": _cone_violations(U) / n_samples,
        "mag_violations":  _mag_violations(U) / n_samples,
        "mean_magnitude":  float(np.mean(np.linalg.norm(U, axis=1))),
    }
    after = {
        "cone_violations": _cone_violations(U_after) / n_samples,
        "mag_violations":  _mag_violations(U_after) / n_samples,
        "mean_magnitude":  float(np.mean(np.linalg.norm(U_after, axis=1))),
        "mean_projection_cost": float(np.mean(np.linalg.norm(U - U_after, axis=1))),
    }
    before["mean_projection_cost"] = 0.0

    banner = summary_banner("§4 Thrust Pointing Cone", before, after)
    print(banner)

    if HAS_MPL:
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(1, 2, figsize=(9, 4.2))

        # Project to the (‖u_xy‖, u_z) plane and draw the cone + ball.
        uxy_b = np.linalg.norm(U[:, :2], axis=1)
        uxy_a = np.linalg.norm(U_after[:, :2], axis=1)

        axes[0].scatter(uxy_b, U[:, 2], s=4, alpha=0.25, c="tab:red",
                         label="raw u_nom")
        axes[1].scatter(uxy_a, U_after[:, 2], s=4, alpha=0.25, c="tab:green",
                         label="after filter")

        # Cone boundary :  uxy = uz · tan(theta_max)
        zz = np.linspace(0, T_max, 100)
        axes[0].plot(zz * np.tan(theta_max), zz, "k--", lw=0.8)
        axes[1].plot(zz * np.tan(theta_max), zz, "k--", lw=0.8)

        # Ball boundary (circle of radius T_max in this projection)
        theta = np.linspace(-np.pi / 2, np.pi / 2, 200)
        axes[0].plot(T_max * np.cos(theta), T_max * np.sin(theta), "k:", lw=0.8)
        axes[1].plot(T_max * np.cos(theta), T_max * np.sin(theta), "k:", lw=0.8)

        for ax, title in zip(axes, ["raw u_nom (before)", "filtered (after)"]):
            ax.set_xlabel("‖u_xy‖")
            ax.set_ylabel("u_z")
            ax.set_title(title)
            ax.set_xlim(0, 3.5e6); ax.set_ylim(-1e6, 3.5e6)
            ax.grid(True, alpha=0.3); ax.legend(loc="lower right")

        save_fig(fig, "s04_thrust_cone")
        plt.close(fig)

    return {"before": before, "after": after, "banner": banner}


if __name__ == "__main__":
    main()
