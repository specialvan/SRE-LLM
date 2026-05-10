"""Animated before-vs-after benefit GIFs for the knowledge base.

Each GIF shows the trajectory / metric evolving through time with two
side-by-side traces: the naive baseline and the article's formulation.
The "data benefit" is visible as a growing gap on the right-hand panel.
"""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

from scripts._asset_common import (ASSET_DIR, COLOR_ACCENT, COLOR_GREEN,
                                    COLOR_INK, COLOR_KEY, COLOR_KEY_SOFT,
                                    COLOR_MUTE, COLOR_RULE, save_gif)


# ---------------------------------------------------------------------------
# §1 Lossless Convexification — descent trajectory
# ---------------------------------------------------------------------------

def gif_01_lossless_convex():
    from starship.lossless_convex import LosslessPDG
    pdg = LosslessPDG(
        r0=np.array([0.0, 0.0, 300.0]),
        v0=np.array([0.0, 0.0, -80.0]),
        m0=250_000.0, T=6.0, N=30)

    # baseline: full throttle all the way
    G_full = np.zeros((pdg.N, 3))
    G_full[:, 2] = pdg.rho2
    r_b, v_b, _ = pdg._dynamics_rollout(G_full)
    # after: solve PDG
    r_a, v_a, _, _ = pdg.solve()

    ts = np.linspace(0, pdg.T, pdg.N + 1)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))

    ax1, ax2 = axes
    ax1.set_title("§1 PDG · 末端高度演化", fontsize=11, color=COLOR_INK)
    ax1.set_xlabel("t [s]"); ax1.set_ylabel("altitude z [m]")
    ax1.axhline(0, color=COLOR_MUTE, lw=0.8, ls="--")
    ax1.set_xlim(0, pdg.T); ax1.set_ylim(-20, 310)
    line_b, = ax1.plot([], [], color=COLOR_ACCENT, lw=2.2,
                        label="baseline (满推力)")
    line_a, = ax1.plot([], [], color=COLOR_KEY, lw=2.2,
                        label="PDG 无损凸化")
    dot_b = ax1.scatter([], [], color=COLOR_ACCENT, s=60, zorder=5)
    dot_a = ax1.scatter([], [], color=COLOR_KEY, s=60, zorder=5)
    ax1.legend(loc="upper right")

    ax2.set_title("末端位置误差收益", fontsize=11, color=COLOR_INK)
    ax2.set_xlabel("t [s]"); ax2.set_ylabel("|z − 0|  [m]")
    ax2.set_xlim(0, pdg.T); ax2.set_yscale("log")
    ax2.set_ylim(1e-1, 400)
    err_b, = ax2.plot([], [], color=COLOR_ACCENT, lw=2.2)
    err_a, = ax2.plot([], [], color=COLOR_KEY, lw=2.2)
    txt = ax2.text(0.02, 0.88, "", transform=ax2.transAxes,
                    fontsize=10, color=COLOR_INK)

    def update(i):
        ii = i + 1
        line_b.set_data(ts[:ii], r_b[:ii, 2])
        line_a.set_data(ts[:ii], r_a[:ii, 2])
        dot_b.set_offsets([[ts[i], r_b[i, 2]]])
        dot_a.set_offsets([[ts[i], r_a[i, 2]]])
        err_b.set_data(ts[:ii], np.abs(r_b[:ii, 2]) + 1e-3)
        err_a.set_data(ts[:ii], np.abs(r_a[:ii, 2]) + 1e-3)
        ratio = (abs(r_b[i, 2]) + 1e-3) / (abs(r_a[i, 2]) + 1e-3)
        txt.set_text(f"t={ts[i]:.2f}s  收益 ×{ratio:.1e}")

    return save_gif(fig, update, pdg.N + 1, "s01_benefit", fps=8)


# ---------------------------------------------------------------------------
# §2 SCP — trust-region iterations
# ---------------------------------------------------------------------------

