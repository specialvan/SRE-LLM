from __future__ import annotations

import json

import numpy as np
import pytest

from sre_control import (
    CanaryScheduler,
    Instance,
    PredictiveAutoscaler,
    Signal,
    SignalFusion,
    SLOGuardrail,
    SREControlStack,
    WeightedLoadBalancer,
)


def _make_stack():
    fusion = SignalFusion(
        x0=np.array([700.0, 25.0, 0.3]),
        P0=np.diag([100.0**2, 8.0**2, 0.1**2]),
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
    balancer = WeightedLoadBalancer(
        instances=[
            Instance("east", np.array([1.0, 0.0]), rps_min=1.0, rps_max=500.0),
            Instance("west", np.array([0.0, 1.0]), rps_min=1.0, rps_max=500.0),
        ]
    )
    stack = SREControlStack(
        fusion=fusion,
        autoscaler=autoscaler,
        guardrail=guardrail,
        balancer=balancer,
    )
    metrics = Signal(
        name="metrics",
        h=lambda x: x[0:2],
        H=lambda x: np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]),
        R=np.diag([25.0**2, 3.0**2]),
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

    assert {
        "dt",
        "runtime",
        "state",
        "replicas_current",
        "replicas_next",
        "canary",
        "guardrail",
        "alloc_shares",
        "alloc_info",
    } <= entry.keys()
    assert isinstance(entry["replicas_next"], int)
    assert entry["canary"] is None
    assert entry["runtime"]["states"][0] == "OBSERVING"
    assert entry["runtime"]["states"][-1] == "EXECUTING"
    assert "GUARDING" in entry["runtime"]["states"]
    assert "ALLOCATING" in entry["runtime"]["states"]
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
    assert any(event["kind"] == "missing_sensor" for event in entry["state"]["events"])
    assert entry["runtime"]["degraded"] is True
    assert "DEGRADED_OBSERVE" in entry["runtime"]["states"]
    assert any(
        event["kind"] == "missing_sensor" for event in entry["runtime"]["events"]
    )
    assert isinstance(entry["replicas_next"], int)
    assert len(entry["alloc_shares"]) == 2
    json.dumps(entry)


def test_sre_stack_carries_canary_local_events_upward():
    stack, metrics = _make_stack()
    stack.canary = CanaryScheduler(
        slo_error_budget=0.01,
        eta_init=0.10,
        eta_min=0.005,
        eta_max=0.30,
    )

    entry = stack.step(
        dt=5.0,
        sensor_readings=[(metrics, np.array([760.0, 28.0]))],
        forecast_rps=800.0,
        current_replicas=6,
        zone_target=np.array([480.0, 320.0]),
        nn_proposal=np.array([500.0, 50.0, 10.0]),
        current_canary_share=0.0,
        canary_observed_error=0.03,
    )

    assert entry["canary"]["accepted"] is False
    assert "freeze" in entry["canary"]["local_states"]
    assert "DEGRADED_PLAN" in entry["runtime"]["states"]
    assert any(
        event["kind"] == "rollout_rejected" for event in entry["runtime"]["events"]
    )
    json.dumps(entry)


def test_sre_stack_carries_guardrail_events_upward():
    stack, metrics = _make_stack()

    entry = stack.step(
        dt=5.0,
        sensor_readings=[(metrics, np.array([760.0, 28.0]))],
        forecast_rps=800.0,
        current_replicas=6,
        zone_target=np.array([480.0, 320.0]),
        # direction is 45 degrees from nominal (>> theta_max_deg=20)
        nn_proposal=np.array([500.0, 500.0, 0.0]),
    )

    assert entry["guardrail"]["cone_violated_before"] is True
    assert "DEGRADED_GUARD" in entry["runtime"]["states"]
    assert entry["runtime"]["degraded"] is True
    assert any(
        event["kind"] == "unsafe_proposal_projected"
        for event in entry["runtime"]["events"]
    )
    json.dumps(entry)


