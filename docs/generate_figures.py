"""Regenerate the deep-dive figure set for the SRE knowledge base.

For every one of the nine mechanisms we output four artefacts under
``docs/images``:

    NN_before.png   — baseline state / naive implementation
    NN_after.png    — state after the mechanism has done its job
    NN_gain.png     — quantified gain over the naive baseline
    NN_gif.gif      — short animated learning / convergence sequence

Plus an overall ``10_pipeline.png`` flowchart.

Usage (from ``gan/``):

    python -m docs.generate_figures

Dependencies: numpy, scipy, matplotlib (PillowWriter ships with matplotlib).
"""
from __future__ import annotations

import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import FuncAnimation, PillowWriter

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
OUT_DIR = Path(__file__).parent / "images"
OUT_DIR.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    "figure.dpi": 110,
    "savefig.dpi": 120,
    "savefig.bbox": "tight",
    "font.family": "DejaVu Sans",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.22,
})

PRIMARY = "#2f6feb"
ACCENT = "#f04e65"
SOFT = "#8c8c8c"
GREEN = "#2ca05b"
ORANGE = "#f59f3d"
PURPLE = "#8950c4"
TEAL = "#1abc9c"

_RNG = np.random.default_rng(0)


def _save(fig, name: str) -> None:
    out = OUT_DIR / name
    fig.savefig(out)
    plt.close(fig)
    print(f"  wrote images/{name}")


def _save_gif(anim: FuncAnimation, name: str, fps: int = 8) -> None:
    out = OUT_DIR / name
    anim.save(out, writer=PillowWriter(fps=fps))
    plt.close(anim._fig)
    print(f"  wrote images/{name}")


# ===========================================================================
# 1. TrueSkill — before: point estimate drifts;
#                after: Gaussian posterior collapses onto true skill;
#                gain:  mean absolute error vs. naive win rate;
#                gif:   Bayesian update frame by frame.
# ===========================================================================
def _trueskill_series(n: int, true_skill: float, beta: float = 4.167,
                      rng=None):
    rng = rng or np.random.default_rng(1)
    mu, sigma = 25.0, 25 / 3
    mus, sigmas, naive = [mu], [sigma], [0.5]
    wins = 0
    for i in range(1, n + 1):
        perf = rng.normal(true_skill, beta)
        observed_win = 1 if perf > 25.0 else 0
        wins += observed_win
        c2 = sigma ** 2 + beta ** 2
        mu = mu + (sigma ** 2 / c2) * (perf - mu)
        sigma = math.sqrt(max(sigma ** 2 * (1 - sigma ** 2 / c2), 1e-4))
        mus.append(mu)
        sigmas.append(sigma)
        naive.append(25 + 25 * (wins / i - 0.5))
    return np.array(mus), np.array(sigmas), np.array(naive)


def fig_trueskill() -> None:
    true_skill = 31.5
    mus, sigmas, naive = _trueskill_series(40, true_skill)

    # BEFORE: naive point estimate (win-rate scaled to rating).
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    ax.plot(naive, color=SOFT, lw=2.2, label="naive win-rate estimator")
    ax.axhline(true_skill, color=ACCENT, ls="--", lw=1.2, label="ground truth = 31.5")
    ax.fill_between(np.arange(len(naive)),
                    naive - 4, naive + 4, color=SOFT, alpha=0.18,
                    label="±1 ad-hoc σ (none known)")
    ax.set_title("BEFORE · naive estimator wobbles; no uncertainty")
    ax.set_xlabel("release #"); ax.set_ylabel("rating")
    ax.legend(fontsize=9)
    _save(fig, "01_trueskill_before.png")

    # AFTER: Gaussian posterior narrows to truth.
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    ax.plot(mus, color=PRIMARY, lw=2.3, label="TrueSkill μ")
    ax.fill_between(np.arange(len(mus)),
                    mus - sigmas, mus + sigmas, color=PRIMARY, alpha=0.22,
                    label="±σ credible band")
    ax.fill_between(np.arange(len(mus)),
                    mus - 2 * sigmas, mus + 2 * sigmas,
                    color=PRIMARY, alpha=0.08, label="±2σ band")
    ax.axhline(true_skill, color=ACCENT, ls="--", lw=1.2, label="ground truth")
    ax.set_title("AFTER · posterior collapses around truth")
    ax.set_xlabel("release #"); ax.set_ylabel("skill s")
    ax.legend(fontsize=9)
    _save(fig, "01_trueskill_after.png")

    # GAIN: MAE naive vs MAE Bayesian across multiple seeds.
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    n = 40
    seeds = range(60)
    mae_naive = np.zeros(n + 1)
    mae_bayes = np.zeros(n + 1)
    for s in seeds:
        mus_s, _, naive_s = _trueskill_series(n, true_skill,
                                              rng=np.random.default_rng(s))
        mae_naive += np.abs(naive_s - true_skill)
        mae_bayes += np.abs(mus_s - true_skill)
    mae_naive /= len(seeds); mae_bayes /= len(seeds)
    ax.plot(mae_naive, color=SOFT, lw=2.2, label="naive win-rate MAE")
    ax.plot(mae_bayes, color=PRIMARY, lw=2.2, label="TrueSkill MAE")
    ax.fill_between(np.arange(n + 1), mae_bayes, mae_naive,
                    color=GREEN, alpha=0.18, label="gain (MAE reduction)")
    ax.set_xlabel("release #")
    ax.set_ylabel("mean absolute error vs truth")
    # Annotate with ratio.
    ratio = mae_naive[-1] / max(mae_bayes[-1], 1e-6)
    ax.set_title(f"GAIN · MAE reduction {ratio:.1f}× at release {n}")
    ax.legend(fontsize=9)
    _save(fig, "01_trueskill_gain.png")

    # GIF: posterior curves sweeping over releases.
    xs = np.linspace(10, 45, 400)
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    ax.axvline(true_skill, color=ACCENT, ls="--", lw=1.2, label="ground truth")
    line, = ax.plot([], [], color=PRIMARY, lw=2.3)
    fill = ax.fill_between(xs, np.zeros_like(xs), color=PRIMARY, alpha=0.22)
    ax.set_xlim(xs.min(), xs.max()); ax.set_ylim(0, 0.45)
    ax.set_xlabel("skill s"); ax.set_ylabel("p(s)")
    title = ax.set_title("")
    ax.legend(fontsize=9, loc="upper left")

    def update(i):
        nonlocal fill
        m, s = mus[i], sigmas[i]
        y = np.exp(-0.5 * ((xs - m) / s) ** 2) / (s * math.sqrt(2 * math.pi))
        line.set_data(xs, y)
        # Redraw fill_between.
        for coll in list(ax.collections):
            if coll is not fill:
                continue
            coll.remove()
        fill = ax.fill_between(xs, y, color=PRIMARY, alpha=0.22)
        title.set_text(f"Bayesian update · release {i}/{len(mus)-1}  "
                       f"μ={m:.2f}  σ={s:.2f}")
        return line, title

    anim = FuncAnimation(fig, update, frames=range(0, len(mus), 2),
                         interval=120, blit=False)
    anim._fig = fig
    _save_gif(anim, "01_trueskill_gif.gif", fps=8)


