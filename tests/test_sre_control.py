"""Unit tests for the sre_control adapters."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
import sre_control.weighted_balancer as weighted_balancer
from scipy.linalg import expm

from sre_control import (CanaryScheduler, FastTrafficSwitcher,
                          Instance, PoolCapacityPlanner,
                          PredictiveAutoscaler, Signal, SignalFusion,
                          AdapterInputError, RecoverableControlError,
                          SLOGuardrail, TopologyState,
                          WeightedLoadBalancer)


# ---------------------------------------------------------------------------
# §1 PoolCapacityPlanner
# ---------------------------------------------------------------------------

def test_pool_planner_respects_keep_alive_floor():
    planner = PoolCapacityPlanner(min_keep_alive=4, max_capacity=100)
    plan, info = planner.plan(demand_rps_forecast=[0, 50, 500, 1_200, 0])
    # With keep-alive floor, every positive-demand slot is ≥ 4.
    assert all(s >= 4 for s in plan if s > 0)
    assert max(plan) <= 100
    assert info["violations_after"] == 0
    assert info["events"] == []


def test_pool_planner_uses_true_ceiling_at_integer_demand():
    planner = PoolCapacityPlanner(min_keep_alive=1, max_capacity=100)

    plan, _info = planner.plan(demand_rps_forecast=[200.0, 200.1, 300.0])

    assert plan == [2, 3, 3]


def test_pool_planner_uses_configured_rps_per_connection():
    planner = PoolCapacityPlanner(
        min_keep_alive=1,
        max_capacity=5,
        rps_per_conn=50.0,
    )

    plan, info = planner.plan(demand_rps_forecast=[100.0, 125.0, 300.0])

    assert plan == [2, 3, 5]
    assert info["capacity_shortfall_rps"] == 50.0


def test_pool_planner_marks_capacity_clip_event():
    planner = PoolCapacityPlanner(min_keep_alive=4, max_capacity=5)
    plan, info = planner.plan(demand_rps_forecast=[100, 800, 1_200])
    assert max(plan) == 5
    assert info["capacity_shortfall_rps"] > 0
    assert "clip" in info["local_states"]
    assert any(event["kind"] == "pool_capacity_clipped"
               for event in info["events"])


def test_pool_planner_marks_exact_capacity_as_advisory_event():
    planner = PoolCapacityPlanner(
        min_keep_alive=1,
        max_capacity=5,
        rps_per_conn=100.0,
    )

    plan, info = planner.plan(demand_rps_forecast=[500.0])

    assert plan == [5]
    assert "clip" in info["local_states"]
    event = next(event for event in info["events"]
                 if event["kind"] == "pool_capacity_clipped")
    assert event["clipped_slots"] == 0
    assert event["capacity_shortfall_rps"] == 0.0


# ---------------------------------------------------------------------------
# §2 CanaryScheduler
# ---------------------------------------------------------------------------

def test_canary_shrinks_trust_region_on_slo_burn():
    sched = CanaryScheduler(slo_error_budget=0.01,
                             eta_init=0.10, eta_min=0.005, eta_max=0.30)
    step = sched.observe(current_share=0.0, proposed_share=0.10,
                          observed_error_rate=0.03)   # bad!
    # Trust region should contract
    assert step.trust_region < 0.10
    assert step.accepted is False
    assert "freeze" in step.local_states
    assert any(event["kind"] == "rollout_rejected"
               for event in step.events)


def test_canary_grows_trust_region_when_safe():
    sched = CanaryScheduler(slo_error_budget=0.01,
                             eta_init=0.05, eta_max=0.40)
    step = sched.observe(current_share=0.0, proposed_share=0.05,
                          observed_error_rate=0.002)
    assert step.accepted
    assert step.trust_region >= 0.05     # non-shrinking on success


def test_canary_warm_start_does_not_poison_slope():
    sched = CanaryScheduler(slo_error_budget=0.01,
                             eta_init=0.05, eta_max=0.40)

    step = sched.observe(
        current_share=0.50,
        proposed_share=0.55,
        observed_error_rate=0.002,
    )

    assert step.accepted is True
    assert step.predicted_error_rate == pytest.approx(0.002)
    assert sched._b_est == pytest.approx(0.0)
    assert sched._last_share == pytest.approx(0.55)
    assert sched._last_err == pytest.approx(0.002)
    assert "initialise" in step.local_states


def test_canary_rejected_step_still_refits_slope_from_observation():
    sched = CanaryScheduler(slo_error_budget=0.01, eta_init=0.05)

    step = sched.observe(
        current_share=0.0,
        proposed_share=0.05,
        observed_error_rate=0.03,
    )

    assert step.accepted is False
    assert sched._b_est == pytest.approx(0.6)
    assert sched._last_share == pytest.approx(0.05)
    assert sched._last_err == pytest.approx(0.03)
    assert "refit_rejected" in step.local_states


def test_canary_rejected_warm_start_shrinks_instead_of_expanding():
    sched = CanaryScheduler(
        slo_error_budget=0.01,
        eta_init=0.10,
        eta_min=0.005,
        eta_max=0.30,
    )

    first = sched.observe(
        current_share=0.50,
        proposed_share=0.60,
        observed_error_rate=0.03,
    )
    second = sched.observe(
        current_share=0.50,
        proposed_share=0.60,
        observed_error_rate=0.03,
    )

    assert first.accepted is False
    assert second.accepted is False
    assert first.trust_region < 0.10
    assert second.trust_region <= first.trust_region
    assert "expand" not in second.local_states
    assert "shrink" in second.local_states
    assert second.events[0]["trust_region"] == pytest.approx(second.trust_region)


@pytest.mark.parametrize(
    ('kwargs', 'match'),
    [
        ({'slo_error_budget': np.nan}, 'slo_error_budget'),
        ({'slo_error_budget': 0.0}, 'slo_error_budget'),
        ({'eta_init': np.inf}, 'eta_init'),
        ({'eta_init': 0.0}, 'eta_init'),
        ({'eta_min': 0.0}, 'eta_min'),
        ({'eta_max': -0.1}, 'eta_max'),
        ({'eta_min': 0.2, 'eta_init': 0.1}, 'eta_min <= eta_init <= eta_max'),
        ({'eta_init': 0.3, 'eta_max': 0.2}, 'eta_min <= eta_init <= eta_max'),
        ({'rho_shrink': np.nan}, 'rho_shrink'),
        ({'rho_shrink': -0.1}, 'rho_shrink'),
        ({'rho_grow': np.inf}, 'rho_grow'),
        ({'rho_grow': -0.1}, 'rho_grow'),
        ({'rho_shrink': 0.8, 'rho_grow': 0.2}, 'rho_shrink <= rho_grow'),
    ],
)
def test_canary_rejects_invalid_constructor_inputs(kwargs, match):
    with pytest.raises(ValueError, match=match):
        CanaryScheduler(**kwargs)


@pytest.mark.parametrize(
    ('field', 'value', 'match'),
    [
        ('current_share', np.nan, 'current_share must be finite'),
        ('current_share', -0.1, 'current_share must be within'),
        ('proposed_share', np.inf, 'proposed_share must be finite'),
        ('proposed_share', 1.1, 'proposed_share must be within'),
        ('observed_error_rate', np.nan, 'observed_error_rate must be finite'),
        ('observed_error_rate', -0.01, 'observed_error_rate must be non-negative'),
    ],
)
def test_canary_rejects_invalid_observation_inputs_without_mutation(
    field, value, match
):
    sched = CanaryScheduler(slo_error_budget=0.01, eta_init=0.05)
    kwargs = {
        'current_share': 0.0,
        'proposed_share': 0.05,
        'observed_error_rate': 0.002,
    }
    kwargs[field] = value

    with pytest.raises(AdapterInputError, match=match):
        sched.observe(**kwargs)

    assert sched._b_est == 0.0
    assert sched._last_share == 0.0
    assert sched._last_err == 0.0
    assert sched._eta == pytest.approx(0.05)
    assert sched._initialised is False


@pytest.mark.parametrize(
    ('current_share', 'match'),
    [
        (np.nan, 'current_share must be finite'),
        (np.inf, 'current_share must be finite'),
        (-0.1, 'current_share must be within'),
        (1.1, 'current_share must be within'),
    ],
)
def test_canary_rejects_invalid_proposal_input(current_share, match):
    sched = CanaryScheduler(slo_error_budget=0.01, eta_init=0.05)

    with pytest.raises(AdapterInputError, match=match):
        sched.propose(current_share)


# ---------------------------------------------------------------------------
# §3 TopologyState
# ---------------------------------------------------------------------------

def test_topology_state_preserves_unit_norm():
    ts = TopologyState()
    for _ in range(1000):
        ts.step(velocity=[0, 0, 0],
                angular_velocity=[0.1, -0.05, 0.08], dt=0.05)
    assert abs(np.linalg.norm(ts.q) - 1.0) < 1e-8


def test_topology_state_repairs_invalid_quaternion_event():
    ts = TopologyState(q=np.array([0.0, 0.0, 0.0, 0.0]))
    trace = ts.step(velocity=[0, 0, 0],
                    angular_velocity=[0.1, 0.0, 0.0], dt=0.05)
    assert abs(np.linalg.norm(ts.q) - 1.0) < 1e-8
    assert "repair_unit_norm" in trace["local_states"]
    assert any(event["kind"] == "topology_state_repaired"
               for event in trace["events"])


@pytest.mark.parametrize("angle", [-3.5, -2.5, -1.5, -0.5, 0.5, 1.5, 2.5, 3.5])
def test_topology_ring_angle_wraps_to_principal_interval(angle):
    ts = TopologyState(q=np.array([
        np.cos(angle / 2.0),
        0.0,
        0.0,
        np.sin(angle / 2.0),
    ]))

    wrapped = ts.ring_angle_rad

    assert -np.pi <= wrapped <= np.pi
    assert wrapped == pytest.approx(((angle + np.pi) % (2 * np.pi)) - np.pi)


@pytest.mark.parametrize(
    ('kwargs', 'match'),
    [
        ({'dt': 0.0}, 'dt must be positive and finite'),
        ({'dt': -0.1}, 'dt must be positive and finite'),
        ({'dt': np.nan}, 'dt must be positive and finite'),
        ({'velocity': [np.nan, 0.0, 0.0]}, 'non-finite topology velocity'),
        ({'angular_velocity': [0.0, np.inf, 0.0]}, 'non-finite angular velocity'),
    ],
)
def test_topology_state_rejects_invalid_step_inputs_without_mutation(kwargs, match):
    ts = TopologyState(
        position=np.array([1.0, 2.0, 3.0]),
        q=np.array([1.0, 0.0, 0.0, 0.0]),
        omega=np.array([0.01, 0.02, 0.03]),
    )
    before_position = ts.position.copy()
    before_q = ts.q.copy()
    before_omega = ts.omega.copy()
    call = {
        'velocity': [0.1, 0.2, 0.3],
        'angular_velocity': [0.01, 0.02, 0.03],
        'dt': 0.05,
    }
    call.update(kwargs)

    with pytest.raises(AdapterInputError, match=match):
        ts.step(**call)

    assert np.allclose(ts.position, before_position)
    assert np.allclose(ts.q, before_q)
    assert np.allclose(ts.omega, before_omega)


# ---------------------------------------------------------------------------
# §4 SLOGuardrail
# ---------------------------------------------------------------------------

def test_guardrail_projects_into_cone_and_ball():
    guard = SLOGuardrail(
        nominal_direction=np.array([0, 0, 1.0]),
        theta_max_deg=15.0,
        magnitude_cap=1000.0,
    )
    audit = guard.audit([900, 900, 0])     # very off-axis + within ball
    assert audit["cone_violated_before"] is True
    assert audit["cone_margin_after"] >= -1e-3
    assert "projected" in audit["local_states"]
    assert any(event["kind"] == "unsafe_proposal_projected"
               for event in audit["events"])


def test_guardrail_honours_magnitude_cap():
    guard = SLOGuardrail(
        nominal_direction=np.array([0, 0, 1.0]),
        theta_max_deg=30.0,
        magnitude_cap=100.0,
    )
    u = guard.approve([0, 0, 10_000])
    assert np.linalg.norm(u) <= 100.0 + 1e-6


@pytest.mark.parametrize("proposal", [
    [np.nan, 0.0, 0.0],
    [np.inf, 0.0, 0.0],
    [0.0, -np.inf, 0.0],
])
def test_guardrail_rejects_non_finite_proposal(proposal):
    guard = SLOGuardrail(
        nominal_direction=np.array([0, 0, 1.0]),
        theta_max_deg=30.0,
        magnitude_cap=100.0,
    )

    with pytest.raises(AdapterInputError, match="non-finite proposal"):
        guard.audit(proposal)


@pytest.mark.parametrize("proposal", [
    [np.nan, 0.0, 0.0],
    [np.inf, 0.0, 0.0],
    [0.0, -np.inf, 0.0],
])
def test_guardrail_approve_rejects_non_finite_proposal(proposal):
    guard = SLOGuardrail(
        nominal_direction=np.array([0, 0, 1.0]),
        theta_max_deg=30.0,
        magnitude_cap=100.0,
    )

    with pytest.raises(AdapterInputError, match="non-finite proposal"):
        guard.approve(proposal)


# ---------------------------------------------------------------------------
# §5 SignalFusion
# ---------------------------------------------------------------------------

def test_signal_fusion_converges_to_truth():
    rng = np.random.default_rng(0)
    truth = np.array([1200.0, 30.0, 0.4])   # QPS, latency_ms, CPU%
    fusion = SignalFusion(
        x0=np.array([1000.0, 25.0, 0.3]),
        P0=np.diag([200**2, 10**2, 0.2**2]),
        Q=np.diag([10.0, 0.5, 0.01]),
        x_ref=truth,
        theta=0.2,
    )
    # Sensor: direct observer of (QPS, latency_ms) only
    sig = Signal(
        name="metrics",
        h=lambda x: x[0:2],
        H=lambda x: np.array([[1, 0, 0], [0, 1, 0]]),
        R=np.diag([50**2, 4**2]),
    )
    for _ in range(200):
        z = truth[0:2] + rng.multivariate_normal([0, 0], sig.R)
        fusion.step(dt=1.0, readings=[(sig, z)])
    err = np.linalg.norm(fusion.state[0:2] - truth[0:2])
    assert err < 30.0


def test_signal_fusion_marks_missing_sensor_as_local_event():
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
    trace = fusion.step(dt=1.0, readings=[(sig, None)])
    assert trace["signals"][0]["used"] is False
    assert "skip_update" in trace["local_states"]
    assert any(event["kind"] == "missing_sensor"
               for event in trace["events"])


def test_signal_fusion_ou_prediction_uses_stable_exact_discretization():
    fusion = SignalFusion(
        x0=np.array([10.0]),
        P0=np.eye(1),
        Q=np.eye(1) * 0.01,
        x_ref=np.array([0.0]),
        theta=0.5,
    )

    trace = fusion.step(dt=5.0, readings=[])

    transition = expm(-0.5 * np.eye(1) * 5.0)
    expected_state = (transition @ np.array([10.0]))[0]
    assert trace["x"][0] == pytest.approx(expected_state)
    assert trace["x"][0] > 0.0


def test_signal_fusion_gates_outlier_when_threshold_is_set():
    """Innovation gating skips a 10σ reading and emits an event."""
    fusion = SignalFusion(
        x0=np.array([1000.0, 25.0, 0.3]),
        P0=np.diag([10**2, 2**2, 0.05**2]),
        Q=np.diag([0.1, 0.01, 0.001]),
        x_ref=np.array([1000.0, 25.0, 0.3]),
        theta=0.2,
        gate_threshold=3.0,
    )
    sig = Signal(
        name="metrics",
        h=lambda x: x[0:2],
        H=lambda x: np.array([[1, 0, 0], [0, 1, 0]]),
        R=np.diag([50**2, 4**2]),
    )
    x_before = fusion.state.copy()
    trace = fusion.step(dt=1.0, readings=[(sig, np.array([5000.0, 200.0]))])

    # Posterior must be unchanged (gated + predict was neutral OU pull)
    assert np.allclose(fusion.state, x_before, atol=0.5)
    assert trace["signals"][0]["used"] is False
    assert trace["signals"][0]["gated"] is True
    assert trace["signals"][0]["innovation_mahalanobis"] > 3.0
    assert "outlier_rejected" in trace["local_states"]
    assert any(event["kind"] == "outlier_rejected"
               for event in trace["events"])


def test_signal_fusion_without_gate_accepts_outlier_like_before():
    """Disabling gating keeps legacy behaviour: big reading pulls posterior."""
    fusion = SignalFusion(
        x0=np.array([1000.0, 25.0, 0.3]),
        P0=np.diag([10**2, 2**2, 0.05**2]),
        Q=np.diag([0.1, 0.01, 0.001]),
        x_ref=np.array([1000.0, 25.0, 0.3]),
        theta=0.2,
        # gate_threshold=None  ← default, legacy behaviour
    )
    sig = Signal(
        name="metrics",
        h=lambda x: x[0:2],
        H=lambda x: np.array([[1, 0, 0], [0, 1, 0]]),
        R=np.diag([50**2, 4**2]),
    )
    trace = fusion.step(dt=1.0, readings=[(sig, np.array([5000.0, 200.0]))])
    # posterior should have moved toward the reading
    assert fusion.state[0] > 1050.0
    assert trace["signals"][0]["used"] is True
    # gated key only appears when update was gated; absence == accepted
    assert trace["signals"][0].get("gated", False) is False


def test_signal_fusion_per_sensor_gate_rejects_one_accepts_other():
    """PR-D: one sensor rejected, the other accepted in the *same tick*."""
    fusion = SignalFusion(
        x0=np.array([1000.0, 25.0, 0.3]),
        P0=np.diag([10**2, 2**2, 0.05**2]),
        Q=np.diag([0.1, 0.01, 0.001]),
        x_ref=np.array([1000.0, 25.0, 0.3]),
        theta=0.0,
        # No fusion-wide default; per-sensor gates fully decide here.
        gate_threshold=None,
    )
    # Tight gate on the metrics channel so a 10σ reading trips it.
    strict = Signal(
        name="metrics",
        h=lambda x: x[0:2],
        H=lambda x: np.array([[1, 0, 0], [0, 1, 0]]),
        R=np.diag([50**2, 4**2]),
        gate_threshold=3.0,
    )
    # Loose gate (or none) on the second sensor so a benign reading
    # passes; here we leave it None so it inherits None from the
    # fusion-wide default, i.e. no gating at all.
    relaxed = Signal(
        name="rum",
        h=lambda x: np.array([x[2]]),
        H=lambda x: np.array([[0, 0, 1]]),
        R=np.diag([0.05**2]),
        gate_threshold=None,
    )
    x_before = fusion.state.copy()
    trace = fusion.step(
        dt=1.0,
        readings=[
            (strict, np.array([5000.0, 200.0])),  # 10σ outlier → reject
            (relaxed, np.array([0.31])),          # nominal      → accept
        ],
    )

    metrics_entry = next(s for s in trace["signals"] if s["signal"] == "metrics")
    rum_entry = next(s for s in trace["signals"] if s["signal"] == "rum")

    # metrics: rejected, posterior protected
    assert metrics_entry["used"] is False
    assert metrics_entry["gated"] is True
    assert metrics_entry["threshold_used"] == 3.0
    assert metrics_entry["innovation_mahalanobis"] > 3.0
    assert metrics_entry["consecutive_rejections"] == 1

    # rum: accepted, threshold_used is None (no gate configured for this sensor)
    assert rum_entry["used"] is True
    assert rum_entry["threshold_used"] is None
    assert rum_entry["consecutive_rejections"] == 0

    # First two state components untouched by the rejected metrics sample.
    assert np.isclose(fusion.state[0], x_before[0], atol=0.5)
    assert np.isclose(fusion.state[1], x_before[1], atol=0.5)
    # CPU component was updated by the accepted rum reading.
    assert fusion.state[2] != x_before[2]


def test_signal_fusion_signal_gate_overrides_fusion_default():
    """A Signal-level gate beats the fusion-wide default even when set."""
    fusion = SignalFusion(
        x0=np.array([1000.0, 25.0, 0.3]),
        P0=np.diag([10**2, 2**2, 0.05**2]),
        Q=np.diag([0.1, 0.01, 0.001]),
        x_ref=np.array([1000.0, 25.0, 0.3]),
        theta=0.0,
        gate_threshold=3.0,         # fusion default would reject
    )
    # Per-sensor override = very permissive ⇒ the same outlier is accepted.
    permissive = Signal(
        name="metrics",
        h=lambda x: x[0:2],
        H=lambda x: np.array([[1, 0, 0], [0, 1, 0]]),
        R=np.diag([50**2, 4**2]),
        gate_threshold=100.0,
    )
    trace = fusion.step(
        dt=1.0,
        readings=[(permissive, np.array([5000.0, 200.0]))],
    )
    entry = trace["signals"][0]
    assert entry["used"] is True
    assert entry["threshold_used"] == 100.0
    assert entry.get("gated", False) is False


def test_signal_fusion_inherits_fusion_default_when_signal_has_no_override():
    """A Signal without an override inherits the fusion-wide gate."""
    fusion = SignalFusion(
        x0=np.array([1000.0, 25.0, 0.3]),
        P0=np.diag([10**2, 2**2, 0.05**2]),
        Q=np.diag([0.1, 0.01, 0.001]),
        x_ref=np.array([1000.0, 25.0, 0.3]),
        theta=0.0,
        gate_threshold=3.0,
    )
    inherited = Signal(
        name="metrics",
        h=lambda x: x[0:2],
        H=lambda x: np.array([[1, 0, 0], [0, 1, 0]]),
        R=np.diag([50**2, 4**2]),
        gate_threshold=None,
    )
    x_before = fusion.state.copy()
    trace = fusion.step(
        dt=1.0,
        readings=[(inherited, np.array([5000.0, 200.0]))],
    )
    entry = trace["signals"][0]
    assert entry["used"] is False
    assert entry["gated"] is True
    assert entry["threshold_used"] == 3.0
    assert entry["innovation_mahalanobis"] > 3.0
    assert np.allclose(fusion.state, x_before, atol=0.5)


@pytest.mark.parametrize("threshold", [0.0, -1.0])
def test_signal_rejects_nonpositive_gate_threshold(threshold):
    with pytest.raises(ValueError, match="gate_threshold"):
        Signal(
            name="metrics",
            h=lambda x: x,
            H=lambda x: np.eye(1),
            R=np.eye(1),
            gate_threshold=threshold,
        )


@pytest.mark.parametrize("threshold", [0.0, -1.0])
def test_signal_fusion_rejects_nonpositive_default_gate_threshold(threshold):
    with pytest.raises(ValueError, match="gate_threshold"):
        SignalFusion(
            x0=np.array([1.0]),
            P0=np.eye(1),
            Q=np.eye(1) * 0.01,
            x_ref=np.array([1.0]),
            gate_threshold=threshold,
        )


def test_signal_fusion_consecutive_rejections_reset_on_acceptance():
    """Counter increments on rejects, resets on a successful update."""
    fusion = SignalFusion(
        x0=np.array([1000.0, 25.0, 0.3]),
        P0=np.diag([10**2, 2**2, 0.05**2]),
        Q=np.diag([1e-3, 1e-3, 1e-4]),
        x_ref=np.array([1000.0, 25.0, 0.3]),
        theta=0.0,
    )
    sig = Signal(
        name="metrics",
        h=lambda x: x[0:2],
        H=lambda x: np.array([[1, 0, 0], [0, 1, 0]]),
        R=np.diag([50**2, 4**2]),
        gate_threshold=3.0,
    )

    # Two rejects in a row.
    for _ in range(2):
        fusion.step(dt=1.0, readings=[(sig, np.array([5000.0, 200.0]))])
    trace = fusion.step(dt=1.0, readings=[(sig, np.array([5000.0, 200.0]))])
    assert trace["signals"][0]["consecutive_rejections"] == 3

    # One nominal reading clears the counter.
    cleared = fusion.step(dt=1.0, readings=[(sig, np.array([1000.0, 25.0]))])
    assert cleared["signals"][0]["used"] is True
    assert cleared["signals"][0]["consecutive_rejections"] == 0


def test_signal_fusion_consecutive_rejections_are_capped():
    fusion = SignalFusion(
        x0=np.array([1000.0, 25.0, 0.3]),
        P0=np.diag([10**2, 2**2, 0.05**2]),
        Q=np.diag([1e-3, 1e-3, 1e-4]),
        x_ref=np.array([1000.0, 25.0, 0.3]),
        theta=0.0,
        max_consecutive_rejections=2,
    )
    sig = Signal(
        name="metrics",
        h=lambda x: x[0:2],
        H=lambda x: np.array([[1, 0, 0], [0, 1, 0]]),
        R=np.diag([50**2, 4**2]),
        gate_threshold=3.0,
    )

    for _ in range(4):
        trace = fusion.step(dt=1.0, readings=[(sig, np.array([5000.0, 200.0]))])

    assert trace["signals"][0]["consecutive_rejections"] == 2
    assert trace["signals"][0]["rejection_counter_saturated"] is True
    assert "rejection_counter_saturated" in trace["local_states"]
    event = next(ev for ev in trace["events"] if ev["kind"] == "outlier_rejected")
    assert event["consecutive_rejections"] == 2


@pytest.mark.parametrize("max_rejections", [0, -1, True])
def test_signal_fusion_rejects_invalid_rejection_counter_cap(max_rejections):
    with pytest.raises(ValueError, match="max_consecutive_rejections"):
        SignalFusion(
            x0=np.array([1.0]),
            P0=np.eye(1),
            Q=np.eye(1) * 0.01,
            x_ref=np.array([1.0]),
            max_consecutive_rejections=max_rejections,
        )


def test_signal_fusion_rejects_duplicate_signal_names_in_tick():
    fusion = SignalFusion(
        x0=np.array([1000.0, 25.0]),
        P0=np.eye(2),
        Q=np.eye(2) * 0.01,
        x_ref=np.array([1000.0, 25.0]),
        theta=0.0,
    )
    first = Signal(
        name="metrics",
        h=lambda x: x,
        H=lambda x: np.eye(2),
        R=np.eye(2),
    )
    second = Signal(
        name="metrics",
        h=lambda x: x,
        H=lambda x: np.eye(2),
        R=np.eye(2) * 2.0,
    )

    with pytest.raises(AdapterInputError, match="duplicate signal name"):
        fusion.step(
            dt=1.0,
            readings=[
                (first, np.array([1000.0, 25.0])),
                (second, np.array([1000.0, 25.0])),
            ],
        )


@pytest.mark.parametrize("reading", [
    np.array([np.nan]),
    np.array([np.inf]),
    np.array([-np.inf]),
])
def test_signal_fusion_rejects_non_finite_sensor_reading_without_mutation(reading):
    fusion = SignalFusion(
        x0=np.array([10.0]),
        P0=np.eye(1),
        Q=np.eye(1),
        x_ref=np.array([0.0]),
        theta=0.5,
    )
    sig = Signal(
        name="metrics",
        h=lambda x: x,
        H=lambda x: np.eye(1),
        R=np.eye(1),
    )
    x_before = fusion.state.copy()
    p_before = fusion.covariance.copy()

    with pytest.raises(AdapterInputError, match="non-finite sensor reading"):
        fusion.step(dt=5.0, readings=[(sig, reading)])

    assert np.allclose(fusion.state, x_before)
    assert np.allclose(fusion.covariance, p_before)


# ---------------------------------------------------------------------------
# §6 PredictiveAutoscaler
# ---------------------------------------------------------------------------

def test_autoscaler_responds_to_forecast_growth():
    asc = PredictiveAutoscaler(
        per_replica_rps=100.0, replicas_min=1, replicas_max=50,
        max_step=5, dt=5.0, horizon=6,
    )
    # Forecast jumps from 500 to 2_500 RPS → need to scale up
    next_r = asc.step(current_replicas=5, observed_rps=500,
                       forecast_rps=2_500)
    assert next_r > 5


def test_autoscaler_marks_replica_bound_as_local_event():
    asc = PredictiveAutoscaler(
        per_replica_rps=100.0, replicas_min=1, replicas_max=10,
        max_step=5, dt=5.0, horizon=6,
    )
    next_r = asc.step(current_replicas=10, observed_rps=1_000,
                       forecast_rps=3_000)
    assert next_r == 10
    assert "integerize" in asc.last_trace["local_states"]
    assert any(event["kind"] == "replica_bound_active"
               for event in asc.last_trace["events"])


def test_autoscaler_internal_plant_matches_executor_step_units():
    asc = PredictiveAutoscaler(
        per_replica_rps=100.0, replicas_min=1, replicas_max=50,
        max_step=5, dt=5.0, horizon=2,
    )

    discrete_effect = asc._mpc.B[:, 0]
    assert discrete_effect[0] == pytest.approx(1.0)
    assert discrete_effect[1] == pytest.approx(asc.per_replica_rps)

    current_replicas = 10
    for u in [-1.0, 0.0, 1.0, float(asc.max_step)]:
        model_next_replicas = current_replicas + discrete_effect[0] * u
        executor_next_replicas = current_replicas + u
        assert model_next_replicas == pytest.approx(executor_next_replicas)


@pytest.mark.parametrize(
    ('field', 'value', 'match'),
    [
        ('observed_rps', np.nan, 'observed_rps must be non-negative and finite'),
        ('observed_rps', np.inf, 'observed_rps must be non-negative and finite'),
        ('observed_rps', -1.0, 'observed_rps must be non-negative and finite'),
        ('forecast_rps', np.nan, 'forecast_rps must be non-negative and finite'),
        ('forecast_rps', np.inf, 'forecast_rps must be non-negative and finite'),
        ('forecast_rps', -1.0, 'forecast_rps must be non-negative and finite'),
        ('current_replicas', -1, 'current_replicas must be a non-negative integer'),
        ('current_replicas', 1.5, 'current_replicas must be a non-negative integer'),
        ('current_replicas', True, 'current_replicas must be a non-negative integer'),
    ],
)
def test_autoscaler_rejects_invalid_runtime_inputs_without_trace_mutation(
    field, value, match
):
    asc = PredictiveAutoscaler(
        per_replica_rps=100.0, replicas_min=1, replicas_max=50,
        max_step=5, dt=5.0, horizon=2,
    )
    asc.last_trace = {'previous': True}
    kwargs = {
        'current_replicas': 5,
        'observed_rps': 500.0,
        'forecast_rps': 600.0,
    }
    kwargs[field] = value

    with pytest.raises(AdapterInputError, match=match):
        asc.step(**kwargs)

    assert asc.last_trace == {'previous': True}


# ---------------------------------------------------------------------------
# §7 FastTrafficSwitcher
# ---------------------------------------------------------------------------

def test_switcher_hits_target_with_zero_residual_rate():
    sw = FastTrafficSwitcher(rate_max=0.4)
    t, s, info = sw.plan(share_from=1.0, share_to=0.0)
    assert abs(s[-1] - 0.0) < 1e-6
    assert info["T_min_seconds"] > 0
    assert info["events"] == []


def test_switcher_safety_margin_preserves_terminal_share():
    sw = FastTrafficSwitcher(rate_max=0.4, safety_margin=1.2)
    _, share, info = sw.plan(share_from=0.0, share_to=1.0)

    assert abs(share[-1] - 1.0) < 1e-6
    assert abs(info["final_share"] - 1.0) < 1e-6


def test_switcher_marks_deadline_exceeded_event():
    sw = FastTrafficSwitcher(rate_max=0.4)
    _, _, info = sw.plan(share_from=0.0, share_to=1.0,
                         deadline_s=0.5)
    assert info["T_min_seconds"] > 0.5
    assert "switch_midpoint" in info["local_states"]
    assert any(event["kind"] == "deadline_exceeded"
               for event in info["events"])


@pytest.mark.parametrize("rate_max", [0.0, -0.1])
def test_switcher_rejects_nonpositive_rate_max(rate_max):
    with pytest.raises(ValueError, match="rate_max"):
        FastTrafficSwitcher(rate_max=rate_max)


# ---------------------------------------------------------------------------
# §8 WeightedLoadBalancer
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ('kwargs', 'match'),
    [
        ({'share_from': np.nan}, 'share_from must be finite'),
        ({'share_to': np.inf}, 'share_to must be finite'),
        ({'dt': 0.0}, 'dt must be positive and finite'),
        ({'dt': -0.1}, 'dt must be positive and finite'),
        ({'dt': np.nan}, 'dt must be positive and finite'),
        ({'deadline_s': np.nan}, 'deadline_s must be positive and finite'),
        ({'deadline_s': 0.0}, 'deadline_s must be positive and finite'),
    ],
)
def test_switcher_rejects_invalid_plan_inputs(kwargs, match):
    sw = FastTrafficSwitcher(rate_max=0.4)
    call = {
        'share_from': 0.0,
        'share_to': 1.0,
        'dt': 0.1,
        'deadline_s': None,
    }
    call.update(kwargs)

    with pytest.raises(AdapterInputError, match=match):
        sw.plan(**call)


@pytest.mark.parametrize('rate_max', [np.nan, np.inf])
def test_switcher_rejects_nonfinite_rate_max(rate_max):
    with pytest.raises(ValueError, match='rate_max'):
        FastTrafficSwitcher(rate_max=rate_max)


@pytest.mark.parametrize('safety_margin', [0.0, -1.0, np.nan, np.inf])
def test_switcher_rejects_invalid_safety_margin(safety_margin):
    with pytest.raises(ValueError, match='safety_margin'):
        FastTrafficSwitcher(rate_max=0.4, safety_margin=safety_margin)


def test_balancer_matches_demand_without_saturating():
    lb = WeightedLoadBalancer(instances=[
        Instance("east-a", np.array([1.0, 0.0]), rps_min=10, rps_max=500),
        Instance("east-b", np.array([1.0, 0.0]), rps_min=10, rps_max=500),
        Instance("west-a", np.array([0.0, 1.0]), rps_min=10, rps_max=500),
    ])
    shares, info = lb.allocate(rps_demand=900, zone_target=[600, 300])
    assert info["rps_residual"] < 1e-6
    # Should not hit any box
    assert not any(info["saturation"])
    assert info["local_states"] == ["solve_ls"]
    assert info["events"] == []


def test_balancer_quantifies_residual_so_safe_does_not_mean_sufficient():
    lb = WeightedLoadBalancer(instances=[
        Instance("east-a", np.array([1.0, 0.0]), rps_min=0, rps_max=100),
        Instance("west-a", np.array([0.0, 1.0]), rps_min=0, rps_max=100),
    ])

    shares, info = lb.allocate(rps_demand=300, zone_target=[150, 150])

    assert np.all(shares <= 100.0 + 1e-6)
    assert info["demand_satisfied"] is False
    assert info["rps_residual"] >= 100.0 - 1e-6
    assert info["rps_residual_fraction"] >= (100.0 / 300.0) - 1e-6
    event = next(event for event in info["events"] if event["kind"] == "bounded_ls_residual")
    assert event["demand_satisfied"] is False
    assert event["rps_residual"] == info["rps_residual"]
    assert event["rps_residual_fraction"] == info["rps_residual_fraction"]


def test_balancer_rejects_mismatched_zone_vector_dimensions():
    with pytest.raises(ValueError, match="zone_vector dimensions"):
        WeightedLoadBalancer(instances=[
            Instance("east-a", np.array([1.0, 0.0]), rps_min=0, rps_max=100),
            Instance("west-a", np.array([1.0]), rps_min=0, rps_max=100),
        ])


def test_balancer_rejects_non_finite_static_configuration():
    with pytest.raises(ValueError, match="finite zone_vector"):
        WeightedLoadBalancer(instances=[
            Instance("east-a", np.array([np.nan]), rps_min=0.0, rps_max=100.0),
        ])

    with pytest.raises(ValueError, match="finite rps bounds"):
        WeightedLoadBalancer(instances=[
            Instance("east-a", np.array([1.0]), rps_min=0.0, rps_max=np.inf),
        ])

    with pytest.raises(ValueError, match="rps_min <= rps_max"):
        WeightedLoadBalancer(instances=[
            Instance("east-a", np.array([1.0]), rps_min=10.0, rps_max=1.0),
        ])


@pytest.mark.parametrize("demand", [np.nan, np.inf, -np.inf])
def test_balancer_rejects_non_finite_runtime_demand(demand):
    lb = WeightedLoadBalancer(instances=[
        Instance("east-a", np.array([1.0]), rps_min=0.0, rps_max=100.0),
    ])

    with pytest.raises(AdapterInputError, match="non-finite rps_demand"):
        lb.allocate(rps_demand=demand, zone_target=[10.0])


def test_balancer_rejects_invalid_runtime_zone_target():
    lb = WeightedLoadBalancer(instances=[
        Instance("east-a", np.array([1.0, 0.0]), rps_min=0.0, rps_max=100.0),
        Instance("west-a", np.array([0.0, 1.0]), rps_min=0.0, rps_max=100.0),
    ])

    with pytest.raises(AdapterInputError, match="zone_target dimension"):
        lb.allocate(rps_demand=10.0, zone_target=[10.0])

    with pytest.raises(AdapterInputError, match="non-finite zone_target"):
        lb.allocate(rps_demand=10.0, zone_target=[np.nan, 10.0])


def test_balancer_wraps_solver_input_errors_as_recoverable(monkeypatch):
    lb = WeightedLoadBalancer(instances=[
        Instance("east-a", np.array([1.0]), rps_min=0.0, rps_max=100.0),
    ])

    def failing_solver(*_args, **_kwargs):
        raise ValueError("synthetic solver input failure")

    monkeypatch.setattr(weighted_balancer, "lsq_linear", failing_solver)

    with pytest.raises(RecoverableControlError, match="bounded LS solver failed"):
        lb.allocate(rps_demand=10.0, zone_target=[10.0])


def test_balancer_rejects_unsuccessful_solver_result(monkeypatch):
    lb = WeightedLoadBalancer(instances=[
        Instance("east-a", np.array([1.0]), rps_min=0.0, rps_max=100.0),
    ])

    def unsuccessful_solver(*_args, **_kwargs):
        return SimpleNamespace(
            success=False,
            message="iteration limit reached",
            x=np.array([10.0]),
            cost=0.0,
        )

    monkeypatch.setattr(weighted_balancer, "lsq_linear", unsuccessful_solver)

    with pytest.raises(RecoverableControlError,
                       match="bounded LS solver did not converge"):
        lb.allocate(rps_demand=10.0, zone_target=[10.0])