def test_sre_stack_carries_allocator_events_upward():
    stack, metrics = _make_stack()
    # shrink caps so the demand saturates at least one instance
    stack.balancer = WeightedLoadBalancer(
        instances=[
            Instance("east", np.array([1.0, 0.0]), rps_min=1.0, rps_max=50.0),
            Instance("west", np.array([0.0, 1.0]), rps_min=1.0, rps_max=50.0),
        ]
    )

    entry = stack.step(
        dt=5.0,
        sensor_readings=[(metrics, np.array([760.0, 28.0]))],
        forecast_rps=800.0,
        current_replicas=6,
        zone_target=np.array([200.0, 200.0]),
        nn_proposal=np.array([300.0, 0.0, 0.0]),
    )

    assert any(entry["alloc_info"]["saturation"])
    assert "DEGRADED_ALLOCATE" in entry["runtime"]["states"]
    assert any(
        event["kind"] == "bounded_ls_residual" for event in entry["runtime"]["events"]
    )
    json.dumps(entry)


def test_sre_stack_recovers_from_recoverable_adapter_error():
    """Recoverable control-domain errors complete the tick with cause fields."""
    from sre_control import RecoverableControlError, SignalFusion

    class _RecoverableFusion(SignalFusion):
        def step(self, dt, readings):
            raise RecoverableControlError("temporary fusion outage")

    stack, metrics = _make_stack()
    stack.fusion = _RecoverableFusion(
        x0=np.array([700.0, 25.0, 0.3]),
        P0=np.diag([100.0**2, 8.0**2, 0.1**2]),
        Q=np.diag([8.0, 0.3, 0.01]),
        x_ref=np.array([700.0, 25.0, 0.3]),
        theta=0.15,
    )

    entry = stack.step(
        dt=5.0,
        sensor_readings=[(metrics, np.array([750.0, 28.0]))],
        forecast_rps=800.0,
        current_replicas=6,
        zone_target=np.array([480.0, 320.0]),
        nn_proposal=np.array([500.0, 50.0, 10.0]),
    )

    assert "DEGRADED_OBSERVE" in entry["runtime"]["states"]
    events = [e for e in entry["runtime"]["events"] if e["kind"] == "adapter_exception"]
    assert events
    assert events[0]["stage"] == "SignalFusion"
    assert events[0]["exception_type"] == "RecoverableControlError"
    assert events[0]["cause_type"] == "control_domain"
    assert events[0]["recoverable"] is True
    assert isinstance(entry["replicas_next"], int)
    assert len(entry["alloc_shares"]) == 2
    json.dumps(entry)


def test_stability_recoverable_error_uses_adapter_exception():
    from sre_control import RecoverableControlError, StabilityGuard

    class _RecoverableStability(StabilityGuard):
        def step(self, x, t):
            raise RecoverableControlError("stability monitor unavailable")

    stack, metrics = _make_stack()
    stack.stability = _RecoverableStability(
        V_fn=lambda x: float(x[0]),
        tolerance=1e-3,
        k_violations=1,
    )

    entry = stack.step(
        dt=5.0,
        sensor_readings=[(metrics, np.array([750.0, 28.0]))],
        forecast_rps=800.0,
        current_replicas=6,
        zone_target=np.array([480.0, 320.0]),
        nn_proposal=np.array([500.0, 50.0, 10.0]),
    )

    events = [e for e in entry["runtime"]["events"] if e["stage"] == "StabilityGuard"]
    assert events
    assert events[0]["kind"] == "adapter_exception"
    assert events[0]["exception_type"] == "RecoverableControlError"
    assert events[0]["recoverable"] is True


def test_stability_monitor_skips_observe_fallback_state():
    from sre_control import RecoverableControlError, SignalFusion, StabilityGuard

    class _RecoverableFusion(SignalFusion):
        def step(self, dt, readings):
            raise RecoverableControlError("temporary fusion outage")

    stack, metrics = _make_stack()
    stack.fusion = _RecoverableFusion(
        x0=np.array([700.0, 25.0, 0.3]),
        P0=np.diag([100.0**2, 8.0**2, 0.1**2]),
        Q=np.diag([8.0, 0.3, 0.01]),
        x_ref=np.array([700.0, 25.0, 0.3]),
        theta=0.15,
    )
    stack.stability = StabilityGuard(
        V_fn=lambda x: (_ for _ in ()).throw(AssertionError("stale state used")),
        tolerance=1e-3,
        k_violations=1,
    )

    entry = stack.step(
        dt=5.0,
        sensor_readings=[(metrics, np.array([750.0, 28.0]))],
        forecast_rps=800.0,
        current_replicas=6,
        zone_target=np.array([480.0, 320.0]),
        nn_proposal=np.array([500.0, 50.0, 10.0]),
    )

    assert entry["stability"] is None
    assert "DEGRADED_OBSERVE" in entry["runtime"]["states"]