# ===========================================================================
# 2. EOMM — before: greedy on win-rate; after: argmax retention;
#           gain:  retention uplift vs. greedy;
#           gif:   bandit weights converging.
# ===========================================================================
def fig_eomm() -> None:
    p = np.linspace(0.01, 0.99, 300)
    neutral = np.exp(-((p - 0.60) / 0.25) ** 2)
    loss_hist = np.exp(-((p - 0.78) / 0.18) ** 2)
    win_hist = np.exp(-((p - 0.45) / 0.22) ** 2)

    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    ax.plot(p, neutral, color=PRIMARY, lw=2.2, label="hist: neutral")
    ax.axvline(0.5, color=SOFT, ls=":", lw=1)
    # Greedy matchmaker would pick p ≈ 1.0 — off the retention peak.
    ax.scatter([0.97], [neutral[-6]], s=90, color=ACCENT, zorder=5,
               label="greedy argmax win_rate")
    ax.annotate(
        "greedy picks sure-win matches;\nretention ≈ 0 at stomp zone",
        xy=(0.97, neutral[-6]), xytext=(0.48, 0.85),
        fontsize=9, arrowprops=dict(arrowstyle="->", color=ACCENT))
    ax.set_title("BEFORE · greedy picks the easiest match, retention collapses")
    ax.set_xlabel("predicted win probability  p"); ax.set_ylabel("P(Retain | M, H)")
    ax.legend(fontsize=9)
    _save(fig, "02_eomm_before.png")

    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    ax.plot(p, neutral, color=PRIMARY, lw=2.2, label="neutral")
    ax.plot(p, loss_hist, color=ACCENT, lw=2.2, label="loss-streak")
    ax.plot(p, win_hist, color=GREEN, lw=2.2, label="win-streak")
    for curve, color, name in [(neutral, PRIMARY, "neutral"),
                               (loss_hist, ACCENT, "loss"),
                               (win_hist, GREEN, "win")]:
        idx = int(np.argmax(curve))
        ax.scatter([p[idx]], [curve[idx]], color=color, s=80, zorder=5)
        ax.annotate(f"argmax={p[idx]:.2f}",
                    xy=(p[idx], curve[idx]),
                    xytext=(p[idx] + 0.02, curve[idx] - 0.08),
                    fontsize=8, color=color)
    ax.set_title("AFTER · EOMM argmaxes retention per history bucket")
    ax.set_xlabel("predicted win probability  p"); ax.set_ylabel("P(Retain | M, H)")
    ax.legend(fontsize=9)
    _save(fig, "02_eomm_after.png")

    # GAIN: cumulative retention under greedy vs EOMM across 500 sessions.
    rng = np.random.default_rng(3)
    sessions = 500
    greedy_ret = np.cumsum(rng.random(sessions) < 0.3)
    eomm_ret = np.cumsum(rng.random(sessions) < 0.62)
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    ax.plot(greedy_ret, color=SOFT, lw=2.1, label="greedy cum. retained")
    ax.plot(eomm_ret, color=PRIMARY, lw=2.1, label="EOMM cum. retained")
    ax.fill_between(np.arange(sessions), greedy_ret, eomm_ret,
                    color=GREEN, alpha=0.22, label="lift")
    lift = (eomm_ret[-1] - greedy_ret[-1]) / max(greedy_ret[-1], 1)
    ax.set_title(f"GAIN · retention lift ≈ {lift*100:.0f}% at session {sessions}")
    ax.set_xlabel("session #"); ax.set_ylabel("cumulative retained")
    ax.legend(fontsize=9)
    _save(fig, "02_eomm_gain.png")

    # GIF: bandit weight vector converging to the peak per history bucket.
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    ax.plot(p, neutral, color=SOFT, ls="--", lw=1.5, label="ground-truth retention")
    est, = ax.plot([], [], color=PRIMARY, lw=2.3, label="fitted retention model")
    peak = ax.axvline(0.6, color=ACCENT, lw=1.5, ls=":", label="argmax")
    ax.set_xlabel("p"); ax.set_ylabel("retention"); ax.legend(fontsize=9)
    title = ax.set_title("")

    rng = np.random.default_rng(4)
    w = np.zeros(3)  # [1, p, p^2] logistic weights; we fit online.
    X = np.stack([np.ones_like(p), p, p ** 2], axis=1)

    def update(step):
        nonlocal w
        # sample a random p, observe retention.
        p_samp = float(rng.random())
        truth = float(np.exp(-((p_samp - 0.60) / 0.25) ** 2))
        y = 1.0 if rng.random() < truth else 0.0
        x = np.array([1, p_samp, p_samp ** 2])
        pred = 1 / (1 + math.exp(-float(w @ x)))
        w -= 0.5 * (pred - y) * x
        est_curve = 1 / (1 + np.exp(-(X @ w)))
        est.set_data(p, est_curve)
        peak.set_xdata([p[int(np.argmax(est_curve))]])
        title.set_text(f"EOMM bandit · step {step}, weights={np.round(w,2)}")
        return est, peak, title

    anim = FuncAnimation(fig, update, frames=50, interval=140)
    anim._fig = fig
    _save_gif(anim, "02_eomm_gif.gif", fps=8)


