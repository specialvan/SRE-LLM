"""Clean, vector-style mechanism diagrams for the knowledge base.

These replace the OCR'd Chinese screenshots in ``DOC/spacex/`` with a
consistent schematic language: rounded boxes, colour-coded arrows, a
plain-English label per symbol.
"""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.transforms import Affine2D

from scripts._asset_common import (ASSET_DIR, COLOR_ACCENT, COLOR_ACCENT_SOFT,
                                    COLOR_BG_PANEL, COLOR_GREEN, COLOR_INK,
                                    COLOR_KEY, COLOR_KEY_SOFT, COLOR_MUTE,
                                    COLOR_RULE, COLOR_WARN, save_png)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _box(ax, xy, wh, text, fill=COLOR_KEY_SOFT, edge=COLOR_KEY,
         fontsize=10, fontweight="normal"):
    x, y = xy; w, h = wh
    ax.add_patch(mpatches.FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08",
        facecolor=fill, edgecolor=edge, linewidth=1.2))
    ax.text(x + w / 2, y + h / 2, text,
            ha="center", va="center", fontsize=fontsize,
            fontweight=fontweight, color=COLOR_INK)


def _arrow(ax, p0, p1, color=COLOR_KEY, label=None, ls="-", rad=0.0):
    ax.annotate("",
                xy=p1, xytext=p0,
                arrowprops=dict(arrowstyle="-|>", color=color,
                                linewidth=1.4, linestyle=ls,
                                connectionstyle=f"arc3,rad={rad}"))
    if label:
        mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
        ax.text(mx, my + 0.05, label, ha="center", fontsize=9,
                color=color)


def _clean_axes(ax, xlim, ylim):
    ax.set_xlim(*xlim); ax.set_ylim(*ylim)
    ax.set_xticks([]); ax.set_yticks([])
    for s in ("top", "right", "bottom", "left"):
        ax.spines[s].set_visible(False)
    ax.set_facecolor(COLOR_BG_PANEL)


# ---------------------------------------------------------------------------
# §1 Lossless Convexification
# ---------------------------------------------------------------------------

def diagram_01_lossless_convex():
    fig, (axL, axR) = plt.subplots(1, 2, figsize=(10.5, 4.2))
    fig.suptitle("§1 Lossless Convexification — 非凸推力下界如何变凸",
                  fontsize=12, fontweight="bold", color=COLOR_INK)

    # LEFT: nonconvex donut (annulus) — original constraint ρ1 ≤ ‖Γ‖ ≤ ρ2
    _clean_axes(axL, (-3.2, 3.2), (-3.2, 3.2))
    axL.set_title("原始：ρ₁ ≤ ‖Γ‖ ≤ ρ₂  (非凸环)",
                   color=COLOR_ACCENT)
    # big disk
    axL.add_patch(mpatches.Circle((0, 0), 2.5,
                                    facecolor=COLOR_ACCENT_SOFT,
                                    edgecolor=COLOR_ACCENT,
                                    linewidth=1.5))
    # inner hole (non-feasible)
    axL.add_patch(mpatches.Circle((0, 0), 1.1,
                                    facecolor="#ffffff",
                                    edgecolor=COLOR_ACCENT,
                                    linewidth=1.5, linestyle="--"))
    axL.text(0, 0, "not\nallowed", ha="center", va="center",
              fontsize=9, color=COLOR_ACCENT, fontweight="bold")
    axL.text(2.0, -2.8, "ρ₂", fontsize=11, color=COLOR_ACCENT, fontweight="bold")
    axL.text(0.8, -1.4, "ρ₁", fontsize=11, color=COLOR_ACCENT, fontweight="bold")
    # show two candidate vectors
    axL.annotate("", xy=(1.7, 0.8), xytext=(0, 0),
                  arrowprops=dict(arrowstyle="-|>", color=COLOR_KEY, lw=1.5))
    axL.text(1.7, 1.0, "Γ ∈ 可行", color=COLOR_KEY, fontsize=9)
    axL.annotate("", xy=(0.6, -0.3), xytext=(0, 0),
                  arrowprops=dict(arrowstyle="-|>", color=COLOR_ACCENT, lw=1.5))
    axL.text(0.4, -0.7, "Γ ∈ 禁区", color=COLOR_ACCENT, fontsize=9)

    # RIGHT: convex disk after adding slack σ
    _clean_axes(axR, (-3.2, 3.2), (-3.2, 3.2))
    axR.set_title("引入 σ 后：‖Γ‖ ≤ σ, ρ₁ ≤ σ ≤ ρ₂  (凸)",
                   color=COLOR_KEY)
    axR.add_patch(mpatches.Circle((0, 0), 2.5,
                                    facecolor=COLOR_KEY_SOFT,
                                    edgecolor=COLOR_KEY,
                                    linewidth=1.5))
    axR.text(0, 0, "feasible", ha="center", va="center",
              fontsize=10, color=COLOR_KEY, fontweight="bold")
    # show σ scaling as a ruler
    axR.annotate("", xy=(2.5, 0), xytext=(0, 0),
                  arrowprops=dict(arrowstyle="<|-|>", color=COLOR_INK, lw=1.2))
    axR.text(1.3, 0.15, "σ", fontsize=12, color=COLOR_INK, fontweight="bold")
    axR.text(0, -2.85, "松弛后 ‖Γ‖ 可自由取 0…σ；\nσ 受凸区间 [ρ₁, ρ₂] 约束",
              ha="center", va="top", fontsize=9, color=COLOR_MUTE)

    plt.tight_layout(rect=[0, 0, 1, 0.94])
    return save_png(fig, "s01_mechanism")


