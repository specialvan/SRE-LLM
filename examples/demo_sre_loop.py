"""End-to-end SRE control loop: 60 s of simulated service traffic.

Chains every adapter from :mod:`sre_control` into a single ``step()``
call and prints a condensed trace. Meant to be readable by a new SRE
teammate so they can see "what does each math module actually do on
my service".
"""

from __future__ import annotations

import numpy as np

from sre_control import (CanaryScheduler, FastTrafficSwitcher, Instance,
                          PoolCapacityPlanner, PredictiveAutoscaler,
                          Signal, SignalFusion, SLOGuardrail,
                          SREControlStack, WeightedLoadBalancer)


def main() -> None:
    rng = np.random.default_rng(1)

    # --- 1) pool planner (§1) --------------------------------------------
    pool = PoolCapacityPlanner(min_keep_alive=8, max_capacity=250)
    pool_plan, pool_info = pool.plan(
        demand_rps_forecast=[1000 + 300 * np.sin(i/5.0) for i in range(12)])
    print(f"§1 pool saving vs on/off baseline: "
          f"{pool_info['cost_saving_pct']:+.1f}%")

    # --- 2) fusion (§5) -------------------------------------------------
    fusion = SignalFusion(
        x0=np.array([1000.0, 25.0, 0.3]),
        P0=np.diag([200**2, 10**2, 0.2**2]),
        Q=np.diag([5.0, 0.2, 0.01]),
        x_ref=np.array([1200.0, 30.0, 0.4]),
        theta=0.15,
    )
    metrics = Signal(
        "metrics",
        h=lambda x: x[0:2],
        H=lambda x: np.array([[1, 0, 0], [0, 1, 0]]),
        R=np.diag([50**2, 4**2]))
    tracing = Signal(
        "tracing",
        h=lambda x: np.array([x[1]]),
        H=lambda x: np.array([[0, 1, 0]]),
        R=np.array([[2.0**2]]))

    # --- 3) autoscaler (§6) ---------------------------------------------
    asc = PredictiveAutoscaler(per_replica_rps=100.0,
                                replicas_min=4, replicas_max=50,
                                max_step=3, dt=5.0, horizon=10)

    # --- 4) canary (§2) -------------------------------------------------
    canary = CanaryScheduler(slo_error_budget=0.01, eta_init=0.05)

    # --- 5) guardrail (§4) -----------------------------------------------
    guard = SLOGuardrail(
        nominal_direction=np.array([0.5, 0.5, 0.0]),
        theta_max_deg=10.0,
        magnitude_cap=2000.0)

    # --- 6) balancer (§8) ------------------------------------------------
    lb = WeightedLoadBalancer(instances=[
        Instance("east-a", np.array([1.0, 0.0]), 20, 800),
        Instance("east-b", np.array([1.0, 0.0]), 20, 800),
        Instance("west-a", np.array([0.0, 1.0]), 20, 800),
        Instance("west-b", np.array([0.0, 1.0]), 20, 800),
    ])

    # --- wire the stack --------------------------------------------------
    stack = SREControlStack(
        fusion=fusion, autoscaler=asc, guardrail=guard,
        balancer=lb, canary=canary,
        switcher=FastTrafficSwitcher(rate_max=0.4), pool=pool)

    # --- 60 s loop, 5 s ticks -------------------------------------------
    current_replicas = 10
    canary_share = 0.0
    t_grid = np.arange(0, 60, 5.0)
    print("\nt   | repl  | canary% | rps_obs | safe_action         | "
          "shares (east-a,east-b,west-a,west-b)")
    print("-" * 96)
    for t in t_grid:
        forecast_rps = 1000 + 500 * np.sin(t / 20)
        observed_rps = forecast_rps + rng.normal(0, 40)
        canary_err = 0.008 if canary_share < 0.5 else 0.012

        # NN proposal — could be an ML-driven routing suggestion
        nn_proposal = np.array([
            forecast_rps * 0.55,
            forecast_rps * 0.45,
            rng.normal(0, 30),
        ])
        sensor_readings = [
            (metrics, np.array([observed_rps, 25 + 5 * np.sin(t / 10)])),
            (tracing, np.array([26 + 4 * np.sin(t / 10 + 0.3)])),
        ]

        entry = stack.step(
            dt=5.0,
            sensor_readings=sensor_readings,
            forecast_rps=forecast_rps,
            current_replicas=current_replicas,
            zone_target=np.array([forecast_rps * 0.6, forecast_rps * 0.4]),
            nn_proposal=nn_proposal,
            current_canary_share=canary_share,
            canary_observed_error=canary_err,
        )
        current_replicas = entry["replicas_next"]
        if entry["canary"] and entry["canary"]["accepted"]:
            canary_share = entry["canary"]["to_pct"]

        shares = entry["alloc_shares"]
        print(f"{t:3.0f}s | {current_replicas:4d}  | "
              f"{canary_share*100:5.1f}% | {observed_rps:7.0f} | "
              f"[{entry['guardrail']['approved'][0]:7.0f} "
              f"{entry['guardrail']['approved'][1]:7.0f} "
              f"{entry['guardrail']['approved'][2]:7.0f}] | "
              f"[{shares[0]:5.0f} {shares[1]:5.0f} "
              f"{shares[2]:5.0f} {shares[3]:5.0f}]")

    print("\nStack produced", len(stack.trace), "trace entries.")


if __name__ == "__main__":
    main()