def test_sre_stack_does_not_swallow_programmer_error():
    stack, metrics = _make_stack()

    def _bug(*_args, **_kwargs):
        raise AttributeError("programmer bug")

    stack.autoscaler.step = _bug

    with pytest.raises(AttributeError, match="programmer bug"):
        stack.step(
            dt=5.0,
            sensor_readings=[(metrics, np.array([750.0, 28.0]))],
            forecast_rps=800.0,
            current_replicas=6,
            zone_target=np.array([480.0, 320.0]),
            nn_proposal=np.array([500.0, 50.0, 10.0]),
        )


def test_guard_fallback_does_not_reuse_malformed_nn_proposal():
    from sre_control import RecoverableControlError, SLOGuardrail

    class _RecoverableGuardrail(SLOGuardrail):
        def audit(self, proposal):
            raise RecoverableControlError("guard unavailable")

    stack, metrics = _make_stack()
    stack.guardrail = _RecoverableGuardrail(
        nominal_direction=np.array([1.0, 0.0, 0.0]),
        theta_max_deg=20.0,
        magnitude_cap=10_000.0,
    )

    entry = stack.step(
        dt=5.0,
        sensor_readings=[(metrics, np.array([750.0, 28.0]))],
        forecast_rps=800.0,
        current_replicas=6,
        zone_target=np.array([480.0, 320.0]),
        nn_proposal=np.array([500.0, 50.0, 10.0]),
    )

    assert "DEGRADED_GUARD" in entry["runtime"]["states"]
    assert entry["guardrail"]["approved"] == [0.0, 0.0, 0.0]
    event = next(
        e for e in entry["runtime"]["events"] if e["kind"] == "adapter_exception"
    )
    assert event["stage"] == "SLOGuardrail"
    assert event["recoverable"] is True


def test_sre_stack_survives_recoverable_autoscaler_exception():
    """If autoscaler has a recoverable failure, next_replicas stays bounded."""
    from sre_control import RecoverableControlError

    stack, metrics = _make_stack()

    def _boom(*_a, **_k):
        raise RecoverableControlError("autoscaler explosion")

    stack.autoscaler.step = _boom  # monkey-patch

    entry = stack.step(
        dt=5.0,
        sensor_readings=[(metrics, np.array([750.0, 28.0]))],
        forecast_rps=800.0,
        current_replicas=6,
        zone_target=np.array([480.0, 320.0]),
        nn_proposal=np.array([500.0, 50.0, 10.0]),
    )

    # Safe fallback: replicas stays inside [min, max]
    assert (
        stack.autoscaler.replicas_min
        <= entry["replicas_next"]
        <= stack.autoscaler.replicas_max
    )
    assert "DEGRADED_PLAN" in entry["runtime"]["states"]
    assert any(
        e["kind"] == "adapter_exception"
        and e["stage"] == "PredictiveAutoscaler"
        and e["recoverable"] is True
        for e in entry["runtime"]["events"]
    )
    json.dumps(entry)


def test_sre_stack_reuses_last_successful_alloc_shares_on_recoverable_balancer_error():
    from sre_control import RecoverableControlError, WeightedLoadBalancer

    class _RecoverableBalancer(WeightedLoadBalancer):
        def allocate(self, rps_demand, zone_target):
            raise RecoverableControlError("allocator unavailable")

    stack, metrics = _make_stack()
    first = stack.step(
        dt=5.0,
        sensor_readings=[(metrics, np.array([760.0, 28.0]))],
        forecast_rps=800.0,
        current_replicas=6,
        zone_target=np.array([480.0, 320.0]),
        nn_proposal=np.array([500.0, 50.0, 10.0]),
    )
    assert sum(first["alloc_shares"]) > 0

    failing = _RecoverableBalancer(instances=stack.balancer.instances)
    stack.balancer = failing
    second = stack.step(
        dt=5.0,
        sensor_readings=[(metrics, np.array([770.0, 28.5]))],
        forecast_rps=820.0,
        current_replicas=first["replicas_next"],
        zone_target=np.array([492.0, 328.0]),
        nn_proposal=np.array([520.0, 55.0, 8.0]),
    )

    assert second["alloc_shares"] == first["alloc_shares"]
    assert "DEGRADED_ALLOCATE" in second["runtime"]["states"]
    event = next(
        e
        for e in second["runtime"]["events"]
        if e["kind"] == "adapter_exception" and e["stage"] == "WeightedLoadBalancer"
    )
    assert event["exception_type"] == "RecoverableControlError"
    assert event["cause_type"] == "control_domain"
    assert event["recoverable"] is True
    json.dumps(second)