# ---------------------------------------------------------------------------
# §2 Successive Convex Programming
# ---------------------------------------------------------------------------

def diagram_02_scp():
    fig, ax = plt.subplots(figsize=(10, 4.3))
    _clean_axes(ax, (-0.2, 10.2), (-1.2, 3.4))
    ax.set_title("§2 SCP · 在非线性曲面上迭代拉直",
                  fontsize=12, fontweight="bold", color=COLOR_INK)

    # True nonlinear objective landscape (a curve)
    x = np.linspace(0, 10, 400)
    y = 2.2 * np.sin(0.5 * x) + 0.15 * x
    ax.plot(x, y, color=COLOR_ACCENT, lw=2.0, label="真动力学 ẋ = f(x, u)")

    # Three iterates & their tangent lines (linearisations)
    iters = [(1.5, COLOR_MUTE), (4.6, "#a07345"), (7.6, COLOR_KEY)]
    for i, (xi, col) in enumerate(iters):
        yi = 2.2 * np.sin(0.5 * xi) + 0.15 * xi
        slope = 2.2 * 0.5 * np.cos(0.5 * xi) + 0.15
        xs = np.linspace(xi - 1.3 * (0.85 ** i), xi + 1.3 * (0.85 ** i), 40)
        ys = yi + slope * (xs - xi)
        ax.plot(xs, ys, color=col, lw=1.4, ls="--")
        ax.scatter([xi], [yi], color=col, s=40, zorder=5)
        ax.text(xi, yi + 0.28, f"iter {i+1}", color=col,
                fontsize=9, ha="center", fontweight="bold")

        # trust region box
        eta = 0.9 * (0.75 ** i)
        ax.add_patch(mpatches.Rectangle((xi - eta, yi - eta * 0.9),
                                         2 * eta, 2 * eta * 0.9,
                                         fill=False, edgecolor=col,
                                         linestyle=":", linewidth=1))

    # Target
    ax.axvline(9.0, color=COLOR_GREEN, lw=1, ls=":")
    ax.text(9.0, 3.0, "目标 x*", color=COLOR_GREEN, fontsize=9, ha="center")

    ax.set_xlabel("state x")
    ax.set_ylabel("f(x)")
    ax.legend(loc="lower right")

    ax.annotate(
        "每轮：在参考点线性化 → 在置信域内解凸子问题 →\n若下降足够则放大置信域、否则收缩",
        xy=(4.6, -0.8), fontsize=9, color=COLOR_MUTE, ha="center")

    fig.tight_layout()
    return save_png(fig, "s02_mechanism")