def gif_02_scp():
    # 1-D drag system: ẋ=v, v̇=-c·v·|v|+u, target x=20
    DT = 0.1; N = 50
    C = 0.05; U_MAX = 2.0; TARGET = 20.0

    def rollout(u_traj):
        x = np.zeros(2); xs = [x.copy()]
        for u in u_traj:
            for _ in range(4):
                k1 = np.array([x[1], -C*x[1]*abs(x[1]) + u])
                x = x + (DT/4) * k1
            xs.append(x.copy())
        return np.array(xs)

    def solve_linear(v_lin):
        from scipy.optimize import minimize
        a = -2.0 * C * abs(v_lin)
        def roll(u):
            x = np.zeros(2)
            for uk in u:
                x = x + DT * np.array([x[1], a*x[1]+uk])
            return x
        def cost(u):
            x_end = roll(u)
            return (x_end[0]-TARGET)**2 + 4*x_end[1]**2 + 0.01*np.sum(u**2)*DT
        u0 = np.zeros(N)
        res = minimize(cost, u0, method="SLSQP",
                        bounds=[(-U_MAX, U_MAX)] * N,
                        options={"maxiter": 40})
        return res.x

    iterates = []
    v_lin = 0.0
    u = solve_linear(v_lin)
    x = rollout(u)
    iterates.append(x)
    for _ in range(5):
        v_lin = float(np.mean(np.abs(x[:, 1])))
        u = solve_linear(v_lin)
        x = rollout(u)
        iterates.append(x)

    ts = np.arange(N + 1) * DT
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
    ax1.set_title("§2 SCP · 位置轨迹随迭代逼近目标",
                   fontsize=11, color=COLOR_INK)
    ax1.set_xlabel("t [s]"); ax1.set_ylabel("x [m]")
    ax1.set_xlim(0, N * DT); ax1.set_ylim(-1, 25)
    ax1.axhline(TARGET, color=COLOR_GREEN, lw=1, ls="--")
    ax1.text(N * DT - 0.2, TARGET + 0.4, "目标 x=20",
              color=COLOR_GREEN, fontsize=9, ha="right")
    line, = ax1.plot([], [], color=COLOR_KEY, lw=2.2)
    iter_txt = ax1.text(0.02, 0.92, "", transform=ax1.transAxes,
                         fontsize=11, color=COLOR_INK, fontweight="bold")

    ax2.set_title("‖x^{k+1} − x^k‖ 收敛", fontsize=11, color=COLOR_INK)
    ax2.set_xlabel("iteration"); ax2.set_ylabel("‖Δx‖")
    ax2.set_yscale("log")
    diffs = [float(np.linalg.norm(iterates[k+1] - iterates[k]))
             for k in range(len(iterates) - 1)]
    ax2.set_xlim(1, len(diffs) + 0.1)
    ax2.set_ylim(max(min(diffs)*0.5, 1e-4), max(diffs)*1.5)
    bars = ax2.plot([], [], color=COLOR_ACCENT, marker="o", lw=1.8)[0]

    total_frames = len(iterates) * 6   # hold each iterate for 6 frames

    def update(i):
        k = min(i // 6, len(iterates) - 1)
        line.set_data(ts, iterates[k][:, 0])
        line.set_color(COLOR_ACCENT if k == 0 else COLOR_KEY)
        label = "baseline (one-shot)" if k == 0 else f"SCP iter {k}"
        iter_txt.set_text(label)
        if k >= 1:
            xs = np.arange(1, k + 1)
            bars.set_data(xs, diffs[:k])

    return save_gif(fig, update, total_frames, "s02_benefit", fps=6)


# ---------------------------------------------------------------------------
# §3 Rigid body — attitude error growth
# ---------------------------------------------------------------------------

def gif_03_rigid_body():
    from scipy.spatial.transform import Rotation
    from starship.quaternion import Quaternion, integrate_quaternion

    w = np.array([0.1, 0.1, 0.0])
    ts = np.linspace(0, 5.0, 80)
    dt = ts[1] - ts[0]

    # Ground truth (analytical)
    R_truth = [Rotation.from_rotvec(w * t).as_matrix() for t in ts]

    # Baseline: Euler small-angle integration
    R_base = []; euler = np.zeros(3)
    for _ in ts:
        R_base.append(Rotation.from_euler("xyz", euler).as_matrix())
        euler = euler + w * dt

    # After: quaternion exponential integration
    R_quat = []; q = np.array([1.0, 0, 0, 0])
    for _ in ts:
        R_quat.append(Quaternion.from_array(q).to_matrix())
        q = integrate_quaternion(q, w, dt)

    def angle_err(R1, R2):
        R_rel = R1.T @ R2
        trace = np.clip((np.trace(R_rel) - 1) / 2, -1, 1)
        return float(np.arccos(trace))

    err_base = np.array([angle_err(rt, rb)
                          for rt, rb in zip(R_truth, R_base)])
    err_quat = np.array([angle_err(rt, rq)
                          for rt, rq in zip(R_truth, R_quat)])

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.5, 4.2))

    ax1.set_title("§3 姿态 · body z-axis 的指向演化",
                   fontsize=11, color=COLOR_INK)
    ax1.set_xlim(-1.2, 1.2); ax1.set_ylim(-1.2, 1.2)
    ax1.set_aspect("equal")
    ax1.set_xticks([]); ax1.set_yticks([])
    ax1.spines[:].set_visible(False)
    ax1.add_patch(mpatches.Circle((0, 0), 1.0, fill=False,
                                    edgecolor=COLOR_RULE, linewidth=1))
    arrow_truth = ax1.annotate("", xy=(0, 1), xytext=(0, 0),
        arrowprops=dict(arrowstyle="-|>", color=COLOR_GREEN, lw=2))
    arrow_base = ax1.annotate("", xy=(0, 1), xytext=(0, 0),
        arrowprops=dict(arrowstyle="-|>", color=COLOR_ACCENT, lw=2))
    arrow_quat = ax1.annotate("", xy=(0, 1), xytext=(0, 0),
        arrowprops=dict(arrowstyle="-|>", color=COLOR_KEY, lw=2))
    ax1.text(-1.15, 1.05, "● truth", color=COLOR_GREEN, fontsize=9)
    ax1.text(-1.15, 0.95, "● Euler 积分", color=COLOR_ACCENT, fontsize=9)
    ax1.text(-1.15, 0.85, "● quaternion", color=COLOR_KEY, fontsize=9)

    ax2.set_title("姿态误差（°）", fontsize=11, color=COLOR_INK)
    ax2.set_xlabel("t [s]"); ax2.set_ylabel("|attitude error| [°]")
    ax2.set_xlim(0, ts[-1]); ax2.set_ylim(0, np.rad2deg(err_base.max())*1.1)
    line_b, = ax2.plot([], [], color=COLOR_ACCENT, lw=2.2, label="Euler")
    line_q, = ax2.plot([], [], color=COLOR_KEY, lw=2.2, label="quaternion")
    ax2.legend()

    def update(i):
        zt = R_truth[i] @ np.array([0, 0, 1.0])
        zb = R_base[i] @ np.array([0, 0, 1.0])
        zq = R_quat[i] @ np.array([0, 0, 1.0])
        # Project onto the (x, z) plane for 2-D viz
        arrow_truth.set_position((0, 0)); arrow_truth.xy = (zt[0], zt[2])
        arrow_base.set_position((0, 0));  arrow_base.xy = (zb[0], zb[2])
        arrow_quat.set_position((0, 0));  arrow_quat.xy = (zq[0], zq[2])
        line_b.set_data(ts[:i+1], np.rad2deg(err_base[:i+1]))
        line_q.set_data(ts[:i+1], np.rad2deg(err_quat[:i+1]))

    return save_gif(fig, update, len(ts), "s03_benefit", fps=15)


