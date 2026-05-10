"""§8 Chopstick-catch thrust allocation — before vs after.

Baseline : equal-share allocation — split the desired force/torque
           among thrusters with no geometry awareness.
After    : :class:`ThrustAllocator.allocate` solves the bounded least
           squares ``min ‖A t − wrench‖² s.t. t_min ≤ t ≤ t_max``.

Metrics :
    - wrench reconstruction error ‖A t − demand‖
    - max per-thruster saturation violation
    - number of infeasible demands (baseline only — exceeds bounds)
"""

from __future__ import annotations

import numpy as np

from starship.catch_controller import ThrustAllocator
from starship.types import Thruster, ThrusterBank
from analysis._common import HAS_MPL, save_fig, summary_banner


def _default_bank() -> ThrusterBank:
    th: list[Thruster] = []
    R = 3.2
    for i in range(3):
        a = i * 2 * np.pi / 3
        th.append(Thruster(
            position=np.array([R * np.cos(a), R * np.sin(a), 0.0]),
            direction=np.array([0.0, 0.0, 1.0]),
            T_min=0.4e6, T_max=2.3e6))
    return ThrusterBank(th)


def main(n_demands: int = 400, seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    bank = _default_bank()
    allocator = ThrustAllocator(bank)
    A = bank.geometry_matrix()

    # Random wrenches : force ≈ vertical around 3*m*g ≈ 5 MN
    F = np.stack([
        rng.normal([0, 0, 5e6], [2e5, 2e5, 1e6]) for _ in range(n_demands)
    ])
    tau = rng.normal(0, 2e6, size=(n_demands, 3))

    base_res = []; base_sat = []
    aft_res = []; aft_sat = []
    for f, t in zip(F, tau):
        demand = np.concatenate([f, t])
        # Baseline : equal split for force, torque via naive pseudoinverse
        # with *no* bounds check.
        t_equal = np.linalg.pinv(A) @ demand
        base_res.append(np.linalg.norm(A @ t_equal - demand))
        base_sat.append(max(0.0, float(
            np.max(np.concatenate([t_equal - np.array([th.T_max for th in bank]),
                                    np.array([th.T_min for th in bank]) - t_equal]))
        )))
        # After : bounded LS
        t_opt, r = allocator.allocate(f, t)
        aft_res.append(r)
        aft_sat.append(max(0.0, float(
            np.max(np.concatenate([t_opt - np.array([th.T_max for th in bank]),
                                    np.array([th.T_min for th in bank]) - t_opt]))
        )))

    base_res = np.array(base_res); base_sat = np.array(base_sat)
    aft_res = np.array(aft_res); aft_sat = np.array(aft_sat)

    before = {
        "mean_residual": float(base_res.mean()),
        "max_residual":  float(base_res.max()),
        "saturation_violation_pct": float(np.mean(base_sat > 1e-6) * 100),
        "mean_saturation_excess":   float(base_sat.mean()),
    }
    after = {
        "mean_residual": float(aft_res.mean()),
        "max_residual":  float(aft_res.max()),
        "saturation_violation_pct": float(np.mean(aft_sat > 1e-6) * 100),
        "mean_saturation_excess":   float(aft_sat.mean()),
    }

    banner = summary_banner("§8 Catch-phase thrust allocation", before, after)
    print(banner)

    if HAS_MPL:
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(1, 2, figsize=(10, 4))
        axes[0].hist(base_res, bins=30, alpha=0.5, label="baseline")
        axes[0].hist(aft_res,  bins=30, alpha=0.5, label="bounded LS")
        axes[0].set_xlabel("‖A·t − demand‖"); axes[0].set_ylabel("count")
        axes[0].set_title("wrench reconstruction error")
        axes[0].legend(); axes[0].grid(True, alpha=0.3)

        axes[1].hist(base_sat, bins=30, alpha=0.5, label="baseline")
        axes[1].hist(aft_sat,  bins=30, alpha=0.5, label="bounded LS")
        axes[1].set_xlabel("saturation excess [N]")
        axes[1].set_ylabel("count")
        axes[1].set_title("thruster bound violation")
        axes[1].legend(); axes[1].grid(True, alpha=0.3)
        save_fig(fig, "s08_catch_allocation")
        plt.close(fig)

    return {"before": before, "after": after, "banner": banner}


if __name__ == "__main__":
    main()