# ---------------------------------------------------------------------------
# §3 6-DoF rigid body on SO(3)
# ---------------------------------------------------------------------------

def diagram_03_rigid_body():
    fig, ax = plt.subplots(figsize=(9.5, 4.2))
    _clean_axes(ax, (-0.2, 10.4), (-2.2, 2.2))
    ax.set_title("§3 6-DoF · 位置 + 姿态 在同一套微分方程里演化",
                  fontsize=12, fontweight="bold", color=COLOR_INK)

    # State block
    _box(ax, (0.2, 0.2), (2.4, 1.7),
          "state\n(r, v, q, ω, m)",
          fill="#fef7e7", edge=COLOR_WARN, fontsize=11, fontweight="bold")

    # Force / torque inputs
    _box(ax, (0.2, -1.9), (2.4, 1.2), "thrusters\n(F_body, τ_body)",
          fill=COLOR_ACCENT_SOFT, edge=COLOR_ACCENT, fontsize=10)
    _arrow(ax, (1.4, -0.7), (1.4, 0.15), color=COLOR_ACCENT)

    # Four dynamics blocks
    blocks = [
        ((3.5, 1.4), "ṙ = v", "位置"),
        ((5.3, 1.4), "v̇ = g + R(q)·F/m", "速度"),
        ((7.3, 1.4), "q̇ = ½·Ω(ω)·q", "姿态 (SO(3))"),
        ((9.1, 1.4), "ω̇ = J⁻¹(τ − ω×Jω)", "角速度"),
    ]
    for (x, y), eq, label in blocks:
        _box(ax, (x - 0.15, y - 0.5), (1.7, 1.0), eq,
              fill=COLOR_KEY_SOFT, edge=COLOR_KEY, fontsize=9)
        ax.text(x + 0.7, y + 0.65, label, color=COLOR_KEY,
                fontsize=9, ha="center")

    _arrow(ax, (2.55, 1.0), (3.5, 1.4), color=COLOR_KEY, rad=-0.2)
    _arrow(ax, (2.55, 1.0), (5.3, 1.4), color=COLOR_KEY, rad=-0.1)
    _arrow(ax, (2.55, 1.0), (7.3, 1.4), color=COLOR_KEY, rad=0.1)
    _arrow(ax, (2.55, 1.0), (9.1, 1.4), color=COLOR_KEY, rad=0.2)

    # RK4 loop
    _box(ax, (4.6, -1.8), (3.0, 1.0),
          "RK4 + quat\nexp-map 归一化",
          fill="#eaf2e6", edge=COLOR_GREEN, fontsize=10, fontweight="bold")
    _arrow(ax, (6.1, 0.9), (6.1, -0.8),
            color=COLOR_GREEN, ls="--", rad=0)
    ax.text(6.3, 0.1, "dstate/dt", color=COLOR_GREEN, fontsize=9)
    _arrow(ax, (4.6, -1.3), (2.6, 0.5),
            color=COLOR_GREEN, ls="--", rad=0.3)
    ax.text(3.0, -0.9, "next state", color=COLOR_GREEN, fontsize=9)

    fig.tight_layout()
    return save_png(fig, "s03_mechanism")


# ---------------------------------------------------------------------------
# §4 Thrust Pointing Cone
# ---------------------------------------------------------------------------

