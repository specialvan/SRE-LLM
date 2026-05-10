from __future__ import annotations

import json

import numpy as np

from sre_control import (Instance, PredictiveAutoscaler, Signal, SignalFusion,
                         SLOGuardrail, SREControlStack, WeightedLoadBalancer)


def _make_stack():
    fusion = SignalFusion(
        x0=np.array([700.0, 25.0, 0.3]),
        P0=np.diag([100.0 ** 2, 8.0 ** 2, 0.1 ** 2]),
        Q=np.diag([8.0, 0.3, 0.01]),
        x_ref=np.array([700.0, 25.0, 0.3]),
        theta=0.15,
    )
    autoscaler = PredictiveAutoscaler(
        per_replica_rps=100.0,
        replicas_min=4,
        replicas_max=30,
        max_step=4,
        dt=5.0,
        horizon=6,
        q_slo=120.0,
        r_cost=0.6,
    )
    guardrail = SLOGuardrail(
        nominal_direction=np.array([1.0, 0.0, 0.0]),
        theta_max_deg=20.0,
        magnitude_cap=10_000.0,
    )
    balancer = WeightedLoadBalancer(instances=[
        Instance("east", np.array([1.0, 0.0]), rps_min=1.0, rps_max=500.0),
        Instance("west", np.array([0.0, 1.0]), rps_min=1.0, rps_max=500.0),
    ])
    stack = SREControlStack(
        fusion=fusion,
        autoscaler=autoscaler,
        guardrail=guardrail,
        balancer=balancer,
    )
    metrics = Signal(
        name="metrics",
        h=lambda x: x[0:2],
        H=lambda x: np.array([[1.0, 0.0, 0.0],
                              [0.0, 1.0, 0.0]]),
        R=np.diag([25.0 ** 2, 3.0 ** 2]),
    )
    return stack, metrics


def test_sre_stack_emits_a_jsonish_contract_trace():
    stack, metrics = _make_stack()

    entry = stack.step(
        dt=5.0,
        sensor_readings=[(metrics, np.array([760.0, 28.0]))],
        forecast_rps=800.0,
        current_replicas=6,
        zone_target=np.array([480.0, 320.0]),
        nn_proposal=np.array([500.0, 50.0, 10.0]),
    )

    assert {"dt", "state", "replicas_current", "replicas_next",
            "canary", "guardrail", "alloc_shares", "alloc_info"} <= entry.keys()
    assert isinstance(entry["replicas_next"], int)
    assert entry["canary"] is None
    assert len(entry["alloc_shares"]) == 2
    assert all(isinstance(flag, bool) for flag in entry["alloc_info"]["saturation"])
    assert np.linalg.norm(entry["guardrail"]["approved"]) <= 10_000.0 + 1e-6
    json.dumps(entry)


def test_sre_stack_survives_missing_sensor_readings():
    stack, metrics = _make_stack()

    entry = stack.step(
        dt=5.0,
        sensor_readings=[(metrics, None)],
        forecast_rps=750.0,
        current_replicas=6,
        zone_target=np.array([420.0, 280.0]),
        nn_proposal=np.array([450.0, 40.0, 12.0]),
    )

    assert entry["state"]["signals"][0]["used"] is False
    assert isinstance(entry["replicas_next"], int)
    assert len(entry["alloc_shares"]) == 2
    json.dumps(entry)
