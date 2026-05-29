from __future__ import annotations

import importlib.util
import json
import tomllib
from pathlib import Path

import numpy as np
import pytest

from sre_control import (
    AdapterInputError,
    CanaryScheduler,
    Instance,
    PredictiveAutoscaler,
    Signal,
    SignalFusion,
    SLOGuardrail,
    SREControlStack,
    StabilityGuard,
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


@pytest.mark.parametrize('dt', [0.0, -1.0, np.nan, np.inf, -np.inf])
def test_sre_stack_rejects_invalid_dt_before_mutating_tick_state(dt):
    stack, metrics = _make_stack()
    x_before = stack.fusion.state.copy()
    p_before = stack.fusion.covariance.copy()

    with pytest.raises(AdapterInputError, match='dt must be positive and finite'):
        stack.step(
            dt=dt,
            sensor_readings=[(metrics, np.array([760.0, 28.0]))],
            forecast_rps=800.0,
            current_replicas=6,
            zone_target=np.array([480.0, 320.0]),
            nn_proposal=np.array([500.0, 50.0, 10.0]),
        )

    assert stack.trace == []
    assert stack._tick_index == 0
    assert stack._elapsed_time == 0.0
    assert np.allclose(stack.fusion.state, x_before)
    assert np.allclose(stack.fusion.covariance, p_before)


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


def test_sre_stack_uses_action_norm_as_total_rps_demand():
    stack, metrics = _make_stack()
    stack.guardrail = SLOGuardrail(
        nominal_direction=np.array([1.0, 0.0, 0.0]),
        theta_max_deg=90.0,
        magnitude_cap=10_000.0,
    )
    stack.balancer = WeightedLoadBalancer(
        instances=[
            Instance("east", np.array([1.0, 0.0, 0.0]), rps_min=0.0, rps_max=1_000.0),
            Instance("west", np.array([0.0, 1.0, 0.0]), rps_min=0.0, rps_max=1_000.0),
        ]
    )

    entry = stack.step(
        dt=5.0,
        sensor_readings=[(metrics, np.array([750.0, 28.0]))],
        forecast_rps=800.0,
        current_replicas=6,
        zone_target=np.array([600.0, 400.0, 0.0]),
        nn_proposal=np.array([600.0, 800.0, 0.0]),
    )

    assert entry["alloc_info"]["demand_satisfied"] is True
    assert entry["alloc_info"]["rps_residual"] < 1e-6
    assert np.allclose(entry["alloc_shares"], [600.0, 400.0], atol=1e-6)


def test_sre_stack_data_contract_exports_stage_boundaries():
    from sre_control import stack_data_contract
    from sre_control.events import EVENT_COUNTEREXAMPLES

    contract = stack_data_contract()

    assert contract["evidence_scope"] == "research_stack_data_contract"
    assert contract["production_claim"] is False
    assert contract["orchestration_model"] == "single_process_research_loop"
    stages = {stage["stage"]: stage for stage in contract["stages"]}
    assert list(stages) == ["observe", "stability", "plan", "guard", "allocate", "execute"]
    assert stages["observe"]["producer"] == "SignalFusion.step"
    assert "sensor_readings" in stages["observe"]["inputs"]
    assert "state" in stages["observe"]["outputs"]
    assert stages["observe"]["event_kinds"] == [
        "missing_sensor",
        "outlier_rejected",
        "adapter_exception",
    ]
    assert stages["guard"]["event_kinds"] == [
        "unsafe_proposal_projected",
        "adapter_exception",
    ]
    assert stages["guard"]["fallback_actions"] == ["zero_guardrail_action"]
    assert stages["guard"]["fallback_action_modes"] == {
        "zero_guardrail_action": "zero_action",
    }
    assert stages["guard"]["fallback_modes"] == ["zero_action"]
    assert stages["allocate"]["event_kinds"] == [
        "bounded_ls_residual",
        "adapter_exception",
    ]
    assert stages["allocate"]["fallback_actions"] == [
        "reuse_last_good_shares",
        "bootstrap_zero_fallback",
    ]
    assert stages["allocate"]["fallback_action_modes"] == {
        "reuse_last_good_shares": "reuse_last_good_cache",
        "bootstrap_zero_fallback": "zero_action",
    }
    assert stages["allocate"]["fallback_modes"] == [
        "reuse_last_good_cache",
        "zero_action",
    ]
    for stage in contract["stages"]:
        assert set(stage["fallback_action_modes"]) == set(stage["fallback_actions"])
        assert set(stage["fallback_action_modes"].values()).issubset(
            set(stage["fallback_modes"])
        )
    for stage in contract["stages"]:
        assert set(stage["event_kinds"]).issubset(EVENT_COUNTEREXAMPLES)
    assert contract["event_stage_routes"] == {
        "SignalFusion": "observe",
        "StabilityGuard": "stability",
        "PredictiveAutoscaler": "plan",
        "CanaryScheduler": "plan",
        "SLOGuardrail": "guard",
        "WeightedLoadBalancer": "allocate",
    }
    assert "runtime.events" in stages["execute"]["outputs"]
    assert contract["split_ready_boundaries"] == [
        "observe_to_plan",
        "plan_to_guard",
        "guard_to_allocate",
        "allocate_to_execute",
    ]
    json.dumps(contract)


def test_stack_contract_fallback_action_modes_match_runtime_mapping():
    from sre_control import stack_data_contract
    from sre_control.stack import SREControlStack

    contract = stack_data_contract()
    action_modes = {
        action: mode
        for stage in contract["stages"]
        for action, mode in stage["fallback_action_modes"].items()
    }

    assert action_modes
    assert set(action_modes) == {
        action
        for stage in contract["stages"]
        for action in stage["fallback_actions"]
    }
    for action, expected_mode in action_modes.items():
        assert SREControlStack._fallback_mode(action) == expected_mode


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


def test_sre_stack_classifies_adapter_input_error_as_adapter_input():
    from sre_control import AdapterInputError, SignalFusion

    class _AdapterInputFusion(SignalFusion):
        def step(self, dt, readings):
            raise AdapterInputError("missing adapter input")

    stack, metrics = _make_stack()
    stack.fusion = _AdapterInputFusion(
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
    event = next(
        e for e in entry["runtime"]["events"] if e["kind"] == "adapter_exception"
    )
    assert event["stage"] == "SignalFusion"
    assert event["exception_type"] == "AdapterInputError"
    assert event["cause_type"] == "adapter_input"
    assert event["recoverable"] is True
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


def test_adapter_exception_family_matches_stack_contract_routes():
    from sre_control import RecoverableControlError, SREControlStack, stack_data_contract

    routes = stack_data_contract()["event_stage_routes"]
    for stage_label, expected_family in routes.items():
        event = SREControlStack._adapter_exception_event(
            stage_label,
            RecoverableControlError("temporary adapter outage"),
            "use_test_fallback",
        )

        assert event["adapter_family"] == expected_family


def test_adapter_exception_exposes_routeable_fallback_mode():
    from sre_control import RecoverableControlError, SREControlStack

    event = SREControlStack._adapter_exception_event(
        'SLOGuardrail',
        RecoverableControlError('guard unavailable'),
        'zero_guardrail_action',
    )

    assert event['fallback_action'] == 'zero_guardrail_action'
    assert event['fallback_mode'] == 'zero_action'


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


def test_sre_stack_autoscaler_fallback_overwrites_last_trace():
    from sre_control import RecoverableControlError

    stack, metrics = _make_stack()
    first = stack.step(
        dt=5.0,
        sensor_readings=[(metrics, np.array([750.0, 28.0]))],
        forecast_rps=900.0,
        current_replicas=6,
        zone_target=np.array([480.0, 320.0]),
        nn_proposal=np.array([500.0, 50.0, 10.0]),
    )
    assert stack.autoscaler.last_trace.get("fallback") is not True

    def _boom(*_a, **_k):
        raise RecoverableControlError("autoscaler explosion")

    stack.autoscaler.step = _boom
    second = stack.step(
        dt=5.0,
        sensor_readings=[(metrics, np.array([760.0, 28.0]))],
        forecast_rps=1200.0,
        current_replicas=first["replicas_next"],
        zone_target=np.array([480.0, 320.0]),
        nn_proposal=np.array([500.0, 50.0, 10.0]),
    )

    assert stack.autoscaler.last_trace["fallback"] is True
    assert stack.autoscaler.last_trace["next_replicas"] == second["replicas_next"]
    assert stack.autoscaler.last_trace["local_states"] == ["error"]
    assert "autoscaler explosion" in stack.autoscaler.last_trace["fallback_reason"]


def test_sre_stack_handles_invalid_forecast_as_plan_adapter_input_error():
    stack, metrics = _make_stack()

    entry = stack.step(
        dt=5.0,
        sensor_readings=[(metrics, np.array([750.0, 28.0]))],
        forecast_rps=np.nan,
        current_replicas=6,
        zone_target=np.array([480.0, 320.0]),
        nn_proposal=np.array([500.0, 50.0, 10.0]),
    )

    assert entry['replicas_next'] == 6
    assert 'DEGRADED_PLAN' in entry['runtime']['states']
    event = next(
        e
        for e in entry['runtime']['events']
        if e['kind'] == 'adapter_exception'
        and e['stage'] == 'PredictiveAutoscaler'
    )
    assert event['exception_type'] == 'AdapterInputError'
    assert event['cause_type'] == 'adapter_input'
    assert event['fallback_action'] == 'keep_current_replicas'
    assert stack.autoscaler.last_trace['fallback'] is True
    assert 'forecast_rps must be non-negative and finite' in (
        stack.autoscaler.last_trace['fallback_reason']
    )
    json.dumps(entry, allow_nan=False)


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
    assert event["adapter_family"] == "allocate"
    assert event["fault_family"] == "control_domain"
    assert event["fallback_action"] == "reuse_last_good_shares"
    assert event["recoverable"] is True
    assert second["alloc_info"]["rps_residual"] is None
    assert second["alloc_info"]["cost"] is None
    json.dumps(second, allow_nan=False)


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
    assert event["adapter_family"] == "allocate"
    assert event["fault_family"] == "control_domain"
    assert event["fallback_action"] == "bootstrap_zero_fallback"
    assert event["recoverable"] is True
    assert entry["alloc_info"]["rps_residual"] is None
    assert entry["alloc_info"]["cost"] is None
    json.dumps(entry, allow_nan=False)


def test_package_surfaces_are_importable():
    import starship
    import sre_control

    assert importlib.util.find_spec("starship") is not None
    assert importlib.util.find_spec("sre_control") is not None
    assert hasattr(starship, "RecoveryPipeline")
    assert hasattr(starship, "CatchController")
    assert hasattr(sre_control, "SREControlStack")
    assert hasattr(sre_control, "stack_data_contract")
    assert hasattr(sre_control, "EVENT_COUNTEREXAMPLES")


def test_pyproject_includes_sre_control_in_package_discovery():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    package_include = pyproject["tool"]["setuptools"]["packages"]["find"]["include"]

    assert "starship*" in package_include
    assert "sre_control*" in package_include


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


def test_sre_stack_refuses_stale_alloc_history_when_only_zone_vector_changes():
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
        instances=[
            Instance("east", np.array([0.8, 0.2]), rps_min=1.0, rps_max=500.0),
            Instance("west", np.array([0.2, 0.8]), rps_min=1.0, rps_max=500.0),
        ]
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
    assert "reuse_last_good_shares" not in second["alloc_info"]["local_states"]


def test_sre_stack_rejects_nan_last_good_alloc_cache():
    stack, _metrics = _make_stack()
    stack._last_good_alloc_signature = stack._allocator_signature()
    stack._last_good_alloc_shares = np.array([np.nan, 100.0])

    assert stack._can_reuse_last_good_alloc() is False


def test_stability_guard_triggers_degraded_plan_on_sustained_violation():
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


def test_stack_clamps_autoscaler_when_stability_triggered():
    stack, metrics = _make_stack()
    stack.fusion.theta = 0.0
    stack.autoscaler.max_step = 4
    stack.stability = StabilityGuard(
        V_fn=lambda x: float(x[0]),
        tolerance=1e-6,
        k_violations=1,
        label="qps",
    )

    stack.step(
        dt=5.0,
        sensor_readings=[(metrics, np.array([700.0, 25.0]))],
        forecast_rps=3000.0,
        current_replicas=6,
        zone_target=np.array([480.0, 320.0]),
        nn_proposal=np.array([500.0, 50.0, 10.0]),
    )
    triggered = stack.step(
        dt=5.0,
        sensor_readings=[(metrics, np.array([900.0, 25.0]))],
        forecast_rps=3000.0,
        current_replicas=6,
        zone_target=np.array([480.0, 320.0]),
        nn_proposal=np.array([500.0, 50.0, 10.0]),
    )

    assert triggered["stability"]["triggered"] is True
    assert "DEGRADED_PLAN" in triggered["runtime"]["states"]
    assert abs(stack.autoscaler.last_trace["raw_control"]) <= 1.0 + 1e-6
    assert triggered["replicas_next"] <= 7


def test_stability_monitor_uses_cumulative_elapsed_time_for_variable_dt():
    stack, metrics = _make_stack()

    class _RecordingStability:
        def __init__(self):
            self.times = []

        def step(self, x, t):
            self.times.append(t)
            return {"events": [], "triggered": False, "local_states": ["observe"]}

    recorder = _RecordingStability()
    stack.stability = recorder

    for dt in [2.0, 5.0]:
        stack.step(
            dt=dt,
            sensor_readings=[(metrics, np.array([760.0, 28.0]))],
            forecast_rps=800.0,
            current_replicas=6,
            zone_target=np.array([480.0, 320.0]),
            nn_proposal=np.array([500.0, 50.0, 10.0]),
        )

    assert recorder.times == pytest.approx([0.0, 2.0])


def test_stability_guard_sre_error_budget_example_triggers_stack_event():
    from sre_control import (
        Instance,
        PredictiveAutoscaler,
        Signal,
        SignalFusion,
        SLOGuardrail,
        SREControlStack,
        StabilityGuard,
        WeightedLoadBalancer,
        sre_error_budget_V,
    )

    fusion = SignalFusion(
        x0=np.array([1000.0, 90.0, 0.005]),
        P0=np.diag([1.0, 1.0, 1e-6]),
        Q=np.diag([1e-6, 1e-6, 1e-8]),
        x_ref=np.array([1000.0, 90.0, 0.005]),
        theta=0.0,
    )
    stack = SREControlStack(
        fusion=fusion,
        autoscaler=PredictiveAutoscaler(
            per_replica_rps=100.0,
            replicas_min=4,
            replicas_max=50,
            max_step=3,
            dt=5.0,
            horizon=5,
        ),
        guardrail=SLOGuardrail(
            nominal_direction=np.array([1.0, 0.0, 0.0]),
            theta_max_deg=45.0,
            magnitude_cap=2_000.0,
        ),
        balancer=WeightedLoadBalancer(
            instances=[
                Instance("east", np.array([1.0, 0.0]), 0.0, 2_000.0),
                Instance("west", np.array([0.0, 1.0]), 0.0, 2_000.0),
            ]
        ),
        stability=StabilityGuard(
            V_fn=sre_error_budget_V(
                latency_target_ms=100.0,
                latency_scale_ms=50.0,
                error_rate_target=0.01,
                error_rate_scale=0.02,
            ),
            tolerance=1e-6,
            k_violations=2,
            label="error_budget",
        ),
    )
    metrics = Signal(
        name="metrics",
        h=lambda x: x,
        H=lambda x: np.eye(3),
        R=np.diag([1e-6, 1e-6, 1e-10]),
    )

    last_entry = None
    for i, reading in enumerate(
        [
            np.array([1000.0, 100.0, 0.01]),
            np.array([1000.0, 125.0, 0.015]),
            np.array([1000.0, 150.0, 0.02]),
        ]
    ):
        last_entry = stack.step(
            dt=5.0,
            sensor_readings=[(metrics, reading)],
            forecast_rps=1000.0,
            current_replicas=10,
            zone_target=np.array([500.0, 500.0]),
            nn_proposal=np.array([500.0, 500.0, 0.0]),
        )

    assert last_entry is not None
    assert last_entry["stability"]["triggered"] is True
    assert "DEGRADED_PLAN" in last_entry["runtime"]["states"]
    assert any(
        ev["kind"] == "stability_violation"
        and ev["stage"] == "StabilityGuard/error_budget"
        for ev in last_entry["runtime"]["events"]
    )


@pytest.mark.parametrize(
    ('kwargs', 'match'),
    [
        ({'tolerance': np.nan}, 'tolerance'),
        ({'tolerance': -1e-6}, 'tolerance'),
        ({'k_violations': 0}, 'k_violations'),
        ({'k_violations': 1.5}, 'k_violations'),
        ({'k_violations': True}, 'k_violations'),
        ({'window': 0}, 'window'),
        ({'window': 1.5}, 'window'),
        ({'window': True}, 'window'),
        ({'label': ''}, 'label'),
        ({'label': '   '}, 'label'),
        ({'label': 123}, 'label'),
    ],
)
def test_stability_guard_rejects_invalid_configuration(kwargs, match):
    from sre_control import StabilityGuard

    with pytest.raises(ValueError, match=match):
        StabilityGuard(V_fn=lambda x: float(x[0]), **kwargs)


@pytest.mark.parametrize(
    ('x', 't', 'match'),
    [
        (np.array([np.nan]), 0.0, 'non-finite stability state'),
        (np.array([1.0]), np.nan, 'stability time'),
        (np.array([1.0]), np.inf, 'stability time'),
    ],
)
def test_stability_guard_rejects_invalid_step_inputs(x, t, match):
    from sre_control import AdapterInputError, StabilityGuard

    guard = StabilityGuard(V_fn=lambda state: float(state[0]))

    with pytest.raises(AdapterInputError, match=match):
        guard.step(x, t=t)

    assert guard.triggered is False


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
            if any(
                ev["kind"] == "stability_violation" for ev in entry["runtime"]["events"]
            )
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
        ev
        for ev in sustained_entry["runtime"]["events"]
        if ev["kind"] == "stability_violation"
    ]
    assert trigger_events
    assert not sustained_events
    assert sustained_entry["stability"]["triggered"] is True
    assert "sustained" in sustained_entry["stability"]["local_states"]
    assert "DEGRADED_PLAN" in sustained_entry["runtime"]["states"]