def test_sre_stack_balancer_recoverable_error_bootstrap_falls_back_to_zero_shares():
    from sre_control import RecoverableControlError, WeightedLoadBalancer

    class _RecoverableBalancer(WeightedLoadBalancer):
        def allocate(self, rps_demand, zone_target):
            raise RecoverableControlError("allocator unavailable")

    stack, metrics = _make_stack()
    stack.balancer = _RecoverableBalancer(instances=stack.balancer.instances)

    entry = stack.step(
        dt=5.0,
        sensor_readings=[(metrics, np.array([750.0, 28.0]))],
        forecast_rps=800.0,
        current_replicas=6,
        zone_target=np.array([480.0, 320.0]),
        nn_proposal=np.array([500.0, 50.0, 10.0]),
    )

    assert entry["alloc_shares"] == [0.0] * len(stack.balancer.instances)
    assert "DEGRADED_ALLOCATE" in entry["runtime"]["states"]
    event = next(
        e
        for e in entry["runtime"]["events"]
        if e["kind"] == "adapter_exception" and e["stage"] == "WeightedLoadBalancer"
    )
    assert event["exception_type"] == "RecoverableControlError"
    assert event["recoverable"] is True
    json.dumps(entry)





def test_sre_stack_refuses_stale_alloc_history_when_balancer_topology_changes():
    from sre_control import RecoverableControlError, WeightedLoadBalancer

    class _RecoverableBalancer(WeightedLoadBalancer):
        def allocate(self, rps_demand, zone_target):
            raise RecoverableControlError("allocator unavailable")

    stack, metrics = _make_stack()
    first = stack.step(
        dt=5.0,
        sensor_readings=[(metrics, np.array([760.0, 28.0]))],
        forecast_rps=800.0,
        current_replicas=6,
        zone_target=np.array([480.0, 320.0]),
        nn_proposal=np.array([500.0, 50.0, 10.0]),
    )
    assert sum(first["alloc_shares"]) > 0

    stack.balancer = _RecoverableBalancer(
        instances=list(reversed(stack.balancer.instances))
    )
    second = stack.step(
        dt=5.0,
        sensor_readings=[(metrics, np.array([770.0, 28.5]))],
        forecast_rps=820.0,
        current_replicas=first["replicas_next"],
        zone_target=np.array([492.0, 328.0]),
        nn_proposal=np.array([520.0, 55.0, 8.0]),
    )

    assert second["alloc_shares"] == [0.0] * len(stack.balancer.instances)
    assert "bootstrap_zero_fallback" in second["alloc_info"]["local_states"]

    """Feed the stack a monotonically increasing Lyapunov candidate.
    After k_violations consecutive violating ticks the stack must
    surface a stability_violation event and DEGRADED_PLAN.

    Trick: the default SignalFusion pulls the posterior toward
    ``x_ref``, so just raising the reading doesn't monotonically raise
    the fused state. Instead we build a custom stack whose fusion has
    no OU pull, so the fused QPS tracks the reading ~1:1.
    """
    from sre_control import (
        Instance,
        PredictiveAutoscaler,
        Signal,
        SignalFusion,
        SLOGuardrail,
        SREControlStack,
        StabilityGuard,
        WeightedLoadBalancer,
    )

    fusion = SignalFusion(
        x0=np.array([700.0, 25.0, 0.3]),
        P0=np.diag([100.0**2, 8.0**2, 0.1**2]),
        Q=np.diag([1e-3, 1e-3, 1e-4]),
        x_ref=np.array([700.0, 25.0, 0.3]),
        theta=0.0,
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
    balancer = WeightedLoadBalancer(
        instances=[
            Instance("east", np.array([1.0, 0.0]), rps_min=1.0, rps_max=500.0),
            Instance("west", np.array([0.0, 1.0]), rps_min=1.0, rps_max=500.0),
        ]
    )
    stack = SREControlStack(
        fusion=fusion,
        autoscaler=autoscaler,
        guardrail=guardrail,
        balancer=balancer,
        stability=StabilityGuard(
            V_fn=lambda x: float(x[0]),
            tolerance=1e-3,
            k_violations=2,
            label="qps",
        ),
    )
    metrics = Signal(
        name="metrics",
        h=lambda x: x[0:2],
        H=lambda x: np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]),
        R=np.diag([25.0**2, 3.0**2]),
    )

    last_entry = None
    for qps in [750.0, 800.0, 850.0, 900.0, 950.0]:
        last_entry = stack.step(
            dt=5.0,
            sensor_readings=[(metrics, np.array([qps, 28.0]))],
            forecast_rps=1000.0,
            current_replicas=6,
            zone_target=np.array([480.0, 320.0]),
            nn_proposal=np.array([500.0, 50.0, 10.0]),
        )

    assert last_entry["stability"] is not None
    assert last_entry["stability"]["triggered"] is True
    assert "DEGRADED_PLAN" in last_entry["runtime"]["states"]
    all_events = [ev for e in stack.trace for ev in e["runtime"]["events"]]
    assert any(
        ev["kind"] == "stability_violation" and ev["stage"].startswith("StabilityGuard")
        for ev in all_events
    )
    json.dumps(last_entry)