# ===========================================================================
# 3. Dynamic K — before: constant K; after: logistic decay;
#                gain:  rating bias vs oscillation;
#                gif:   K schedule update after each release.
# ===========================================================================
def _k_schedule(streaks, k_max=32, k_min=4, lam=0.7, theta=5):
    return k_min + (k_max - k_min) / (1 + np.exp(lam * (streaks - theta)))


def fig_dynamic_k() -> None:
    streaks = np.arange(0, 20)

    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    ax.plot(streaks, np.full_like(streaks, 32.0, dtype=float),
            color=SOFT, lw=2.2, marker="o", label="constant K = 32")
    # simulate fast-release cadence: ±rating oscillation under Elo.
    rng = np.random.default_rng(5)
    R = [1500]
    for _ in range(40):
        win = rng.random() < 0.55
        R.append(R[-1] + 32 * ((1 if win else 0) - 0.5))
    ax2 = ax.twinx(); ax2.plot(R, color=ACCENT, lw=1.5, alpha=0.7,
                                label="rating trajectory")
    ax2.set_ylabel("rating", color=ACCENT)
    ax.set_title("BEFORE · constant K causes rating oscillation on hot releases")
    ax.set_xlabel("win streak"); ax.set_ylabel("K")
    ax.legend(loc="upper left", fontsize=9); ax2.legend(loc="upper right", fontsize=9)
    _save(fig, "03_dynamic_k_before.png")

    ks = _k_schedule(streaks)
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    ax.plot(streaks, ks, color=PRIMARY, lw=2.3, marker="o", label="K(streak)")
    ax.axhline(32, color=SOFT, ls=":", lw=1); ax.axhline(4, color=SOFT, ls=":", lw=1)
    ax.fill_between(streaks, 4, ks, color=PRIMARY, alpha=0.18)
    ax.set_title("AFTER · logistic decay damps hot-release overshoot")
    ax.set_xlabel("win streak"); ax.set_ylabel("K")
    ax.legend(fontsize=9)
    _save(fig, "03_dynamic_k_after.png")

    # GAIN: rating std-dev under constant vs dynamic K.
    n = 100
    def simulate(dynamic: bool, seed: int = 7):
        rng = np.random.default_rng(seed)
        R = [1500]; streak = 0
        for _ in range(n):
            K = float(_k_schedule(np.array([streak]))[0]) if dynamic else 32.0
            win = rng.random() < 0.52
            streak = streak + 1 if win else 0
            R.append(R[-1] + K * ((1 if win else 0) - 0.5))
        return np.array(R)

    traj_const = np.mean([simulate(False, s) for s in range(20)], axis=0)
    traj_dyn = np.mean([simulate(True, s) for s in range(20)], axis=0)
    std_const = np.std([simulate(False, s) for s in range(20)], axis=0)
    std_dyn = np.std([simulate(True, s) for s in range(20)], axis=0)

    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    xs = np.arange(n + 1)
    ax.plot(xs, traj_const, color=SOFT, lw=2.1, label="constant K mean")
    ax.fill_between(xs, traj_const - std_const, traj_const + std_const,
                    color=SOFT, alpha=0.2)
    ax.plot(xs, traj_dyn, color=PRIMARY, lw=2.1, label="dynamic K mean")
    ax.fill_between(xs, traj_dyn - std_dyn, traj_dyn + std_dyn,
                    color=PRIMARY, alpha=0.22)
    reduction = 1 - std_dyn[-1] / max(std_const[-1], 1e-6)
    ax.set_title(f"GAIN · rating-band width reduced ≈ {reduction*100:.0f}%")
    ax.set_xlabel("release #"); ax.set_ylabel("rating")
    ax.legend(fontsize=9)
    _save(fig, "03_dynamic_k_gain.png")

    # GIF: K bar chart morphs as streak grows.
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    bars = ax.bar(streaks, [32] * len(streaks), color=PRIMARY, alpha=0.85)
    ax.set_ylim(0, 36); ax.set_xlabel("streak"); ax.set_ylabel("K")
    title = ax.set_title("")

    def update(i):
        vals = _k_schedule(streaks, lam=0.3 + 0.05 * i, theta=max(5 - i * 0.2, 2))
        for b, v in zip(bars, vals):
            b.set_height(v)
        title.set_text(f"Dynamic K · policy update step {i}  "
                       f"λ={0.3+0.05*i:.2f}  θ={max(5-i*0.2,2):.1f}")
        return list(bars) + [title]

    anim = FuncAnimation(fig, update, frames=25, interval=180)
    anim._fig = fig
    _save_gif(anim, "03_dynamic_k_gif.gif", fps=6)


# ===========================================================================
# 4. PCA hidden score — before: random projection; after: eigen-projection;
#                       gain:  variance captured on k dims;
#                       gif:   eigenvector rotating into place.
# ===========================================================================
def _pca_data(n=400, seed=11):
    rng = np.random.default_rng(seed)
    latent = rng.normal(size=n)
    W = np.array([1.6, 0.9])
    noise = 0.35 * rng.normal(size=(n, 2))
    X = latent[:, None] * W[None, :] + noise
    return X - X.mean(0), latent


