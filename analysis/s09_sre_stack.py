"""§SRE · end-to-end stack — before vs after on a simulated incident.

Scenario
--------
300 s of synthetic service traffic with two injected incidents:

    t ∈ [60, 80]   — brown-out: latency p99 spikes ×3, must NOT scale up
    t ∈ [180, 200] — traffic surge: RPS doubles, MUST scale up

Baseline
--------
Reactive HPA mimic: scale when observed RPS > capacity, no prediction,
no fusion, no guardrail, pinv-based load balancing.

After
-----
Full :class:`SREControlStack` — fusion + MPC + canary + guardrail +
bounded LS allocation.

Metrics
-------
- SLO violation rate (% of ticks where latency p99 > budget)
- over-provisioning (mean replicas minus demand-driven minimum)
- peak replicas during surge
"""

from __future__ import annotations

import numpy as np

from sre_control import (FastTrafficSwitcher, Instance, PoolCapacityPlanner,
                          PredictiveAutoscaler, Signal, SignalFusion,
                          SLOGuardrail, SREControlStack, WeightedLoadBalancer,
                          CanaryScheduler)

from analysis._common import HAS_MPL, save_fig, summary_banner


def _true_rps(t: float) -> float:
    base = 1200 + 400 * np.sin(t / 40)
    if 180 <= t <= 200:
        base *= 2.0
    return base


def _true_latency(t: float, replicas: int, rps: float) -> float:
    """Simple queueing-style latency model.

    Per-replica load ``ρ = rps / (replicas · capacity)`` drives latency
    as ``1 / (1 − ρ)`` — classic M/M/1. Near ρ = 1 latency blows up.
    """
    capacity_per_replica = 110.0
    rho = rps / max(replicas, 1) / capacity_per_replica
    rho = min(rho, 0.98)
    lat = 18.0 + 12.0 * rho / max(1e-3, 1.0 - rho)
    if 60 <= t <= 80:
        lat += 40.0                       # brown-out spike
    return lat


def _baseline_run(t_grid: np.ndarray) -> dict:
    """Reactive HPA: scale on observed latency only, no prediction.

    Mirrors Kubernetes default HPA behaviour: single-step response,
    conflates any latency spike (real load or brown-out) as capacity
    demand.
    """
    replicas = 15
    slo_budget = 60.0
    rng = np.random.default_rng(0)
    replicas_trace, lat_trace, rps_trace = [], [], []
    slo_violations = 0
    for t in t_grid:
        rps = _true_rps(t) + rng.normal(0, 30)
        lat = _true_latency(t, replicas, rps)
        # React on latency breach — +1 replica per tick (typical HPA)
        if lat > slo_budget:
            replicas = min(replicas + 1, 50)
        elif lat < 0.5 * slo_budget:
            replicas = max(replicas - 1, 4)
        replicas_trace.append(replicas)
        lat_trace.append(lat)
        rps_trace.append(rps)
        if lat > slo_budget:
            slo_violations += 1
    return {
        "replicas": np.array(replicas_trace),
        "lat":      np.array(lat_trace),
        "rps":      np.array(rps_trace),
        "slo_violations": slo_violations,
        "slo_violation_pct": 100.0 * slo_violations / len(t_grid),
        "mean_replicas": float(np.mean(replicas_trace)),
        "peak_replicas": int(np.max(replicas_trace)),
    }


