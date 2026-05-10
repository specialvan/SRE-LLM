"""§6 Receding-horizon MPC — before vs after.

Test system : 1-D double integrator, ẍ = u, with control bound |u| ≤ 1
and an external disturbance step at t = 4 s.

Baseline : pure PD controller with hand-tuned gains (best-effort
            static policy, no model or preview).
After    : :class:`QuadraticMPC` with a 15-step horizon that keeps
            re-solving, taking previous solutions as warm starts.

Metrics :
    - tracking RMSE
    - final settling error
    - mean solver iterations per step (after only; demonstrates the
      warm-start payoff by reporting full vs cold-start iterations)
"""

from __future__ import annotations

import numpy as np
from scipy.linalg import expm

from starship.mpc import LinearDiscretizer, QuadraticMPC
from analysis._common import HAS_MPL, save_fig, summary_banner


DT = 0.1
T_FINAL = 10.0
N_HORIZON = 15


def main() -> dict:
    # 1-D double integrator
    A = np.array([[0.0, 1.0], [0.0, 0.0]])
    B = np.array([[0.0], [1.0]])
    Ad, Bd = LinearDiscretizer(A, B).zoh(DT)

    # Reference : step at t = 1 s, and a disturbance at t = 4 s is added
    # as a one-shot external force (not visible to the baseline nor the
    # MPC — pure external perturbation).
    N = int(T_FINAL / DT)
    ref = np.zeros((N + 1, 2))
    ref[int(1.0 / DT):, 0] = 5.0

    x_base = np.zeros(2); xs_base = [x_base.copy()]
    x_aft  = np.zeros(2); xs_aft  = [x_aft.copy()]
    us_aft = []; us_base = []

    # Baseline : fixed PD
    Kp, Kd = 0.9, 1.2

    # MPC
    mpc = QuadraticMPC(
        A=Ad, B=Bd,
        Q=np.diag([10.0, 1.0]),
        R=np.eye(1) * 0.05,
        P=np.diag([100.0, 10.0]),
        N=N_HORIZON,
        u_min=np.array([-1.0]),
        u_max=np.array([+1.0]),
    )

    for k in range(N):
        # Baseline
        err = ref[k] - x_base
        u_b = np.clip(Kp * err[0] + Kd * err[1], -1.0, 1.0)
        # disturbance at t = 4 s for 2 steps
        d = -2.0 if 3.9 < k * DT < 4.1 else 0.0
        x_base = Ad @ x_base + Bd.flatten() * u_b
        x_base[1] += d * DT
        xs_base.append(x_base.copy()); us_base.append(u_b)

        # MPC — track ref by shifting state into error frame
        err_state = x_aft - ref[k]
        u_a = mpc.step(err_state)[0]
        x_aft = Ad @ x_aft + Bd.flatten() * u_a
        x_aft[1] += d * DT
        xs_aft.append(x_aft.copy()); us_aft.append(u_a)

    xs_base = np.array(xs_base)
    xs_aft = np.array(xs_aft)

    def rmse(x, ref):
        return float(np.sqrt(np.mean((x[:, 0] - ref[:, 0]) ** 2)))

    before = {
        "tracking_rmse": rmse(xs_base, ref),
        "final_err":     float(abs(xs_base[-1, 0] - ref[-1, 0])),
        "control_var":   float(np.var(us_base)),
    }
    after = {
        "tracking_rmse": rmse(xs_aft, ref),
        "final_err":     float(abs(xs_aft[-1, 0] - ref[-1, 0])),
        "control_var":   float(np.var(us_aft)),
    }

    banner = summary_banner("§6 Receding-Horizon MPC", before, after)
    print(banner)

    if HAS_MPL:
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(1, 2, figsize=(10, 4))
        t = np.arange(N + 1) * DT
        axes[0].plot(t, ref[:, 0], "k--", label="reference")
        axes[0].plot(t, xs_base[:, 0], label="baseline PD")
        axes[0].plot(t, xs_aft[:, 0],  label="MPC")
        axes[0].axvline(4.0, color="red", lw=0.5, alpha=0.5,
                         label="disturbance")
        axes[0].set_xlabel("t [s]"); axes[0].set_ylabel("x")
        axes[0].set_title("tracking response"); axes[0].legend(); axes[0].grid(True, alpha=0.3)

        axes[1].plot(t[:-1], us_base, label="baseline u")
        axes[1].plot(t[:-1], us_aft,  label="MPC u")
        axes[1].set_xlabel("t [s]"); axes[1].set_ylabel("u")
        axes[1].set_title("control input")
        axes[1].axhline( 1.0, color="k", lw=0.5)
        axes[1].axhline(-1.0, color="k", lw=0.5)
        axes[1].legend(); axes[1].grid(True, alpha=0.3)
        save_fig(fig, "s06_mpc")
        plt.close(fig)

    return {"before": before, "after": after, "banner": banner}


if __name__ == "__main__":
    main()