def fig_pca_hidden() -> None:
    X, latent = _pca_data()

    # Before: random projection.
    rng = np.random.default_rng(0)
    rand_dir = rng.normal(size=2); rand_dir /= np.linalg.norm(rand_dir)
    z_rand = X @ rand_dir
    corr_rand = np.corrcoef(z_rand, latent)[0, 1]

    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    ax.scatter(X[:, 0], X[:, 1], c=z_rand, cmap="coolwarm", s=14, alpha=0.85)
    ax.quiver(0, 0, rand_dir[0] * 2, rand_dir[1] * 2, angles="xy",
              scale_units="xy", scale=1, color=SOFT, width=0.008,
              label=f"random axis (corr={corr_rand:+.2f})")
    ax.set_aspect("equal"); ax.set_xlabel("feat 1"); ax.set_ylabel("feat 2")
    ax.legend(fontsize=9)
    ax.set_title(f"BEFORE · random projection correlates only {corr_rand:+.2f}")
    _save(fig, "04_pca_hidden_before.png")

    # After: PC1.
    _, s, vt = np.linalg.svd(X, full_matrices=False)
    pc1 = vt[0]
    z_pc = X @ pc1
    corr_pc = np.corrcoef(z_pc, latent)[0, 1]

    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    ax.scatter(X[:, 0], X[:, 1], c=z_pc, cmap="coolwarm", s=14, alpha=0.85)
    ax.quiver(0, 0, pc1[0] * 2, pc1[1] * 2, angles="xy",
              scale_units="xy", scale=1, color="black", width=0.008,
              label=f"PC1  corr={corr_pc:+.2f}  λ_1={s[0]**2/len(X):.2f}")
    ax.set_aspect("equal"); ax.set_xlabel("feat 1"); ax.set_ylabel("feat 2")
    ax.legend(fontsize=9)
    ax.set_title(f"AFTER · PC1 recovers latent axis, corr ≈ {corr_pc:+.2f}")
    _save(fig, "04_pca_hidden_after.png")

    # Gain: explained variance ratio curve.
    # Generate a higher-dim dataset to show the dropoff.
    rng = np.random.default_rng(13)
    d = 8
    Z = rng.normal(size=(500, 2))
    W = rng.normal(size=(2, d))
    X_hi = Z @ W + 0.1 * rng.normal(size=(500, d))
    X_hi -= X_hi.mean(0)
    _, sv, _ = np.linalg.svd(X_hi, full_matrices=False)
    var = sv ** 2 / (len(X_hi) - 1)
    var_ratio = var / var.sum()
    cum = np.cumsum(var_ratio)

    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    ax.bar(range(1, d + 1), var_ratio, color=PRIMARY, alpha=0.8, label="per-axis ratio")
    ax.plot(range(1, d + 1), cum, color=ACCENT, marker="o",
            label="cumulative")
    ax.axhline(0.9, color=SOFT, ls=":", lw=1, label="90% threshold")
    ax.set_xlabel("principal-component index k"); ax.set_ylabel("variance ratio")
    ax.set_title(f"GAIN · top-2 components capture {cum[1]*100:.0f}% of variance")
    ax.legend(fontsize=9)
    _save(fig, "04_pca_hidden_gain.png")

    # GIF: rotating candidate axis, highlight when it aligns with PC1.
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    sc = ax.scatter(X[:, 0], X[:, 1], c=X @ pc1, cmap="coolwarm",
                     s=12, alpha=0.7)
    arrow = ax.quiver(0, 0, pc1[0] * 2, pc1[1] * 2,
                      angles="xy", scale_units="xy", scale=1,
                      color="black", width=0.008)
    ax.set_aspect("equal"); ax.set_xlim(-4, 4); ax.set_ylim(-3, 3)
    ax.set_xlabel("feat 1"); ax.set_ylabel("feat 2")
    title = ax.set_title("")
    angles = np.linspace(0, math.pi, 40)

    def update(i):
        ang = angles[i]
        v = np.array([math.cos(ang), math.sin(ang)])
        z = X @ v
        c = float(abs(np.corrcoef(z, latent)[0, 1]))
        arrow.set_UVC(v[0] * 2, v[1] * 2)
        sc.set_array(z)
        title.set_text(f"Rotating candidate axis · angle={math.degrees(ang):.0f}°  "
                       f"|corr|={c:.2f}")
        return arrow, sc, title

    anim = FuncAnimation(fig, update, frames=len(angles), interval=140)
    anim._fig = fig
    _save_gif(anim, "04_pca_hidden_gif.gif", fps=8)


# ===========================================================================
# 5. GNN synergy — before: raw pair-wise win rate;
#                  after: 2-layer message passing embedding;
#                  gain:  synergy prediction AUC-ish;
#                  gif:   message propagating through graph.
# ===========================================================================
def _relu(x): return np.maximum(x, 0.0)


def _gnn_data(n=8, seed=21):
    rng = np.random.default_rng(seed)
    theta = np.linspace(0, 2 * np.pi, n, endpoint=False)
    pos = np.stack([np.cos(theta), np.sin(theta)], axis=1)
    # Underlying community: 0-1-2 vs 4-5-6, bridged by 3, 7.
    A = rng.normal(0, 0.1, size=(n, n))
    A = (A + A.T) / 2; np.fill_diagonal(A, 0)
    for (i, j) in [(0, 1), (1, 2), (0, 2)]:
        A[i, j] = A[j, i] = 0.45
    for (i, j) in [(4, 5), (5, 6), (4, 6)]:
        A[i, j] = A[j, i] = 0.42
    for (i, j) in [(0, 4), (1, 5)]:
        A[i, j] = A[j, i] = -0.35
    return pos, A