def diagram_04_cone():
    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    _clean_axes(ax, (-3.6, 3.6), (-0.6, 4.5))
    ax.set_title("§4 指向锥 ∩ 幅值球 · 把 NN 候选推力投回可行集",
                  fontsize=12, fontweight="bold", color=COLOR_INK)

    # the cone (triangle) with vertical axis
    theta = np.deg2rad(22)   # bigger than reality for legibility
    h = 4.0
    cone = plt.Polygon([[0, 0],
                         [-h * np.tan(theta), h],
                         [h * np.tan(theta), h]],
                        closed=True,
                        facecolor=COLOR_KEY_SOFT,
                        edgecolor=COLOR_KEY, linewidth=1.5)
    ax.add_patch(cone)
    # ball cap
    arc_theta = np.linspace(np.pi / 2 - theta, np.pi / 2 + theta, 100)
    R = h / np.cos(theta)
    bx = R * np.cos(arc_theta)
    by = R * np.sin(arc_theta)
    ax.plot(bx, by, color=COLOR_KEY, lw=1.5)
    # fill ball cap
    ax.fill_between(bx, by, np.full_like(by, h), color=COLOR_KEY_SOFT, alpha=0.5)

    # axis
    ax.plot([0, 0], [0, h + 0.4], color=COLOR_MUTE, lw=1, ls=":")
    ax.text(0.05, h + 0.45, "n̂", fontsize=11, color=COLOR_MUTE)

    # a raw u_nom outside the cone
    u_raw = np.array([2.3, 1.9])
    ax.annotate("", xy=u_raw, xytext=(0, 0),
                arrowprops=dict(arrowstyle="-|>", color=COLOR_ACCENT, lw=1.6))
    ax.scatter(*u_raw, color=COLOR_ACCENT, s=70, zorder=5)
    ax.text(u_raw[0] + 0.1, u_raw[1] + 0.1, "u_nom (NN)",
            color=COLOR_ACCENT, fontsize=10, fontweight="bold")

    # projected u* on cone boundary
    # direction along cone edge: (sin θ, cos θ)
    edge_dir = np.array([np.sin(theta), np.cos(theta)])
    u_proj_scalar = float(u_raw @ edge_dir)
    u_proj = u_proj_scalar * edge_dir
    ax.scatter(*u_proj, color=COLOR_GREEN, s=70, zorder=6)
    ax.annotate("", xy=u_proj, xytext=(0, 0),
                arrowprops=dict(arrowstyle="-|>", color=COLOR_GREEN, lw=1.6))
    ax.plot([u_raw[0], u_proj[0]], [u_raw[1], u_proj[1]],
            color=COLOR_ACCENT, lw=1, ls="--")
    ax.text(u_proj[0] - 0.1, u_proj[1] - 0.2, "u⋆ = filter(u_nom)",
            color=COLOR_GREEN, fontsize=10, fontweight="bold", ha="right")

    # labels
    ax.text(h * np.tan(theta) + 0.05, h - 0.1,
            "锥内: n̂·u ≥ ‖u‖·cosθ_max",
            color=COLOR_KEY, fontsize=9)
    ax.text(-3.3, 3.4, "球内: ‖u‖ ≤ T_max",
             color=COLOR_KEY, fontsize=9)

    fig.tight_layout()
    return save_png(fig, "s04_mechanism")


# ---------------------------------------------------------------------------
# §5 EKF multi-sensor
# ---------------------------------------------------------------------------

