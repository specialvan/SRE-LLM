from __future__ import annotations

import numpy as np

from sre_control import (CanaryScheduler, FastTrafficSwitcher, Instance,
                         PoolCapacityPlanner, PredictiveAutoscaler, Signal,
                         SignalFusion, SLOGuardrail, TopologyState,
                         WeightedLoadBalancer)
from sre_control.events import EVENT_COUNTEREXAMPLES, validate_event


def _collect_local_events():
    events = []

    pool = PoolCapacityPlanner(min_keep_alive=4, max_capacity=5)
    _, pool_info = pool.plan(demand_rps_forecast=[800])
    events.extend(pool_info["events"])

    fusion = SignalFusion(
        x0=np.array([1000.0, 25.0, 0.3]),
        P0=np.diag([200**2, 10**2, 0.2**2]),
        Q=np.diag([10.0, 0.5, 0.01]),
        x_ref=np.array([1000.0, 25.0, 0.3]),
        theta=0.2,
    )
    sig = Signal(
        name="metrics",
        h=lambda x: x[0:2],
        H=lambda x: np.array([[1, 0, 0], [0, 1, 0]]),
        R=np.diag([50**2, 4**2]),
    )
    events.extend(fusion.step(dt=1.0, readings=[(sig, None)])["events"])

    topology = TopologyState(q=np.array([0.0, 0.0, 0.0, 0.0]))
    events.extend(topology.step(
        velocity=[0, 0, 0],
        angular_velocity=[0.1, 0.0, 0.0],
        dt=0.05,
    )["events"])

    canary = CanaryScheduler(slo_error_budget=0.01, eta_init=0.10)
    events.extend(canary.observe(
        current_share=0.0,
        proposed_share=0.10,
        observed_error_rate=0.03,
    ).events)

    guard = SLOGuardrail(
        nominal_direction=np.array([0, 0, 1.0]),
        theta_max_deg=15.0,
        magnitude_cap=1000.0,
    )
    events.extend(guard.audit([900, 900, 0])["events"])

    autoscaler = PredictiveAutoscaler(
        per_replica_rps=100.0,
        replicas_min=1,
        replicas_max=10,
        max_step=5,
        dt=5.0,
        horizon=6,
    )
    autoscaler.step(current_replicas=10, observed_rps=1_000,
                    forecast_rps=3_000)
    events.extend(autoscaler.last_trace["events"])

    switcher = FastTrafficSwitcher(rate_max=0.4)
    _, _, switch_info = switcher.plan(
        share_from=0.0,
        share_to=1.0,
        deadline_s=0.5,
    )
    events.extend(switch_info["events"])

    balancer = WeightedLoadBalancer(instances=[
        Instance("east", np.array([1.0, 0.0]), rps_min=10, rps_max=100),
        Instance("west", np.array([0.0, 1.0]), rps_min=10, rps_max=100),
    ])
    _, alloc_info = balancer.allocate(
        rps_demand=500,
        zone_target=[250, 250],
    )
    events.extend(alloc_info["events"])

    # outlier_rejected: fusion with a tight gate and a 10σ reading
    gated_fusion = SignalFusion(
        x0=np.array([1000.0, 25.0, 0.3]),
        P0=np.diag([10**2, 2**2, 0.05**2]),
        Q=np.diag([0.1, 0.01, 0.001]),
        x_ref=np.array([1000.0, 25.0, 0.3]),
        theta=0.2,
        gate_threshold=3.0,
    )
    events.extend(gated_fusion.step(
        dt=1.0,
        readings=[(sig, np.array([5000.0, 200.0]))],  # way outside 3σ
    )["events"])

    return events


def test_all_runtime_events_follow_shared_schema():
    events = _collect_local_events()
    assert {event["kind"] for event in events} == set(EVENT_COUNTEREXAMPLES)
    assert all(validate_event(event) for event in events)


def test_every_event_kind_has_a_specific_counterexample():
    for kind, counterexample in EVENT_COUNTEREXAMPLES.items():
        assert kind
        assert len(counterexample) >= 60
        assert counterexample.startswith(("Do not", "Avoid"))