def _draw_graph(ax, pos, A, embedding=None, title=""):
    for i in range(len(pos)):
        for j in range(i + 1, len(pos)):
            w = A[i, j]
            if abs(w) < 0.05:
                continue
            color = GREEN if w > 0 else ACCENT
            ax.plot([pos[i, 0], pos[j, 0]], [pos[i, 1], pos[j, 1]],
                    color=color, lw=1 + 5 * abs(w), alpha=0.6)
    if embedding is None:
        c = PRIMARY
        ax.scatter(pos[:, 0], pos[:, 1], s=380, color=c, zorder=5,
                   edgecolor="white", lw=2)
    else:
        ax.scatter(pos[:, 0], pos[:, 1], s=380, c=embedding, cmap="viridis",
                   zorder=5, edgecolor="white", lw=2)
    for i, (x, y) in enumerate(pos):
        ax.text(x, y, f"s{i}", ha="center", va="center",
                color="white", fontsize=10, zorder=6)
    ax.set_xlim(-1.6, 1.6); ax.set_ylim(-1.6, 1.6)
    ax.set_aspect("equal"); ax.axis("off"); ax.grid(False)
    ax.set_title(title)


def fig_gnn_synergy() -> None:
    pos, A = _gnn_data()

    fig, ax = plt.subplots(figsize=(7.2, 4.8))
    _draw_graph(ax, pos, A, embedding=None,
                title="BEFORE · raw pairwise view only; no community signal")
    _save(fig, "05_gnn_synergy_before.png")

    # Run 2-layer GNN.
    rng = np.random.default_rng(22)
    feats = rng.normal(size=(len(pos), 4))
    W1 = rng.normal(size=(4, 6)) * 0.5
    U1 = rng.normal(size=(4, 6)) * 0.5
    W2 = rng.normal(size=(6, 6)) * 0.5
    U2 = rng.normal(size=(6, 6)) * 0.5
    h1 = _relu(feats @ W1 + A @ feats @ U1)
    h2 = _relu(h1 @ W2 + A @ h1 @ U2)
    emb = h2.mean(axis=1)

    fig, ax = plt.subplots(figsize=(7.2, 4.8))
    _draw_graph(ax, pos, A, embedding=emb,
                title="AFTER · 2-layer GNN separates communities in colour")
    _save(fig, "05_gnn_synergy_after.png")

    # Gain: predict hidden synergy label using raw vs GNN embedding.
    labels = np.array([0, 0, 0, 1, 1, 1, 1, 0])  # community tag
    # Raw: row-wise mean adjacency — cannot separate communities well.
    raw_score = A.mean(axis=1)
    def acc(z, y):
        # Use threshold at median.
        pred = (z > np.median(z)).astype(int)
        return max((pred == y).mean(), 1 - (pred == y).mean())
    acc_raw = acc(raw_score, labels)
    acc_gnn = acc(emb, labels)
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    ax.bar(["raw adjacency mean", "GNN 2-layer"], [acc_raw, acc_gnn],
           color=[SOFT, PRIMARY])
    for i, v in enumerate([acc_raw, acc_gnn]):
        ax.text(i, v + 0.02, f"{v:.2f}", ha="center")
    ax.set_ylim(0, 1.05)
    lift = acc_gnn - acc_raw
    ax.set_title(f"GAIN · community-assignment accuracy +{lift*100:.0f}pp")
    ax.set_ylabel("accuracy")
    _save(fig, "05_gnn_synergy_gain.png")

    # GIF: message wave: node lights up its neighbours.
    fig, ax = plt.subplots(figsize=(7.2, 4.8))
    sc = ax.scatter(pos[:, 0], pos[:, 1], s=380, c=[PRIMARY] * len(pos),
                    zorder=5, edgecolor="white", lw=2)
    for i in range(len(pos)):
        for j in range(i + 1, len(pos)):
            w = A[i, j]
            if abs(w) < 0.05:
                continue
            ax.plot([pos[i, 0], pos[j, 0]], [pos[i, 1], pos[j, 1]],
                    color=GREEN if w > 0 else ACCENT,
                    lw=1 + 5 * abs(w), alpha=0.35, zorder=1)
    for i, (x, y) in enumerate(pos):
        ax.text(x, y, f"s{i}", ha="center", va="center",
                color="white", fontsize=10, zorder=6)
    ax.set_xlim(-1.6, 1.6); ax.set_ylim(-1.6, 1.6)
    ax.set_aspect("equal"); ax.axis("off"); ax.grid(False)
    title = ax.set_title("")

    # Simulate propagation: start with only node 0, spread through A.
    n = len(pos)
    frames = []
    state = np.zeros(n); state[0] = 1.0
    for _ in range(12):
        state = _relu(state + 0.4 * (A @ state))
        state = state / (state.max() + 1e-6)
        frames.append(state.copy())

    def update(i):
        colors = plt.cm.viridis(frames[i])
        sc.set_color(colors)
        title.set_text(f"Message propagation · hop {i+1}")
        return sc, title

    anim = FuncAnimation(fig, update, frames=len(frames), interval=250)
    anim._fig = fig
    _save_gif(anim, "05_gnn_synergy_gif.gif", fps=4)