def diagram_05_ekf():
    fig, ax = plt.subplots(figsize=(10.5, 4.6))
    _clean_axes(ax, (-0.2, 11.2), (-0.2, 5.2))
    ax.set_title("§5 EKF · 雷达 + IMU + 视觉 Fiducial 多源融合",
                  fontsize=12, fontweight="bold", color=COLOR_INK)

    # Three sensor inputs on the left
    sensors = [
        ((0.3, 3.8), "雷达 range/az/el\nR=diag(40², 5mrad²)"),
        ((0.3, 2.1), "IMU ω, a_body\n高频(1kHz) 低噪"),
        ((0.3, 0.3), "塔架 AprilTag\npinhole pix 2×2"),
    ]
    for (x, y), text in sensors:
        _box(ax, (x, y), (2.5, 1.2), text,
              fill=COLOR_ACCENT_SOFT, edge=COLOR_ACCENT, fontsize=9)

    # Predict & Update blocks
    _box(ax, (4.2, 3.2), (2.8, 1.5),
          "Predict:\n x̂_k|k−1 = f(x̂_{k−1})\n P_k|k−1 = F P F^T + Q",
          fill="#fef7e7", edge=COLOR_WARN, fontsize=9)
    _box(ax, (4.2, 0.7), (2.8, 1.8),
          "Update:\n y = z − h(x̂)\n K = P H^T S⁻¹\n x̂_k|k = x̂ + K y",
          fill="#eaf2e6", edge=COLOR_GREEN, fontsize=9)

    # state estimate out
    _box(ax, (8.3, 2.0), (2.6, 1.5),
          "融合态\nx̂ = [r, v, q, ω]\nP",
          fill=COLOR_KEY_SOFT, edge=COLOR_KEY, fontsize=10, fontweight="bold")

    # arrows
    for (_, y), _ in sensors:
        _arrow(ax, (2.8, y + 0.6), (4.2, 1.6), color=COLOR_ACCENT, rad=-0.15)
    _arrow(ax, (5.6, 3.2), (5.6, 2.5), color=COLOR_INK, label="x̂")
    _arrow(ax, (7.0, 1.6), (8.3, 2.75), color=COLOR_GREEN)
    _arrow(ax, (9.5, 3.5), (5.6, 4.7), color=COLOR_KEY,
            ls="--", rad=0.3)
    ax.text(7.5, 4.4, "feedback to next k", color=COLOR_KEY,
             fontsize=9, ha="center")

    fig.tight_layout()
    return save_png(fig, "s05_mechanism")


# ---------------------------------------------------------------------------
# §6 MPC Receding Horizon
# ---------------------------------------------------------------------------

def diagram_06_mpc():
    fig, ax = plt.subplots(figsize=(10.5, 4.4))
    _clean_axes(ax, (-0.2, 12.2), (-0.3, 4.0))
    ax.set_title("§6 MPC · 解一个 N 步最优，只执行 u₀，然后 shift+resolve",
                  fontsize=12, fontweight="bold", color=COLOR_INK)

    # Three horizons (at t, t+1, t+2)
    horizons = [
        (0.2, "#c8d4e3", "t"),
        (3.0, "#b1c3d8", "t + dt"),
        (5.8, "#9bb0cc", "t + 2·dt"),
    ]
    for (x0, col, label) in horizons:
        ax.add_patch(mpatches.Rectangle(
            (x0, 0.5), 5.6, 2.2, facecolor=col, edgecolor=COLOR_KEY,
            linewidth=1, alpha=0.5))
        ax.text(x0 + 2.8, 2.85, f"horizon @ {label}",
                 ha="center", fontsize=9, color=COLOR_KEY)

        # plan curve
        xs = np.linspace(x0, x0 + 5.2, 60)
        ys = 1.6 + 0.6 * np.exp(-0.3 * (xs - x0)) * np.sin(1.4 * (xs - x0))
        ax.plot(xs, ys, color=COLOR_KEY, lw=1.1, ls="--")
        # u0 bar
        ax.add_patch(mpatches.Rectangle(
            (x0, 0.55), 0.5, 0.35, facecolor=COLOR_ACCENT,
            edgecolor=COLOR_ACCENT, alpha=0.9))

    # execution line
    ax.plot([0.2, 6.3], [0.5, 0.5], color=COLOR_ACCENT, lw=3.5, alpha=0.85)
    ax.text(3.2, 0.2, "实际执行的控制（只取每个 horizon 的 u₀）",
             ha="center", fontsize=10, color=COLOR_ACCENT, fontweight="bold")

    # target line
    ax.axhline(1.6, color=COLOR_GREEN, lw=1, ls=":")
    ax.text(11.5, 1.65, "reference", color=COLOR_GREEN, fontsize=9)

    ax.text(6.0, 3.5,
             "每拍只执行第一步；\n下一拍用上拍解做 warm-start",
             fontsize=10, color=COLOR_MUTE, ha="center")

    fig.tight_layout()
    return save_png(fig, "s06_mechanism")