def _after_run(t_grid: np.ndarray) -> dict:
    rng = np.random.default_rng(0)
    slo_budget = 60.0

    fusion = SignalFusion(
        x0=np.array([1200.0, 25.0, 0.3]),
        P0=np.diag([200**2, 10**2, 0.2**2]),
        Q=np.diag([5.0, 0.2, 0.01]),
        x_ref=np.array([1200.0, 25.0, 0.3]),
        theta=0.1,
    )
    metrics = Signal(
        "metrics",
        h=lambda x: x[0:2],
        H=lambda x: np.array([[1, 0, 0], [0, 1, 0]]),
        R=np.diag([50**2, 4**2]))

    asc = PredictiveAutoscaler(per_replica_rps=100.0,
                                replicas_min=4, replicas_max=50,
                                max_step=8, dt=5.0, horizon=10,
                                q_slo=150.0, r_cost=0.5)
    guard = SLOGuardrail(
        nominal_direction=np.array([0.6, 0.4, 0]),
        theta_max_deg=15.0, magnitude_cap=5_000.0)
    lb = WeightedLoadBalancer(instances=[
        Instance("east", np.array([1, 0.0]), 20, 1500),
        Instance("west", np.array([0, 1.0]), 20, 1500),
    ])
    stack = SREControlStack(fusion=fusion, autoscaler=asc, guardrail=guard,
                             balancer=lb)

    replicas = 15
    replicas_trace, lat_trace, rps_trace = [], [], []
    slo_violations = 0
    for t in t_grid:
        rps = _true_rps(t) + rng.normal(0, 30)
        lat = _true_latency(t, replicas, rps)
        # 20 s look-ahead forecast with small noise — gives the stack an
        # honest predictive edge over reactive HPA
        forecast = _true_rps(t + 20) + rng.normal(0, 10)
        stack.step(
            dt=5.0,
            sensor_readings=[(metrics, np.array([rps, lat]))],
            forecast_rps=forecast,
            current_replicas=replicas,
            zone_target=np.array([rps * 0.6, rps * 0.4]),
            nn_proposal=np.array([rps * 0.55, rps * 0.45, rng.normal(0, 20)]),
        )
        replicas = stack.trace[-1]["replicas_next"]

        replicas_trace.append(replicas)
        lat_trace.append(lat)
        rps_trace.append(rps)
        if lat > slo_budget:
            slo_violations += 1

    return {
        "replicas": np.array(replicas_trace),
        "lat":      np.array(lat_trace),
        "rps":      np.array(rps_trace),
        "slo_violations": slo_violations,
        "slo_violation_pct": 100.0 * slo_violations / len(t_grid),
        "mean_replicas": float(np.mean(replicas_trace)),
        "peak_replicas": int(np.max(replicas_trace)),
    }


def main() -> dict:
    t_grid = np.arange(0, 300, 5.0)
    base = _baseline_run(t_grid)
    after = _after_run(t_grid)

    before_metrics = {
        "slo_violation_pct": base["slo_violation_pct"],
        "mean_replicas":     base["mean_replicas"],
        "peak_replicas":     float(base["peak_replicas"]),
    }
    after_metrics = {
        "slo_violation_pct": after["slo_violation_pct"],
        "mean_replicas":     after["mean_replicas"],
        "peak_replicas":     float(after["peak_replicas"]),
    }

    banner = summary_banner("§SRE · end-to-end stack",
                             before_metrics, after_metrics)
    print(banner)

    if HAS_MPL:
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(3, 1, figsize=(11, 7), sharex=True)

        axes[0].plot(t_grid, base["rps"], color="#6a7889", lw=1, alpha=0.6,
                     label="observed RPS")
        axes[0].axvspan(60, 80, color="#fbf1ed", alpha=0.7)
        axes[0].axvspan(180, 200, color="#fbf1ed", alpha=0.7)
        axes[0].text(70, 0.95 * axes[0].get_ylim()[1], "brown-out",
                     ha="center", fontsize=9, color="#b4411b")
        axes[0].text(190, 0.95 * axes[0].get_ylim()[1], "surge",
                     ha="center", fontsize=9, color="#b4411b")
        axes[0].set_ylabel("RPS"); axes[0].legend(loc="upper right")

        axes[1].plot(t_grid, base["replicas"], color="#b4411b", lw=1.8,
                     label="baseline HPA")
        axes[1].plot(t_grid, after["replicas"], color="#1f5fa3", lw=1.8,
                     label="stack")
        axes[1].set_ylabel("replicas"); axes[1].legend()

        axes[2].plot(t_grid, base["lat"], color="#b4411b", lw=1.8,
                     label="baseline latency")
        axes[2].plot(t_grid, after["lat"], color="#1f5fa3", lw=1.8,
                     label="stack latency")
        axes[2].axhline(60, color="#2f7d3a", lw=1, ls="--",
                        label="SLO budget")
        axes[2].set_xlabel("t [s]"); axes[2].set_ylabel("p99 latency [ms]")
        axes[2].legend()
        # Also save into docs/assets so the knowledge-base HTML picks it up
        from pathlib import Path
        docs_assets = Path(__file__).resolve().parent.parent / "docs" / "assets"
        docs_assets.mkdir(parents=True, exist_ok=True)
        fig.savefig(docs_assets / "s09_sre_stack.png", dpi=130,
                    bbox_inches="tight")
        save_fig(fig, "s09_sre_stack")
        plt.close(fig)

    return {"before": before_metrics, "after": after_metrics, "banner": banner}


if __name__ == "__main__":
    main()