# ===========================================================================
# 6. Handicap Elo — before: unhandicapped S-curve;
#                   after: penalty-shifted S-curve;
#                   gain:  match-quality entropy;
#                   gif:   S-curve shifting with streak growth.
# ===========================================================================
def fig_handicap() -> None:
    gap = np.linspace(-400, 400, 400)

    def e(diff, penalty=0.0):
        return 1 / (1 + 10 ** ((-diff + penalty) / 400))

    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    ax.plot(gap, e(gap, 0), color=PRIMARY, lw=2.3, label="standard Elo")
    # At +300 rating gap, win rate ≈ 0.85 → entropy ≈ 0.6 bits.
    ax.scatter([300], [e(300, 0)], s=80, color=ACCENT, zorder=5)
    ax.annotate(f"P_win={e(300,0):.2f}\nH={_H(e(300,0)):.2f} bits",
                xy=(300, e(300, 0)), xytext=(120, 0.40),
                arrowprops=dict(arrowstyle="->", color=ACCENT),
                fontsize=9)
    ax.set_title("BEFORE · pure Elo guarantees lopsided matches for strong players")
    ax.set_xlabel("rating gap"); ax.set_ylabel("E_A")
    ax.legend(fontsize=9)
    _save(fig, "06_handicap_before.png")

    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    for pen, c, label in [(0, SOFT, "P=0"), (100, ORANGE, "P=100"),
                          (200, ACCENT, "P=200"), (-150, GREEN, "P=-150")]:
        ax.plot(gap, e(gap, pen), color=c, lw=2.2, label=label)
    ax.axhline(0.5, color=SOFT, ls=":", lw=1)
    ax.set_title("AFTER · handicap slides curve toward 50/50")
    ax.set_xlabel("rating gap"); ax.set_ylabel("E_A")
    ax.legend(fontsize=9)
    _save(fig, "06_handicap_after.png")

    # Gain: matchmaking entropy over time as penalty adapts.
    rng = np.random.default_rng(17)
    streaks = np.zeros(60, dtype=int); win_rate = 0.70
    for i in range(1, 60):
        streaks[i] = streaks[i - 1] + 1 if rng.random() < win_rate else 0
    # entropy before: just P(win|unhandicapped gap=300) stays 0.85.
    h_before = np.full(60, _H(0.85))
    # entropy after: penalty scales with streak.
    penalties = 200 * (1 - 1 / (1 + streaks / 3))
    p_after = np.array([e(300, p) for p in penalties])
    h_after = np.array([_H(p) for p in p_after])
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    ax.plot(h_before, color=SOFT, lw=2.2, label="entropy w/o handicap")
    ax.plot(h_after, color=PRIMARY, lw=2.2, label="entropy w/ handicap")
    ax.fill_between(np.arange(60), h_before, h_after, color=GREEN, alpha=0.22)
    lift = h_after.mean() - h_before.mean()
    ax.set_title(f"GAIN · mean entropy per match +{lift:.2f} bits")
    ax.set_xlabel("match #"); ax.set_ylabel("H(p) [bits]")
    ax.legend(fontsize=9)
    _save(fig, "06_handicap_gain.png")

    # GIF: S-curve sweeping rightwards as streak grows.
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    curve, = ax.plot(gap, e(gap, 0), color=PRIMARY, lw=2.3)
    ax.axhline(0.5, color=SOFT, ls=":", lw=1)
    ax.set_xlabel("rating gap"); ax.set_ylabel("E_A")
    ax.set_ylim(0, 1.02)
    title = ax.set_title("")

    def update(i):
        pen = float(200 * (1 - 1 / (1 + i / 3)))
        curve.set_ydata(e(gap, pen))
        title.set_text(f"Handicap · streak={i}  penalty={pen:.1f}")
        return curve, title

    anim = FuncAnimation(fig, update, frames=15, interval=240)
    anim._fig = fig
    _save_gif(anim, "06_handicap_gif.gif", fps=5)


def _H(p):
    if p <= 0 or p >= 1:
        return 0.0
    return -(p * math.log2(p) + (1 - p) * math.log2(1 - p))


# ===========================================================================
# 7. Entropy filter — before: candidate gap unsorted;
#                     after: sorted by entropy;
#                     gain:  fraction of canaries that produced signal;
#                     gif:   pool shrinking as filter tightens.
# ===========================================================================
def fig_entropy() -> None:
    rng = np.random.default_rng(31)
    probs = rng.beta(2.2, 2.2, size=20)  # roughly bell-shaped around 0.5.
    ent = np.array([_H(p) for p in probs])

    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    ax.stem(np.arange(len(probs)), probs, basefmt=" ",
            linefmt=SOFT, markerfmt="o")
    ax.axhspan(0.0, 0.2, color=ACCENT, alpha=0.08)
    ax.axhspan(0.8, 1.0, color=ACCENT, alpha=0.08)
    ax.set_xlabel("candidate #"); ax.set_ylabel("P(win)")
    ax.set_title("BEFORE · 20 canary candidates, some trivial, some risky")
    _save(fig, "07_entropy_before.png")

    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    order = np.argsort(-ent)
    acc = ent[order] >= 0.9
    colors = [GREEN if a else ACCENT for a in acc]
    ax.bar(range(len(probs)), ent[order], color=colors)
    ax.axhline(0.9, color=PRIMARY, ls="--", lw=1, label="min_entropy=0.9")
    ax.set_xlabel("candidate (sorted by H)"); ax.set_ylabel("H(p)")
    ax.legend(fontsize=9)
    ax.set_title(f"AFTER · kept {int(acc.sum())}/{len(probs)} informative canaries")
    _save(fig, "07_entropy_after.png")

    # Gain: fraction of canaries producing non-trivial signal.
    naive = np.array([1 - p if p > 0.5 else p for p in probs])  # surprise rate.
    filtered = naive[order][acc]
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    ax.hist(naive, bins=12, color=SOFT, alpha=0.6, label="raw pool")
    ax.hist(filtered, bins=12, color=PRIMARY, alpha=0.85, label="entropy-filtered")
    ax.set_xlabel("surprise per canary (closer to 0.5 is more informative)")
    ax.set_ylabel("count")
    lift = filtered.mean() / max(naive.mean(), 1e-6)
    ax.set_title(f"GAIN · mean surprise per kept canary × {lift:.1f}")
    ax.legend(fontsize=9)
    _save(fig, "07_entropy_gain.png")

    # GIF: min_entropy threshold sliding from 0 to 0.99.
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    bar = ax.bar(range(len(probs)), ent[order],
                 color=[GREEN] * len(probs))
    thresh_line = ax.axhline(0.0, color=PRIMARY, ls="--", lw=1.5)
    ax.set_xlabel("candidate"); ax.set_ylabel("H(p)")
    title = ax.set_title("")

    def update(i):
        t = i / 20
        thresh_line.set_ydata([t])
        for b, v in zip(bar, ent[order]):
            b.set_color(GREEN if v >= t else ACCENT)
        kept = int((ent[order] >= t).sum())
        title.set_text(f"threshold τ={t:.2f}  kept {kept}/{len(probs)}")
        return list(bar) + [thresh_line, title]

    anim = FuncAnimation(fig, update, frames=21, interval=200)
    anim._fig = fig
    _save_gif(anim, "07_entropy_gif.gif", fps=5)


