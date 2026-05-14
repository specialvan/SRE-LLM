from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime

import numpy as np

from sre_control import (
    CanaryScheduler,
    FastTrafficSwitcher,
    Instance,
    PoolCapacityPlanner,
    PredictiveAutoscaler,
    Signal,
    SignalFusion,
    SLOGuardrail,
    SREControlStack,
    WeightedLoadBalancer,
)


def _build_stack() -> tuple[SREControlStack, PoolCapacityPlanner, Signal, Signal]:
    pool = PoolCapacityPlanner(min_keep_alive=8, max_capacity=250)
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
        R=np.diag([50**2, 4**2]),
        gate_threshold=3.2,
    )
    tracing = Signal(
        "tracing",
        h=lambda x: np.array([x[1]]),
        H=lambda x: np.array([[0, 1, 0]]),
        R=np.array([[2.0**2]]),
        gate_threshold=4.0,
    )
    asc = PredictiveAutoscaler(
        per_replica_rps=100.0,
        replicas_min=4,
        replicas_max=50,
        max_step=3,
        dt=5.0,
        horizon=10,
    )
    canary = CanaryScheduler(slo_error_budget=0.01, eta_init=0.05)
    guard = SLOGuardrail(
        nominal_direction=np.array([0.55, 0.45, 0.0]),
        theta_max_deg=10.0,
        magnitude_cap=2200.0,
    )
    lb = WeightedLoadBalancer(
        instances=[
            Instance("east-a", np.array([1.0, 0.0]), 20, 800),
            Instance("east-b", np.array([1.0, 0.0]), 20, 800),
            Instance("west-a", np.array([0.0, 1.0]), 20, 800),
            Instance("west-b", np.array([0.0, 1.0]), 20, 800),
        ]
    )
    stack = SREControlStack(
        fusion=fusion,
        autoscaler=asc,
        guardrail=guard,
        balancer=lb,
        canary=canary,
        switcher=FastTrafficSwitcher(rate_max=0.4),
        pool=pool,
    )
    return stack, pool, metrics, tracing


def _round_series(values: list[float]) -> list[float]:
    return [round(float(value), 2) for value in values]


