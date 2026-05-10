"""§7 Belly-flop → Landing-flip — before vs after.

Baseline : try to flip with a constant, small torque throughout the
           manoeuvre (what you'd do if you didn't solve for the
           torque profile at all).
After    : bang-bang optimal flip from :class:`FlipPlanner` (saturate
           +τ_max, then −τ_max, zero angular velocity at the end).

Metrics :
    - residual pitch error at t = T     [deg]
    - residual angular velocity          [deg/s]
    - total manoeuvre duration           [s]
    - "safety margin" = (available τ_max − |τ used|) / τ_max
"""

from __future__ import annotations

import numpy as np

from starship.flip_maneuver import FlipPlanner
from analysis._common import HAS_MPL, save_fig, summary_banner


def _integrate_constant_torque(tau: float, I: float, theta0: float,
                                T: float, dt: float = 0.05):
    N = int(T / dt)
    t = np.linspace(0, T, N + 1)
    omega = np.zeros(N + 1)
    theta = np.zeros(N + 1); theta[0] = theta0
    for k in range(N):
        omega[k + 1] = omega[k] + (tau / I) * dt
        theta[k + 1] = theta[k] - omega[k + 1] * dt       # flipping direction
    return t, theta, omega


def main() -> dict:
    I = 1.0e8
    tau_max = 6.0e7

    # Baseline : pick a modest 30% torque, same total time as the bang-bang
    planner = FlipPlanner(I_xx=I, tau_max=tau_max,
                           theta_start=np.pi / 2, theta_end=0.0)
    t_bb, th_bb, om_bb = planner.plan()
    T_total = float(t_bb[-1])

    # baseline uses a *constant* downward torque matching the average
    tau_avg = 0.30 * tau_max
    t_b, th_b, om_b = _integrate_constant_torque(
        tau_avg, I, np.pi / 2, T_total)

    before = {
        "final_pitch_deg":  float(np.rad2deg(th_b[-1])),
        "final_omega_degs": float(np.rad2deg(om_b[-1])),
        "duration_s":       T_total,
        "torque_margin":    1.0 - tau_avg / tau_max,
    }
    after = {
        "final_pitch_deg":  float(np.rad2deg(th_bb[-1])),
        "final_omega_degs": float(np.rad2deg(om_bb[-1])),
        "duration_s":       T_total,
        "torque_margin":    0.0,     # bang-bang saturates τ
    }

    banner = summary_banner("§7 Belly-Flop → Landing-Flip", before, after)
    print(banner)

    if HAS_MPL:
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(1, 2, figsize=(10, 4))
        axes[0].plot(t_b,  np.rad2deg(th_b),  label="baseline constant τ")
        axes[0].plot(t_bb, np.rad2deg(th_bb), label="bang-bang (planner)")
        axes[0].axhline(0, color="k", lw=0.5)
        axes[0].axhline(90, color="k", ls="--", lw=0.5, alpha=0.5)
        axes[0].set_xlabel("t [s]"); axes[0].set_ylabel("pitch θ [°]")
        axes[0].set_title("pitch trajectory")
        axes[0].legend(); axes[0].grid(True, alpha=0.3)

        axes[1].plot(t_b,  np.rad2deg(om_b),  label="baseline")
        axes[1].plot(t_bb, np.rad2deg(om_bb), label="bang-bang")
        axes[1].axhline(0, color="k", lw=0.5)
        axes[1].set_xlabel("t [s]"); axes[1].set_ylabel("ω [°/s]")
        axes[1].set_title("angular velocity")
        axes[1].legend(); axes[1].grid(True, alpha=0.3)
        save_fig(fig, "s07_flip_maneuver")
        plt.close(fig)

    return {"before": before, "after": after, "banner": banner}


if __name__ == "__main__":
    main()