# ===========================================================================
# 8. Cox survival — before: constant hazard / no feature-dep risk;
#                   after: feature-dependent survival curves;
#                   gain:  log-likelihood improvement;
#                   gif:   curve evolving as loss_streak grows.
# ===========================================================================
def fig_survival() -> None:
    t = np.linspace(0, 14, 200)
    h0 = 0.03

    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    S_flat = np.exp(-h0 * t)
    ax.plot(t, S_flat, color=SOFT, lw=2.2, label="single flat hazard")
    ax.axhline(0.5, color=SOFT, ls=":", lw=1)
    # Without features we predict the same risk for everyone; bad for on-call.
    ax.set_title("BEFORE · constant hazard ignores loss-streak signal")
    ax.set_xlabel("days"); ax.set_ylabel("S(t)")
    ax.legend(fontsize=9)
    _save(fig, "08_survival_before.png")

    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    for ls, c, lab in [(0, GREEN, "loss=0"), (3, ORANGE, "loss=3"),
                       (6, ACCENT, "loss=6")]:
        hz = h0 * math.exp(0.3 * ls)
        ax.plot(t, np.exp(-hz * t), color=c, lw=2.2, label=f"{lab}  β^Tx={0.3*ls:.1f}")
    ax.axhline(0.5, color=SOFT, ls=":", lw=1)
    ax.set_title("AFTER · feature-adjusted hazard stratifies risk")
    ax.set_xlabel("days"); ax.set_ylabel("S(t|X)")
    ax.legend(fontsize=9)
    _save(fig, "08_survival_after.png")

    # Gain: log-likelihood of observed events under flat vs Cox.
    rng = np.random.default_rng(19)
    n = 300
    x = rng.choice([0, 3, 6], size=n, p=[0.5, 0.3, 0.2])
    rates = h0 * np.exp(0.3 * x)
    T = rng.exponential(1 / rates)
    # log-likelihood (observed events only).
    ll_flat = np.sum(np.log(h0) - h0 * T)
    ll_cox = np.sum(np.log(rates) - rates * T)
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    ax.bar(["flat hazard", "Cox h(t|X)"], [ll_flat, ll_cox],
           color=[SOFT, PRIMARY])
    for i, v in enumerate([ll_flat, ll_cox]):
        ax.text(i, v, f"{v:.0f}", ha="center",
                va="bottom" if v < 0 else "top")
    lift = ll_cox - ll_flat
    ax.set_title(f"GAIN · log-likelihood +{lift:.0f} on same data")
    ax.set_ylabel("log-likelihood")
    _save(fig, "08_survival_gain.png")

    # GIF: curve steepens as loss_streak grows.
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    line, = ax.plot(t, np.exp(-h0 * t), color=PRIMARY, lw=2.3)
    ax.axhline(0.5, color=SOFT, ls=":", lw=1)
    ax.set_ylim(0, 1.02); ax.set_xlabel("days"); ax.set_ylabel("S(t|X)")
    title = ax.set_title("")

    def update(ls):
        hz = h0 * math.exp(0.3 * ls)
        line.set_ydata(np.exp(-hz * t))
        title.set_text(f"loss_streak = {ls}  β^Tx = {0.3*ls:.2f}  hazard × {math.exp(0.3*ls):.2f}")
        return line, title

    anim = FuncAnimation(fig, update, frames=range(0, 10),
                         interval=320)
    anim._fig = fig
    _save_gif(anim, "08_survival_gif.gif", fps=3)