# ---------------------------------------------------------------------------
# §7 Flip maneuver
# ---------------------------------------------------------------------------

def diagram_07_flip():
    fig, (axL, axR) = plt.subplots(1, 2, figsize=(11, 4.2))
    fig.suptitle("§7 Belly-Flop → Landing-Flip · bang-bang 最小时间翻转",
                  fontsize=12, fontweight="bold", color=COLOR_INK)

    # LEFT: schematic with booster orientation at three phases
    _clean_axes(axL, (-0.2, 6.2), (-0.2, 5.2))
    poses = [
        (1.0, 4.3, np.pi / 2, "belly-down"),
        (3.0, 2.8, np.pi / 4, "flipping"),
        (5.0, 1.0, 0.0, "tail-down"),
    ]
    for (cx, cy, ang, label) in poses:
        # draw the booster as a tilted capsule
        w, h = 0.3, 1.3
        rect = mpatches.Rectangle((-w / 2, -h / 2), w, h,
                                    facecolor="#bfc4cc",
                                    edgecolor=COLOR_INK, linewidth=1.2)
        t = Affine2D().rotate(ang).translate(cx, cy) + axL.transData
        rect.set_transform(t)
        axL.add_patch(rect)
        # nose marker (small triangle at top of body)
        nose = plt.Polygon([[0, h / 2],
                             [-w / 2, h / 2 - 0.2],
                             [w / 2, h / 2 - 0.2]],
                             facecolor=COLOR_KEY, edgecolor=COLOR_KEY)
        nose.set_transform(t)
        axL.add_patch(nose)
        axL.text(cx, cy - 0.9, label, ha="center", fontsize=9,
                  color=COLOR_MUTE)

    axL.annotate("", xy=(4.3, 1.6), xytext=(1.8, 4.0),
                  arrowprops=dict(arrowstyle="-|>",
                                  color=COLOR_ACCENT, lw=1.5,
                                  connectionstyle="arc3,rad=-0.3"))
    axL.text(5.8, 4.2, "pitch 从 90°\n翻到 0°",
              color=COLOR_ACCENT, fontsize=10, ha="center",
              fontweight="bold")

    # RIGHT: τ profile (bang-bang)
    t = np.linspace(0, 3.0, 300)
    tau = np.where(t < 1.5, 1.0, -1.0)
    axR.plot(t, tau, color=COLOR_ACCENT, lw=2.5)
    axR.fill_between(t, 0, tau, color=COLOR_ACCENT, alpha=0.18)
    axR.axhline(0, color=COLOR_MUTE, lw=0.6)
    axR.set_title("力矩 τ(t)：先 +τ_max 加速翻 → 后 −τ_max 刹停",
                   color=COLOR_ACCENT, fontsize=10)
    axR.set_xlabel("t [s]")
    axR.set_ylabel("τ / τ_max")
    axR.set_ylim(-1.3, 1.3)
    axR.text(0.75, 0.6, "+τ_max", ha="center", color=COLOR_INK, fontsize=10)
    axR.text(2.25, -0.6, "−τ_max", ha="center", color=COLOR_INK, fontsize=10)
    axR.axvline(1.5, color=COLOR_MUTE, lw=1, ls=":")
    axR.text(1.5, 1.1, "switch", ha="center", fontsize=9, color=COLOR_MUTE)

    plt.tight_layout(rect=[0, 0, 1, 0.94])
    return save_png(fig, "s07_mechanism")