# ---------------------------------------------------------------------------
# §4 Cone filter — sample stream
# ---------------------------------------------------------------------------

def gif_04_cone():
    from starship.thrust_constraints import (ConeQPFilter,
                                              pointing_cone_constraint)
    rng = np.random.default_rng(1)
    T_max = 2.3e6
    theta_max = np.deg2rad(15.0)
    n_hat = np.array([0.0, 0.0, 1.0])
    filt = ConeQPFilter(n_hat=n_hat, theta_max=theta_max, T_max=T_max)

    N = 120
    U = rng.uniform(-3e6, 3e6, size=(N, 3))
    U[:, 2] += 1.5e6
    U_f = np.array([filt.filter(u) for u in U])

    # Project to (|u_xy|, u_z)
    uxy_b = np.linalg.norm(U[:, :2], axis=1)
    uxy_a = np.linalg.norm(U_f[:, :2], axis=1)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.5, 4.4))

    ax1.set_title("§4 锥+球投影 · 候选推力分布",
                   fontsize=11, color=COLOR_INK)
    ax1.set_xlabel("‖u_xy‖  [N]"); ax1.set_ylabel("u_z  [N]")
    ax1.set_xlim(0, 3.5e6); ax1.set_ylim(-1e6, 3.5e6)
    # cone & ball boundaries
    zz = np.linspace(0, T_max, 100)
    ax1.plot(zz * np.tan(theta_max), zz, "k--", lw=0.8)
    arc_t = np.linspace(-np.pi/2, np.pi/2, 200)
    ax1.plot(T_max * np.cos(arc_t), T_max * np.sin(arc_t),
              "k:", lw=0.8)
    sc_b = ax1.scatter([], [], s=20, c=COLOR_ACCENT, alpha=0.7,
                        label="u_nom")
    sc_a = ax1.scatter([], [], s=20, c=COLOR_KEY, alpha=0.7,
                        label="u⋆ (filter)")
    ax1.legend(loc="upper right")

    ax2.set_title("累计违规率", fontsize=11, color=COLOR_INK)
    ax2.set_xlabel("样本数"); ax2.set_ylabel("违规样本占比")
    ax2.set_xlim(0, N); ax2.set_ylim(0, 1.05)
    line_b, = ax2.plot([], [], color=COLOR_ACCENT, lw=2.2,
                       label="baseline")
    line_a, = ax2.plot([], [], color=COLOR_KEY, lw=2.2,
                       label="filter")
    ax2.legend(loc="upper right")

    def violated(u):
        return pointing_cone_constraint(u, n_hat, theta_max) < -1e-4 \
            or np.linalg.norm(u) > T_max + 1e-6

    viol_b = np.cumsum([violated(u) for u in U])
    viol_a = np.cumsum([violated(u) for u in U_f])

    def update(i):
        sc_b.set_offsets(np.column_stack([uxy_b[:i+1], U[:i+1, 2]]))
        sc_a.set_offsets(np.column_stack([uxy_a[:i+1], U_f[:i+1, 2]]))
        xs = np.arange(1, i + 2)
        line_b.set_data(xs, viol_b[:i+1] / xs)
        line_a.set_data(xs, viol_a[:i+1] / xs)

    return save_gif(fig, update, N, "s04_benefit", fps=15)