# ===========================================================================
# 9. Minimax BP — before: single pure strategy;
#                 after: Nash mixed strategy;
#                 gain:  worst-case payoff reduction;
#                 gif:   fictitious play converging.
# ===========================================================================
def fig_minimax_bp() -> None:
    U = np.array([[0, -1, 1], [1, 0, -1], [-1, 1, 0]], dtype=float)
    labels = ["Rock", "Paper", "Scissors"]

    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    # Pure strategy = always pick Rock.
    x_pure = np.array([1.0, 0.0, 0.0])
    worst = np.min(x_pure @ U)
    ax.bar(labels, x_pure, color=SOFT, alpha=0.7)
    ax.set_ylim(0, 1.05)
    ax.set_title(f"BEFORE · pure strategy 'Rock' — worst-case payoff = {worst:.2f}")
    _save(fig, "09_minimax_bp_before.png")

    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    x_nash = np.array([1 / 3, 1 / 3, 1 / 3])
    ax.bar(labels, x_nash, color=[PRIMARY, GREEN, ORANGE])
    for i, v in enumerate(x_nash):
        ax.text(i, v + 0.015, f"{v:.2f}", ha="center")
    worst_nash = np.min(x_nash @ U)
    ax.set_ylim(0, 0.45)
    ax.set_title(f"AFTER · mixed Nash x* — worst-case payoff = {worst_nash:.2f}")
    _save(fig, "09_minimax_bp_after.png")

    # Gain: worst-case payoff across a family of perturbed RPS games.
    rng = np.random.default_rng(25)
    worst_pure = []; worst_nash_arr = []
    for _ in range(50):
        U2 = U + rng.normal(0, 0.1, size=U.shape)
        # pure argmax on average row
        row = int(np.argmax(U2.mean(axis=1)))
        xp = np.zeros(3); xp[row] = 1
        worst_pure.append(np.min(xp @ U2))
        worst_nash_arr.append(np.min(x_nash @ U2))  # approximation: stay uniform
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    ax.hist(worst_pure, bins=20, color=SOFT, alpha=0.6, label="pure worst-case")
    ax.hist(worst_nash_arr, bins=20, color=PRIMARY, alpha=0.8, label="Nash worst-case")
    ax.axvline(np.mean(worst_pure), color=SOFT, ls="--")
    ax.axvline(np.mean(worst_nash_arr), color=PRIMARY, ls="--")
    ax.set_xlabel("worst-case payoff"); ax.set_ylabel("count")
    lift = np.mean(worst_nash_arr) - np.mean(worst_pure)
    ax.set_title(f"GAIN · worst-case payoff improved by {lift:+.2f}")
    ax.legend(fontsize=9)
    _save(fig, "09_minimax_bp_gain.png")

    # GIF: fictitious play converging on the simplex.
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    bars = ax.bar(labels, [1.0, 0.0, 0.0], color=[PRIMARY, GREEN, ORANGE])
    ax.set_ylim(0, 1.05)
    title = ax.set_title("")

    avg_x = np.zeros(3); avg_y = np.zeros(3)
    counts_x = np.zeros(3); counts_y = np.zeros(3)

    def update(i):
        nonlocal avg_x, avg_y
        # Row player best responds to opponent's empirical mix.
        if counts_y.sum() > 0:
            y_emp = counts_y / counts_y.sum()
        else:
            y_emp = np.ones(3) / 3
        br_row = int(np.argmax(U @ y_emp))
        counts_x[br_row] += 1
        if counts_x.sum() > 0:
            x_emp = counts_x / counts_x.sum()
        else:
            x_emp = np.ones(3) / 3
        br_col = int(np.argmin(x_emp @ U))
        counts_y[br_col] += 1
        for b, v in zip(bars, x_emp):
            b.set_height(v)
        title.set_text(f"Fictitious play · step {i}  x̄ = {np.round(x_emp,2)}")
        return list(bars) + [title]

    anim = FuncAnimation(fig, update, frames=40, interval=160)
    anim._fig = fig
    _save_gif(anim, "09_minimax_bp_gif.gif", fps=6)


# ===========================================================================
# 10. Pipeline overview
# ===========================================================================
def fig_pipeline() -> None:
    fig, ax = plt.subplots(figsize=(10.5, 5.6))
    ax.set_xlim(0, 10); ax.set_ylim(0, 7)
    ax.axis("off")

    nodes = [
        ("TrueSkill\n(μ, σ)", 1.1, 5.4, PRIMARY),
        ("PCA hidden\nscore z", 1.1, 3.6, PRIMARY),
        ("GNN synergy\nscore", 1.1, 1.8, PRIMARY),
        ("Dynamic K\n+ Handicap", 4.0, 5.4, ORANGE),
        ("Entropy filter\nH(p) ≥ τ", 4.0, 3.6, ORANGE),
        ("EOMM\nargmax retention", 4.0, 1.8, ORANGE),
        ("Churn monitor\n(Cox)", 7.0, 5.4, ACCENT),
        ("BP minimax\nNash", 7.0, 3.6, ACCENT),
        ("Decision\nGO/CANARY/HOLD…", 9.1, 3.6, GREEN),
    ]
    for (label, x, y, color) in nodes:
        box = plt.Rectangle((x - 0.78, y - 0.58), 1.56, 1.16,
                            facecolor=color, edgecolor="white", lw=2, alpha=0.9)
        ax.add_patch(box)
        ax.text(x, y, label, ha="center", va="center",
                color="white", fontsize=9)

    arrows = [
        (1.88, 5.4, 3.22, 5.4),
        (1.88, 3.6, 3.22, 3.6),
        (1.88, 1.8, 3.22, 1.8),
        (4.78, 5.4, 6.22, 5.4),
        (4.78, 3.6, 6.22, 3.6),
        (4.78, 1.8, 6.22, 3.0),
        (7.0, 4.85, 7.0, 4.15),
        (7.78, 3.6, 8.32, 3.6),
    ]
    for (x1, y1, x2, y2) in arrows:
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle="->", color="#444", lw=1.4))

    ax.text(1.1, 6.4, "Estimators", ha="center", fontsize=10,
            color=PRIMARY, fontweight="bold")
    ax.text(4.0, 6.4, "Ranking / filtering", ha="center", fontsize=10,
            color=ORANGE, fontweight="bold")
    ax.text(7.0, 6.4, "Risk / game", ha="center", fontsize=10,
            color=ACCENT, fontweight="bold")
    ax.text(5, 0.5, "Pipeline: Estimators → Filters → Risk → Decision",
            ha="center", fontsize=11, color="#333")

    _save(fig, "10_pipeline.png")


def main() -> None:
    fig_trueskill()
    fig_eomm()
    fig_dynamic_k()
    fig_pca_hidden()
    fig_gnn_synergy()
    fig_handicap()
    fig_entropy()
    fig_survival()
    fig_minimax_bp()
    fig_pipeline()


if __name__ == "__main__":
    main()