def _stage_rollup(timeline: list[dict]) -> list[dict]:
    counter: Counter[str] = Counter()
    for row in timeline:
        counter.update(row["states"])
    return [
        {"state": state, "count": count}
        for state, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


def build_control_center_payload() -> dict:
    rng = np.random.default_rng(7)
    stack, pool, metrics, tracing = _build_stack()
    current_replicas = 10
    canary_share = 0.0
    timeline: list[dict] = []
    event_counter: Counter[str] = Counter()
    event_log: list[dict] = []
    observed_rps_series: list[float] = []
    forecast_rps_series: list[float] = []
    replicas_series: list[int] = []
    pool_series: list[int] = []
    latest_entry = None

    demand_forecast = [1000 + 300 * np.sin(i / 5.0) for i in range(12)]
    pool_plan, pool_info = pool.plan(demand_forecast)

    for tick, t in enumerate(np.arange(0, 60, 5.0)):
        forecast_rps = float(1000 + 500 * np.sin(t / 20))
        observed_rps = float(forecast_rps + rng.normal(0, 40))
        latency = float(25 + 5 * np.sin(t / 10))
        canary_err = 0.008 if canary_share < 0.5 else 0.012
        nn_proposal = np.array(
            [
                forecast_rps * 0.55,
                forecast_rps * 0.45,
                rng.normal(0, 30),
            ]
        )
        sensor_readings = [
            (metrics, np.array([observed_rps, latency])),
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
        latest_entry = entry
        current_replicas = entry["replicas_next"]
        if entry["canary"] and entry["canary"]["accepted"]:
            canary_share = entry["canary"]["to_pct"]

        runtime_events = entry["runtime"]["events"]
        event_details = []
        for event in runtime_events:
            event_counter[event["kind"]] += 1
            detail = {
                "tick": tick,
                "time_s": float(t),
                "stage": event["stage"],
                "kind": event["kind"],
                "detail": event["detail"],
                "safe_action": event["safe_action"],
            }
            event_details.append(detail)
            event_log.append(detail)

        posterior_state = entry["state"].get("x") or [0.0, 0.0, 0.0]
        timeline.append(
            {
                "tick": tick,
                "time_s": float(t),
                "forecast_rps": round(forecast_rps, 2),
                "observed_rps": round(observed_rps, 2),
                "replicas_next": int(entry["replicas_next"]),
                "degraded": bool(entry["runtime"]["degraded"]),
                "states": entry["runtime"]["states"],
                "events": [event["kind"] for event in runtime_events],
                "event_details": event_details,
                "alloc_shares": [round(float(share), 2) for share in entry["alloc_shares"]],
                "pool_connections": int(pool_plan[tick]),
                "posterior_qps": round(float(posterior_state[0]), 2),
                "posterior_latency": round(float(posterior_state[1]), 2),
                "guardrail_projection_distance": round(
                    float(entry["guardrail"]["projection_distance"]), 4
                ),
            }
        )
        observed_rps_series.append(observed_rps)
        forecast_rps_series.append(forecast_rps)
        replicas_series.append(entry["replicas_next"])
        pool_series.append(pool_plan[tick])

    degraded_ticks = sum(1 for row in timeline if row["degraded"])
    latest_state = (
        latest_entry["state"] if latest_entry else {"x": [0.0, 0.0, 0.0], "P_trace": 0.0}
    )
    latest_guardrail = (
        latest_entry["guardrail"]
        if latest_entry
        else {"projection_distance": 0.0, "local_states": []}
    )
    latest_alloc = (
        latest_entry["alloc_info"]
        if latest_entry
        else {"rps_residual": 0.0, "local_states": []}
    )
    latest_canary = latest_entry["canary"] if latest_entry else None
    latest_shares = latest_entry["alloc_shares"] if latest_entry else []

    adapters = [
        {
            "id": "pool-planner",
            "label": "Pool Capacity Planner",
            "metric": f"{pool_plan[-1]} conns",
            "detail": f"capacity shortfall {pool_info['capacity_shortfall_rps']:.1f} rps",
            "status": "attention" if pool_info["capacity_shortfall_rps"] > 0 else "healthy",
        },
        {
            "id": "signal-fusion",
            "label": "Signal Fusion",
            "metric": f"P-trace {latest_state['P_trace']:.2f}",
            "detail": f"posterior qps {latest_state['x'][0]:.1f}",
            "status": "healthy",
        },
        {
            "id": "predictive-autoscaler",
            "label": "Predictive Autoscaler",
            "metric": f"next {latest_entry['replicas_next']} replicas",
            "detail": f"current {latest_entry['replicas_current']} → next {latest_entry['replicas_next']}",
            "status": "attention"
            if any(state.startswith("DEGRADED_PLAN") for state in latest_entry["runtime"]["states"])
            else "healthy",
        },
        {
            "id": "canary-scheduler",
            "label": "Canary Scheduler",
            "metric": f"{canary_share * 100:.1f}%",
            "detail": (
                f"trust region {latest_canary['trust_region']:.3f}"
                if latest_canary
                else "no canary decision in latest tick"
            ),
            "status": "attention" if latest_canary and not latest_canary["accepted"] else "healthy",
        },
        {
            "id": "slo-guardrail",
            "label": "SLO Guardrail",
            "metric": f"Δ {latest_guardrail['projection_distance']:.2f}",
            "detail": ", ".join(latest_guardrail["local_states"]),
            "status": "attention" if latest_guardrail["projection_distance"] > 1e-6 else "healthy",
        },
        {
            "id": "weighted-balancer",
            "label": "Weighted Load Balancer",
            "metric": f"residual {latest_alloc['rps_residual']:.2f}",
            "detail": ", ".join(latest_alloc["local_states"]),
            "status": "attention" if latest_alloc["rps_residual"] > 1e-6 else "healthy",
        },
        {
            "id": "fast-switcher",
            "label": "Fast Traffic Switcher",
            "metric": "standby",
            "detail": "armed for incident cutover planning",
            "status": "standby",
        },
        {
            "id": "runtime-events",
            "label": "Runtime Events",
            "metric": str(sum(event_counter.values())),
            "detail": f"{len(event_counter)} distinct kinds across timeline",
            "status": "healthy" if event_counter else "standby",
        },
    ]

    total_share = sum(float(share) for share in latest_shares) or 1.0
    load_split = [
        {
            "instance": instance.name,
            "zone": "east" if instance.zone_vector[0] >= instance.zone_vector[1] else "west",
            "share": round(float(share), 2),
            "pct": round(float(share) / total_share * 100, 2),
        }
        for instance, share in zip(stack.balancer.instances, latest_shares)
    ]

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "hero": {
            "title": "Starship SRE Control Center",
            "subtitle": "把 observe → plan → guard → allocate 的控制栈真实打到可视化前端。",
            "theme": "maximalist mission-control editorial",
        },
        "summary": {
            "ticks": len(timeline),
            "degraded_ticks": degraded_ticks,
            "event_visible_fraction": round(
                sum(1 for row in timeline if row["events"]) / max(len(timeline), 1),
                4,
            ),
            "current_replicas": int(current_replicas),
            "canary_share_pct": round(canary_share * 100, 2),
            "avg_observed_rps": round(float(np.mean(observed_rps_series)), 2),
            "peak_forecast_rps": round(float(np.max(forecast_rps_series)), 2),
        },
        "timeline": timeline,
        "adapters": adapters,
        "events": {
            "total": int(sum(event_counter.values())),
            "distinct_kinds": len(event_counter),
            "kinds": [
                {"kind": kind, "count": count}
                for kind, count in sorted(
                    event_counter.items(), key=lambda item: (-item[1], item[0])
                )
            ],
            "recent": event_log[-8:],
        },
        "series": {
            "replicas": replicas_series,
            "observed_rps": _round_series(observed_rps_series),
            "forecast_rps": _round_series(forecast_rps_series),
            "pool_connections": pool_series,
            "degraded_mask": [row["degraded"] for row in timeline],
        },
        "load_split": load_split,
        "stage_rollup": _stage_rollup(timeline),
    }