# ---------------------------------------------------------------------------
# §8 Catch thrust allocation
# ---------------------------------------------------------------------------

def diagram_08_catch():
    fig, (axL, axR) = plt.subplots(1, 2, figsize=(11, 4.6))
    fig.suptitle("§8 捕获段推力分配 · 3 台 Raptor 合成 6-D 力/力矩",
                  fontsize=12, fontweight="bold", color=COLOR_INK)

    # LEFT: top-down view of three thrusters at 120°
    _clean_axes(axL, (-2.6, 2.6), (-2.6, 2.6))
    axL.add_patch(mpatches.Circle((0, 0), 1.2,
                                    facecolor="#f1efe9",
                                    edgecolor=COLOR_MUTE,
                                    linewidth=1))
    thrust_mags = [0.95, 0.75, 0.80]     # arbitrary for vis
    for i, (ang_deg, mag) in enumerate(zip([90, 210, 330], thrust_mags)):
        a = np.deg2rad(ang_deg)
        r0 = 1.2 * np.array([np.cos(a), np.sin(a)])
        axL.scatter(*r0, s=90, c=COLOR_ACCENT, zorder=5)
        axL.annotate("", xy=r0 + mag * np.array([np.cos(a), np.sin(a)]) * 1.2,
                      xytext=r0,
                      arrowprops=dict(arrowstyle="-|>",
                                      color=COLOR_ACCENT, lw=1.8))
        axL.text(r0[0] * 1.55, r0[1] * 1.55, f"T{i+1}\n={mag*2.3:.1f} MN",
                  ha="center", fontsize=9, color=COLOR_ACCENT,
                  fontweight="bold")
    # net force arrow at centre
    net = sum(m * np.array([np.cos(np.deg2rad(a)), np.sin(np.deg2rad(a))])
              for m, a in zip(thrust_mags, [90, 210, 330]))
    axL.annotate("", xy=net * 0.9, xytext=(0, 0),
                  arrowprops=dict(arrowstyle="-|>",
                                  color=COLOR_KEY, lw=2.2))
    axL.text(0.05, -0.25, "合成 F_body",
              color=COLOR_KEY, fontsize=10, fontweight="bold")
    axL.set_title("布局（俯视）· 3 台 Raptor 120° 环绕",
                   color=COLOR_INK, fontsize=10)

    # RIGHT: allocation equation
    _clean_axes(axR, (0, 10), (0, 5))
    axR.set_title("分配问题 · 有界最小二乘",
                   color=COLOR_INK, fontsize=10)

    axR.text(0.3, 4.2,
              "min‖A·t − [F; τ]‖²",
              fontsize=16, color=COLOR_INK, fontweight="bold")
    axR.text(0.3, 3.0,
              "s.t.  T_min ≤ t_i ≤ T_max",
              fontsize=14, color=COLOR_INK)

    axR.text(0.3, 1.8,
              "A = [d₁  d₂  d₃]\n    [l₁×d₁  l₂×d₂  l₃×d₃]",
              fontsize=12, color=COLOR_MUTE, family="monospace")

    axR.text(0.3, 0.5,
              "→ scipy.optimize.lsq_linear\n  3 个变量, 6 个残差, 6 个框约束",
              fontsize=10, color=COLOR_GREEN)

    plt.tight_layout(rect=[0, 0, 1, 0.94])
    return save_png(fig, "s08_mechanism")


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------

def main():
    diagram_01_lossless_convex()
    diagram_02_scp()
    diagram_03_rigid_body()
    diagram_04_cone()
    diagram_05_ekf()
    diagram_06_mpc()
    diagram_07_flip()
    diagram_08_catch()
    print("mechanism diagrams written to:", ASSET_DIR)


if __name__ == "__main__":
    main()