# ---------------------------------------------------------------------------
# §5 EKF — error trajectories
# ---------------------------------------------------------------------------

def gif_05_ekf():
    import analysis.s05_ekf as s5
    from starship.ekf import EKF, MultiSensorEKF, RadarMeasurement

    rng = np.random.default_rng(0)
    r0 = np.array([0, 0, 1500.0]); v0 = np.array([20, 0, -60.0])
    N = int(s5.T_FINAL / s5.DT)
    truth_r = np.zeros((N+1, 3)); truth_v = np.zeros((N+1, 3))
    truth_r[0], truth_v[0] = r0, v0
    for k in range(N):
        truth_v[k+1] = truth_v[k] + s5.G * s5.DT
        truth_r[k+1] = truth_r[k] + truth_v[k] * s5.DT + 0.5 * s5.G * s5.DT * s5.DT

    radar = RadarMeasurement(R=np.diag([40.0**2, 5e-3**2, 5e-3**2]))
    radar_z = []
    for k in range(N+1):
        x_true = np.concatenate([truth_r[k], truth_v[k],
                                  [1, 0, 0, 0], [0, 0, 0]])
        radar_z.append(radar.h(x_true) +
                        rng.multivariate_normal(np.zeros(3), radar.R))

    def xyz(z):
        r_, a_, e_ = z
        return np.array([r_*np.cos(e_)*np.cos(a_),
                          r_*np.cos(e_)*np.sin(a_),
                          r_*np.sin(e_)])
    base_r = np.array([xyz(z) for z in radar_z])
    base_v = np.zeros_like(base_r)
    base_v[1:] = (base_r[1:] - base_r[:-1]) / s5.DT

    init_v = (base_r[1] - base_r[0]) / s5.DT
    ekf = EKF(x=np.concatenate([base_r[0], init_v]),
              P=np.diag([80**2]*3 + [30**2]*3),
              process_noise=np.diag([1e-2]*3 + [1.0]*3),
              f=s5.dynamics, F_jac=s5.F_jac)

    class A:
        R = radar.R
        def h(self, x): return radar.h(np.concatenate([x[0:3], x[3:6]]))
        def H(self, x): return radar.H(np.concatenate(
            [x[0:3], x[3:6], np.zeros(7)]))[:, 0:6]

    fused = MultiSensorEKF(ekf)
    est_r = np.zeros_like(base_r); est_r[0] = ekf.x[0:3]
    est_v = np.zeros_like(base_r); est_v[0] = ekf.x[3:6]
    for k in range(N):
        fused.step(np.zeros(0), s5.DT, [(A(), radar_z[k+1])])
        est_r[k+1] = ekf.x[0:3]; est_v[k+1] = ekf.x[3:6]

    ts = np.arange(N+1) * s5.DT
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.2))

    ax1.set_title("§5 EKF · 位置误差 (m)", fontsize=11, color=COLOR_INK)
    ax1.set_xlabel("t [s]"); ax1.set_ylabel("‖Δr‖  [m]")
    ax1.set_xlim(0, ts[-1])
    ax1.set_ylim(0, max(200, float(np.linalg.norm(
        base_r - truth_r, axis=1).max()) * 1.1))
    line_b, = ax1.plot([], [], color=COLOR_ACCENT, lw=2.0,
                        label="raw radar")
    line_a, = ax1.plot([], [], color=COLOR_KEY, lw=2.2,
                        label="EKF")
    ax1.legend()

    ax2.set_title("速度误差 (m/s)", fontsize=11, color=COLOR_INK)
    ax2.set_xlabel("t [s]"); ax2.set_ylabel("‖Δv‖  [m/s]")
    ax2.set_xlim(0, ts[-1])
    max_vel_err = max(float(np.linalg.norm(base_v - truth_v, axis=1).max()), 100)
    ax2.set_ylim(0, max_vel_err * 1.1)
    line_vb, = ax2.plot([], [], color=COLOR_ACCENT, lw=2.0,
                        label="finite-diff")
    line_va, = ax2.plot([], [], color=COLOR_KEY, lw=2.2,
                        label="EKF")
    ax2.legend()

    err_pos_b = np.linalg.norm(base_r - truth_r, axis=1)
    err_pos_a = np.linalg.norm(est_r - truth_r, axis=1)
    err_v_b   = np.linalg.norm(base_v - truth_v, axis=1)
    err_v_a   = np.linalg.norm(est_v - truth_v, axis=1)

    def update(i):
        line_b.set_data(ts[:i+1], err_pos_b[:i+1])
        line_a.set_data(ts[:i+1], err_pos_a[:i+1])
        line_vb.set_data(ts[:i+1], err_v_b[:i+1])
        line_va.set_data(ts[:i+1], err_v_a[:i+1])

    return save_gif(fig, update, len(ts), "s05_benefit", fps=12)