def test_stability_guard_reports_sustained_trigger_without_new_event():
    from sre_control import (
        Instance,
        PredictiveAutoscaler,
        Signal,
        SignalFusion,
        SLOGuardrail,
        SREControlStack,
        StabilityGuard,
        WeightedLoadBalancer,
    )

    fusion = SignalFusion(
        x0=np.array([700.0, 25.0, 0.3]),
        P0=np.diag([100.0**2, 8.0**2, 0.1**2]),
        Q=np.diag([1e-3, 1e-3, 1e-4]),
        x_ref=np.array([700.0, 25.0, 0.3]),
        theta=0.0,
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
    balancer = WeightedLoadBalancer(
        instances=[
            Instance("east", np.array([1.0, 0.0]), rps_min=1.0, rps_max=500.0),
            Instance("west", np.array([0.0, 1.0]), rps_min=1.0, rps_max=500.0),
        ]
    )
    stack = SREControlStack(
        fusion=fusion,
        autoscaler=autoscaler,
        guardrail=guardrail,
        balancer=balancer,
        stability=StabilityGuard(
            V_fn=lambda x: float(x[0]),
            tolerance=1e-3,
            k_violations=2,
            label="qps",
        ),
    )
    metrics = Signal(
        name="metrics",
        h=lambda x: x[0:2],
        H=lambda x: np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]),
        R=np.diag([25.0**2, 3.0**2]),
    )

    entries = []
    for qps in [750.0, 800.0, 850.0, 900.0]:
        entries.append(
            stack.step(
                dt=5.0,
                sensor_readings=[(metrics, np.array([qps, 28.0]))],
                forecast_rps=1000.0,
                current_replicas=6,
                zone_target=np.array([480.0, 320.0]),
                nn_proposal=np.array([500.0, 50.0, 10.0]),
            )
        )

    sustained_entry = stack.step(
        dt=5.0,
        sensor_readings=[(metrics, np.array([850.0, 28.0]))],
        forecast_rps=1000.0,
        current_replicas=6,
        zone_target=np.array([480.0, 320.0]),
        nn_proposal=np.array([500.0, 50.0, 10.0]),
    )

    trigger_entry = next(
        (
            entry
            for entry in entries
            if any(ev["kind"] == "stability_violation" for ev in entry["runtime"]["events"])
        ),
        None,
    )

    assert trigger_entry is not None

    trigger_events = [
        ev
        for ev in trigger_entry["runtime"]["events"]
        if ev["kind"] == "stability_violation"
    ]
    sustained_events = [
        ev for ev in sustained_entry["runtime"]["events"]
        if ev["kind"] == "stability_violation"
    ]
    assert trigger_events
    assert not sustained_events
    assert sustained_entry["stability"]["triggered"] is True
    assert "sustained" in sustained_entry["stability"]["local_states"]
    assert "DEGRADED_PLAN" in sustained_entry["runtime"]["states"]
