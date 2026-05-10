"""§2 Successive Convex Programming — before vs after.

Question : does iteratively re-linearising a nonlinear system around
the current reference beat solving a *single* linearisation taken once
at the initial point?

Test problem : a unit-mass point mass with quadratic drag

    ẋ = v,   v̇ = −c·v·|v| + u,    c = 0.05

Goal : bring (x, v) to (20, 0) in 5 s with |u| ≤ 2.

We emulate a convex sub-solver using scipy SLSQP on the *linear model*
only — that way we see the ``linear model ignores drag`` effect
bleeding into the baseline, while SCP iteratively corrects the
reference.

Metrics :
  - final position error        |x(T) − 20|
  - final speed                 |v(T)|
  - iterations                  1 vs. SCP.max_iter
  - convergence history         plotted
"""

from __future__ import annotations

from typing import Tuple

import numpy as np
from scipy.optimize import minimize

from analysis._common import HAS_MPL, save_fig, summary_banner


DT = 0.1
N_STEPS = 50
U_MAX = 2.0
X_TARGET = 20.0
C_DRAG = 0.05


# ----------------------------------------------------------------------
# True nonlinear dynamics (RK4)
# ----------------------------------------------------------------------

def f_nl(x: np.ndarray, u: float) -> np.ndarray:
    return np.array([x[1], -C_DRAG * x[1] * abs(x[1]) + u])


def rollout_nl(u_traj: np.ndarray) -> np.ndarray:
    x = np.zeros(2)
    xs = [x.copy()]
    for u in np.atleast_1d(u_traj).ravel():
        k1 = f_nl(x, u)
        k2 = f_nl(x + 0.5 * DT * k1, u)
        k3 = f_nl(x + 0.5 * DT * k2, u)
        k4 = f_nl(x + DT * k3, u)
        x = x + DT * (k1 + 2 * k2 + 2 * k3 + k4) / 6.0
        xs.append(x.copy())
    return np.array(xs)


# ----------------------------------------------------------------------
# Linearised model (drag is approximated as affine around v_ref)
# ----------------------------------------------------------------------

def linear_cost_and_solve(v_lin: float) -> np.ndarray:
    """Return u_traj* that minimises tracking on the linear model
    ẍ = u − 2·C_drag·|v_lin|·v (with drag derivative evaluated at v_lin)."""
    a = -2.0 * C_DRAG * abs(v_lin)      # ∂(−c|v|v)/∂v ≈ -2c|v|

    def roll(u):
        x = np.zeros(2)
        for uk in u:
            dx = np.array([x[1], a * x[1] + uk])
            x = x + DT * dx
        return x

    def cost(u):
        x_end = roll(u)
        return (x_end[0] - X_TARGET) ** 2 + 4.0 * x_end[1] ** 2 \
            + 0.01 * float(np.sum(u ** 2) * DT)

    u0 = np.zeros(N_STEPS)
    res = minimize(cost, u0, method="SLSQP",
                   bounds=[(-U_MAX, U_MAX)] * N_STEPS,
                   options={"maxiter": 60, "ftol": 1e-4})
    return res.x


def main() -> dict:
    # --- baseline : linearise once around v_lin = 0 (no drag) ----------
    u_base = linear_cost_and_solve(v_lin=0.0)
    x_base = rollout_nl(u_base)
    base_metrics = {
        "final_pos_err":  float(abs(x_base[-1, 0] - X_TARGET)),
        "final_speed":    float(abs(x_base[-1, 1])),
        "control_effort": float(np.sum(u_base ** 2) * DT),
        "iters":          1,
    }

    # --- SCP : re-linearise around the mean |v| of the last rollout ---
    u_iter = u_base.copy()
    x_iter = x_base.copy()
    history = [float(np.linalg.norm(x_iter - 0.0))]
    for k in range(6):
        v_lin = float(np.mean(np.abs(x_iter[:, 1])))
        u_new = linear_cost_and_solve(v_lin=v_lin)
        x_new = rollout_nl(u_new)
        diff = float(np.linalg.norm(x_new - x_iter))
        history.append(diff)
        u_iter, x_iter = u_new, x_new
        if diff < 1e-3:
            break

    after_metrics = {
        "final_pos_err":  float(abs(x_iter[-1, 0] - X_TARGET)),
        "final_speed":    float(abs(x_iter[-1, 1])),
        "control_effort": float(np.sum(u_iter ** 2) * DT),
        "iters":          len(history) - 1,
    }

    banner = summary_banner("§2 Successive Convex Programming",
                             base_metrics, after_metrics)
    print(banner)

    if HAS_MPL:
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(1, 2, figsize=(10, 4))
        t = np.arange(N_STEPS + 1) * DT
        axes[0].plot(t, x_base[:, 0], label="baseline (one-shot linearisation)")
        axes[0].plot(t, x_iter[:, 0], label="SCP (iterated)")
        axes[0].axhline(X_TARGET, color="k", ls="--", lw=0.5, label="target")
        axes[0].set_xlabel("t [s]"); axes[0].set_ylabel("x [m]")
        axes[0].set_title("position tracking")
        axes[0].legend(); axes[0].grid(True, alpha=0.3)

        axes[1].semilogy(range(len(history)), history, "o-")
        axes[1].set_xlabel("SCP iteration")
        axes[1].set_ylabel("‖x^{k+1} − x^k‖")
        axes[1].set_title("SCP convergence")
        axes[1].grid(True, alpha=0.3)
        save_fig(fig, "s02_scp")
        plt.close(fig)

    return {"before": base_metrics, "after": after_metrics, "banner": banner}


if __name__ == "__main__":
    main()