# ---------------------------------------------------------------------------
# §6 MPC — tracking response with disturbance
# ---------------------------------------------------------------------------

def gif_06_mpc():
    import analysis.s06_mpc as s6
    from starship.mpc import LinearDiscretizer, QuadraticMPC

    DT = 0.1; N_total = 100
    A = np.array([[0.0, 1.0], [0.0, 0.0]])
    B = np.array([[0.0], [1.0]])
    Ad, Bd = LinearDiscretizer(A, B).zoh(DT)

    ref = np.zeros((N_total + 1, 2))
    ref[int(1.0/DT):, 0] = 5.0

    x_b = np.zeros(2); xs_b = [x_b.copy()]; us_b = []
    x_a = np.zeros(2); xs_a = [x_a.copy()]; us_a = []

    Kp, Kd = 0.9, 1.2
    mpc = QuadraticMPC(A=Ad, B=Bd,
                       Q=np.diag([10.0, 1.0]), R=np.eye(1)*0.05,
                       P=np.diag([100.0, 10.0]),
                       N=15,
                       u_min=np.array([-1.0]), u_max=np.array([1.0]))
    for k in range(N_total):
        e = ref[k] - x_b
        u_b = float(np.clip(Kp*e[0] + Kd*e[1], -1, 1))
        d = -2.0 if 3.9 < k*DT < 4.1 else 0.0
        x_b = Ad @ x_b + Bd.flatten() * u_b; x_b[1] += d*DT
        xs_b.append(x_b.copy()); us_b.append(u_b)

        u_a = float(mpc.step(x_a - ref[k])[0])
        x_a = Ad @ x_a + Bd.flatten() * u_a; x_a[1] += d*DT
        xs_a.append(x_a.copy()); us_a.append(u_a)

    xs_b = np.array(xs_b); xs_a = np.array(xs_a)
    ts = np.arange(N_total + 1) * DT

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.2))
    ax1.set_title("§6 MPC · 跟踪响应", fontsize=11, color=COLOR_INK)
    ax1.set_xlabel("t [s]"); ax1.set_ylabel("position")
    ax1.set_xlim(0, ts[-1]); ax1.set_ylim(-0.5, 6)
    ax1.plot(ts, ref[:, 0], color=COLOR_GREEN, lw=1.2, ls="--",
              label="reference")
    ax1.axvline(4.0, color="#caa96a", lw=0.8, ls=":",
                 label="disturbance")
    line_b, = ax1.plot([], [], color=COLOR_ACCENT, lw=2.0, label="PD")
    line_a, = ax1.plot([], [], color=COLOR_KEY, lw=2.2, label="MPC")
    ax1.legend(loc="lower right")

    ax2.set_title("误差演化", fontsize=11, color=COLOR_INK)
    ax2.set_xlabel("t [s]"); ax2.set_ylabel("|x − ref|")
    ax2.set_xlim(0, ts[-1]); ax2.set_ylim(0, 5.5)
    err_b = np.abs(xs_b[:, 0] - ref[:, 0])
    err_a = np.abs(xs_a[:, 0] - ref[:, 0])
    el_b, = ax2.plot([], [], color=COLOR_ACCENT, lw=2.0)
    el_a, = ax2.plot([], [], color=COLOR_KEY, lw=2.2)

    def update(i):
        line_b.set_data(ts[:i+1], xs_b[:i+1, 0])
        line_a.set_data(ts[:i+1], xs_a[:i+1, 0])
        el_b.set_data(ts[:i+1], err_b[:i+1])
        el_a.set_data(ts[:i+1], err_a[:i+1])

    return save_gif(fig, update, N_total + 1, "s06_benefit", fps=14)


