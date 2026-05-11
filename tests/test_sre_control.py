"""Unit tests for the sre_control adapters."""

from __future__ import annotations

import numpy as np

from sre_control import (CanaryScheduler, FastTrafficSwitcher,
                          Instance, PoolCapacityPlanner,
                          PredictiveAutoscaler, Signal, SignalFusion,
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


def test_canary_grows_trust_region_when_safe():
    sched = CanaryScheduler(slo_error_budget=0.01,
                             eta_init=0.05, eta_max=0.40)
    step = sched.observe(current_share=0.0, proposed_share=0.05,
                          observed_error_rate=0.002)
    assert step.accepted
    assert step.trust_region >= 0.05     # non-shrinking on success


# ---------------------------------------------------------------------------
# §3 TopologyState
# ---------------------------------------------------------------------------

def test_topology_state_preserves_unit_norm():
    ts = TopologyState()
    for _ in range(1000):
        ts.step(velocity=[0, 0, 0],
                angular_velocity=[0.1, -0.05, 0.08], dt=0.05)
    assert abs(np.linalg.norm(ts.q) - 1.0) < 1e-8


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


# ---------------------------------------------------------------------------
# §7 FastTrafficSwitcher
# ---------------------------------------------------------------------------

def test_switcher_hits_target_with_zero_residual_rate():
    sw = FastTrafficSwitcher(rate_max=0.4)
    t, s, info = sw.plan(share_from=1.0, share_to=0.0)
    assert abs(s[-1] - 0.0) < 1e-6
    assert info["T_min_seconds"] > 0


# ---------------------------------------------------------------------------
# §8 WeightedLoadBalancer
# ---------------------------------------------------------------------------

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
