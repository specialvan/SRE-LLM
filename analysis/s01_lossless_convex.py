"""§1 Lossless convexification — before vs after.

Baseline  : fixed-throttle open-loop descent (engine at ρ2 the whole way).
After     : SLSQP-solved PDG that respects the pointing cone + throttle
            envelope and maximises final mass.

Metrics compared :
    - terminal position error ‖r(T) − rf‖
    - terminal speed          ‖v(T) − vf‖
    - fuel burned             m0 − m(T)
    - worst-case cone margin  min(n̂ᵀΓ − ‖Γ‖·cos θ_max)
"""

from __future__ import annotations

import time

import numpy as np

from starship.lossless_convex import LosslessPDG

from analysis._common import HAS_MPL, save_fig, summary_banner


def _fixed_throttle_rollout(pdg: LosslessPDG) -> dict:
    """Baseline: fire straight up at ρ2 for the whole horizon."""
    G = np.zeros((pdg.N, 3))
    G[:, 2] = pdg.rho2
    r, v, m = pdg._dynamics_rollout(G)
    cos_t = float(np.cos(np.deg2rad(pdg.theta_max_deg)))
    margins = np.array([pdg.n_hat @ g - np.linalg.norm(g) * cos_t for g in G])
    return {
        "pos_err": float(np.linalg.norm(r[-1] - pdg.rf)),
        "vel_err": float(np.linalg.norm(v[-1] - pdg.vf)),
        "fuel":    float(pdg.m0 - m[-1]),
        "cone_margin_min": float(margins.min()),
        "r_traj": r, "v_traj": v, "Gamma": G,
    }


def _solve_pdg(pdg: LosslessPDG) -> dict:
    r, v, G, info = pdg.solve()
    return {
        "pos_err": float(np.linalg.norm(r[-1] - pdg.rf)),
        "vel_err": float(np.linalg.norm(v[-1] - pdg.vf)),
        "fuel":    float(pdg.m0 - info["m_final"]),
        "cone_margin_min": float(info["cone_margin_min"]),
        "r_traj": r, "v_traj": v, "Gamma": G,
        "solver_ok": info["success"],
    }


def main() -> dict:
    pdg = LosslessPDG(
        r0=np.array([0.0, 0.0, 300.0]),
        v0=np.array([0.0, 0.0, -80.0]),
        rf=np.zeros(3),
        vf=np.zeros(3),
        m0=250_000.0,           # ~empty Super Heavy
        T=6.0,
        N=20,
    )
    t0 = time.time()
    base = _fixed_throttle_rollout(pdg)
    t1 = time.time()
    after = _solve_pdg(pdg)
    t2 = time.time()

    before_metrics = {k: base[k] for k in ("pos_err", "vel_err", "fuel", "cone_margin_min")}
    after_metrics  = {k: after[k] for k in ("pos_err", "vel_err", "fuel", "cone_margin_min")}
    before_metrics["solve_ms"] = 1000 * (t1 - t0)
    after_metrics["solve_ms"]  = 1000 * (t2 - t1)

    banner = summary_banner("§1 Lossless Convexification", before_metrics, after_metrics)
    print(banner)

    if HAS_MPL:
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(1, 2, figsize=(10, 4))
        t_base = np.linspace(0, pdg.T, base["r_traj"].shape[0])
        t_aft = np.linspace(0, pdg.T, after["r_traj"].shape[0])

        axes[0].plot(t_base, base["r_traj"][:, 2], label="baseline (ρ2 fixed)")
        axes[0].plot(t_aft,  after["r_traj"][:, 2], label="PDG (lossless cvx)")
        axes[0].axhline(0, color="k", lw=0.5)
        axes[0].set_xlabel("t [s]"); axes[0].set_ylabel("altitude z [m]")
        axes[0].set_title("altitude profile")
        axes[0].legend(); axes[0].grid(True, alpha=0.3)

        axes[1].plot(t_base, base["v_traj"][:, 2], label="baseline")
        axes[1].plot(t_aft,  after["v_traj"][:, 2], label="PDG")
        axes[1].set_xlabel("t [s]"); axes[1].set_ylabel("v_z [m/s]")
        axes[1].set_title("vertical speed")
        axes[1].legend(); axes[1].grid(True, alpha=0.3)
        save_fig(fig, "s01_lossless_convex")
        plt.close(fig)

    return {"before": before_metrics, "after": after_metrics, "banner": banner}


if __name__ == "__main__":
    main()