# ---------------------------------------------------------------------------
# §7 Flip — attitude evolution
# ---------------------------------------------------------------------------

def gif_07_flip():
    from starship.flip_maneuver import FlipPlanner

    I = 1.0e8
    tau_max = 6.0e7
    planner = FlipPlanner(I_xx=I, tau_max=tau_max,
                           theta_start=np.pi/2, theta_end=0.0)
    t_bb, th_bb, om_bb = planner.plan(dt=0.05)
    T_total = float(t_bb[-1])
    n_frames = len(t_bb)

    # baseline: constant 30% torque
    tau_avg = 0.3 * tau_max
    dt = 0.05
    N = n_frames
    t_b = np.linspace(0, T_total, N)
    omega_b = np.zeros(N); theta_b = np.zeros(N); theta_b[0] = np.pi/2
    for k in range(N - 1):
        omega_b[k+1] = omega_b[k] + (tau_avg/I) * (t_b[k+1] - t_b[k])
        theta_b[k+1] = theta_b[k] - omega_b[k+1] * (t_b[k+1] - t_b[k])

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.3))

    ax1.set_title("§7 Flip · 箭体姿态 (俯视 xz 平面)",
                   fontsize=11, color=COLOR_INK)
    ax1.set_xlim(-1.5, 1.5); ax1.set_ylim(-1.5, 1.5)
    ax1.set_aspect("equal"); ax1.set_xticks([]); ax1.set_yticks([])
    for s in ax1.spines.values(): s.set_visible(False)
    arrow_b = ax1.annotate("", xy=(0, 1), xytext=(0, 0),
        arrowprops=dict(arrowstyle="-|>", color=COLOR_ACCENT, lw=2.5))
    arrow_a = ax1.annotate("", xy=(0, 1), xytext=(0, 0),
        arrowprops=dict(arrowstyle="-|>", color=COLOR_KEY, lw=2.5))
    ax1.text(-1.4, 1.35, "● baseline 恒定 0.3·τ_max", color=COLOR_ACCENT, fontsize=9)
    ax1.text(-1.4, 1.2,  "● bang-bang (planner)", color=COLOR_KEY, fontsize=9)
    ax1.text(-1.4, -1.4, "目标：俯仰 0°", color=COLOR_GREEN, fontsize=9)

    ax2.set_title("pitch 角（°）", fontsize=11, color=COLOR_INK)
    ax2.set_xlabel("t [s]"); ax2.set_ylabel("pitch θ  [°]")
    ax2.set_xlim(0, T_total); ax2.set_ylim(-10, 100)
    ax2.axhline(0, color=COLOR_GREEN, lw=1, ls="--")
    line_b, = ax2.plot([], [], color=COLOR_ACCENT, lw=2.0)
    line_a, = ax2.plot([], [], color=COLOR_KEY, lw=2.2)

    def update(i):
        # baseline direction
        th_baseline = theta_b[i]
        th_after = th_bb[i]
        arrow_b.set_position((0, 0))
        arrow_b.xy = (np.sin(th_baseline), np.cos(th_baseline))
        arrow_a.set_position((0, 0))
        arrow_a.xy = (np.sin(th_after), np.cos(th_after))
        line_b.set_data(t_b[:i+1], np.rad2deg(theta_b[:i+1]))
        line_a.set_data(t_bb[:i+1], np.rad2deg(th_bb[:i+1]))

    return save_gif(fig, update, n_frames, "s07_benefit", fps=14)


# ---------------------------------------------------------------------------
# §8 Catch allocation — violations over stream
# ---------------------------------------------------------------------------

def gif_08_catch():
    from starship.catch_controller import ThrustAllocator
    from starship.types import Thruster, ThrusterBank

    th = []
    R = 3.2
    for i in range(3):
        a = i * 2*np.pi/3
        th.append(Thruster(
            position=np.array([R*np.cos(a), R*np.sin(a), 0]),
            direction=np.array([0, 0, 1.0]),
            T_min=0.4e6, T_max=2.3e6))
    bank = ThrusterBank(th)
    allocator = ThrustAllocator(bank)
    A = bank.geometry_matrix()
    lb = np.array([t.T_min for t in bank])
    ub = np.array([t.T_max for t in bank])

    rng = np.random.default_rng(0)
    N = 120
    Fs = np.stack([rng.normal([0,0,5e6], [2e5,2e5,1e6]) for _ in range(N)])
    taus = rng.normal(0, 2e6, size=(N, 3))

    viol_b = np.zeros(N); viol_a = np.zeros(N)
    res_b = np.zeros(N); res_a = np.zeros(N)
    for i, (F, tau) in enumerate(zip(Fs, taus)):
        demand = np.concatenate([F, tau])
        # Baseline: pinv (unbounded)
        t_base = np.linalg.pinv(A) @ demand
        res_b[i] = np.linalg.norm(A @ t_base - demand)
        viol_b[i] = max(0.0, float(np.max(
            np.concatenate([t_base - ub, lb - t_base]))))
        # After
        t_opt, r = allocator.allocate(F, tau)
        res_a[i] = r
        viol_a[i] = max(0.0, float(np.max(
            np.concatenate([t_opt - ub, lb - t_opt]))))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.3))

    ax1.set_title("§8 Catch · 推力器饱和违规占比",
                   fontsize=11, color=COLOR_INK)
    ax1.set_xlabel("样本 index"); ax1.set_ylabel("累计违规占比")
    ax1.set_xlim(0, N); ax1.set_ylim(0, 1.05)
    line_b, = ax1.plot([], [], color=COLOR_ACCENT, lw=2.0,
                        label="pinv")
    line_a, = ax1.plot([], [], color=COLOR_KEY, lw=2.2,
                        label="bounded LS")
    ax1.legend()

    ax2.set_title("分配残差 ‖A·t − demand‖", fontsize=11, color=COLOR_INK)
    ax2.set_xlabel("样本 index"); ax2.set_ylabel("residual  [N·m]")
    ax2.set_xlim(0, N)
    ax2.set_ylim(0, max(res_b.max(), res_a.max()) * 1.1)
    r_b, = ax2.plot([], [], color=COLOR_ACCENT, lw=2.0)
    r_a, = ax2.plot([], [], color=COLOR_KEY, lw=2.2)

    cum_b = np.cumsum((viol_b > 1e-6).astype(float))
    cum_a = np.cumsum((viol_a > 1e-6).astype(float))

    def update(i):
        xs = np.arange(1, i + 2)
        line_b.set_data(xs, cum_b[:i+1] / xs)
        line_a.set_data(xs, cum_a[:i+1] / xs)
        r_b.set_data(np.arange(i+1), res_b[:i+1])
        r_a.set_data(np.arange(i+1), res_a[:i+1])

    return save_gif(fig, update, N, "s08_benefit", fps=15)


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------

def main():
    print("building §1 ...");  gif_01_lossless_convex()
    print("building §2 ...");  gif_02_scp()
    print("building §3 ...");  gif_03_rigid_body()
    print("building §4 ...");  gif_04_cone()
    print("building §5 ...");  gif_05_ekf()
    print("building §6 ...");  gif_06_mpc()
    print("building §7 ...");  gif_07_flip()
    print("building §8 ...");  gif_08_catch()
    print("benefit GIFs written to:", ASSET_DIR)


if __name__ == "__main__":
    main()
