from __future__ import annotations

from pathlib import Path
import re

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]

from sre_control import (
    CanaryScheduler,
    FastTrafficSwitcher,
    Instance,
    PoolCapacityPlanner,
    PredictiveAutoscaler,
    Signal,
    SignalFusion,
    SLOGuardrail,
    StabilityGuard,
    TopologyState,
    WeightedLoadBalancer,
)
from sre_control import RecoverableControlError
from sre_control.events import EVENT_COUNTEREXAMPLES, make_event, validate_event


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
    events.extend(
        topology.step(
            velocity=[0, 0, 0],
            angular_velocity=[0.1, 0.0, 0.0],
            dt=0.05,
        )["events"]
    )

    canary = CanaryScheduler(slo_error_budget=0.01, eta_init=0.10)
    events.extend(
        canary.observe(
            current_share=0.0,
            proposed_share=0.10,
            observed_error_rate=0.03,
        ).events
    )

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
    autoscaler.step(current_replicas=10, observed_rps=1_000, forecast_rps=3_000)
    events.extend(autoscaler.last_trace["events"])

    switcher = FastTrafficSwitcher(rate_max=0.4)
    _, _, switch_info = switcher.plan(
        share_from=0.0,
        share_to=1.0,
        deadline_s=0.5,
    )
    events.extend(switch_info["events"])

    balancer = WeightedLoadBalancer(
        instances=[
            Instance("east", np.array([1.0, 0.0]), rps_min=10, rps_max=100),
            Instance("west", np.array([0.0, 1.0]), rps_min=10, rps_max=100),
        ]
    )
    _, alloc_info = balancer.allocate(
        rps_demand=500,
        zone_target=[250, 250],
    )
    events.extend(alloc_info["events"])

    # outlier_rejected: fusion with a tight gate and a 10-sigma reading
    gated_fusion = SignalFusion(
        x0=np.array([1000.0, 25.0, 0.3]),
        P0=np.diag([10**2, 2**2, 0.05**2]),
        Q=np.diag([0.1, 0.01, 0.001]),
        x_ref=np.array([1000.0, 25.0, 0.3]),
        theta=0.2,
        gate_threshold=3.0,
    )
    events.extend(
        gated_fusion.step(
            dt=1.0,
            readings=[(sig, np.array([5000.0, 200.0]))],  # way outside 3-sigma
        )["events"]
    )

    # adapter_exception: force a recoverable adapter failure inside
    # SREControlStack.step. This keeps the test deterministic instead of
    # relying on numerical edge cases.
    from sre_control import SREControlStack

    class _RecoverableFusion(SignalFusion):
        def step(self, dt, readings):
            raise RecoverableControlError("synthetic fusion outage")

    crashing = _RecoverableFusion(
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
    guard_stack = SLOGuardrail(
        nominal_direction=np.array([1.0, 0.0, 0.0]),
        theta_max_deg=20.0,
        magnitude_cap=10_000.0,
    )
    balancer_stack = WeightedLoadBalancer(
        instances=[
            Instance("east", np.array([1.0, 0.0]), rps_min=1.0, rps_max=500.0),
            Instance("west", np.array([0.0, 1.0]), rps_min=1.0, rps_max=500.0),
        ]
    )
    stack = SREControlStack(
        fusion=crashing,
        autoscaler=autoscaler,
        guardrail=guard_stack,
        balancer=balancer_stack,
    )
    entry = stack.step(
        dt=5.0,
        sensor_readings=[(sig, np.array([750.0, 28.0]))],
        forecast_rps=800.0,
        current_replicas=6,
        zone_target=np.array([480.0, 320.0]),
        nn_proposal=np.array([500.0, 50.0, 10.0]),
    )
    events.extend(
        [e for e in entry["runtime"]["events"] if e["kind"] == "adapter_exception"]
    )

    guard = StabilityGuard(
        V_fn=lambda x: float(x[0]),
        tolerance=0.0,
        k_violations=1,
        window=2,
        label="schema",
    )
    guard.step(np.array([1.0]), t=0.0)
    events.extend(guard.step(np.array([2.0]), t=1.0)["events"])

    return events


def test_all_runtime_events_follow_shared_schema():
    events = _collect_local_events()
    assert {event["kind"] for event in events} == set(EVENT_COUNTEREXAMPLES)
    assert all(validate_event(event) for event in events)


def test_adapter_exception_event_includes_machine_readable_cause_fields():
    event = make_event(
        stage="SignalFusion",
        kind="adapter_exception",
        detail="RecoverableControlError: temporary failure",
        safe_action="substitute observe fallback and continue tick",
        exception_type="RecoverableControlError",
        cause_type="control_domain",
        recoverable=True,
    )

    assert validate_event(event)
    assert event["exception_type"] == "RecoverableControlError"
    assert event["cause_type"] == "control_domain"
    assert event["recoverable"] is True


def test_every_event_kind_has_a_specific_counterexample():
    for kind, counterexample in EVENT_COUNTEREXAMPLES.items():
        assert kind
        assert len(counterexample) >= 60
        assert counterexample.startswith(("Do not", "Avoid"))


def _parse_markdown_table_rows(text: str, header: str) -> list[list[str]]:
    start = text.index(header)
    lines = text[start:].splitlines()
    rows: list[list[str]] = []
    in_table = False
    for line in lines[1:]:
        if not line.startswith("|"):
            if in_table:
                break
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not in_table:
            in_table = True
            continue
        if cells and all(re.fullmatch(r"-+", cell) for cell in cells):
            continue
        rows.append(cells)
    return rows


def test_event_schema_doc_kinds_match_registry():
    doc = (REPO_ROOT / "docs" / "EVENT_SCHEMA.md").read_text(encoding="utf-8")
    rows = _parse_markdown_table_rows(doc, "## 2. Current Event Kinds")
    documented_kinds = {row[0].strip("`") for row in rows}

    assert documented_kinds == set(EVENT_COUNTEREXAMPLES)


def test_runtime_states_doc_emitters_match_registry():
    doc = (REPO_ROOT / "docs" / "RUNTIME_STATES.md").read_text(encoding="utf-8")
    rows = _parse_markdown_table_rows(doc, "Current local event emitters:")
    documented_emitters = {
        (row[0].strip("`") , row[1].strip("`")): {
            kind.strip().strip("`") for kind in row[2].split(",") if kind.strip()
        }
        for row in rows
    }

    assert documented_emitters == {
        ("PoolCapacityPlanner.plan()", 'info["events"]'): {"pool_capacity_clipped"},
        ("SignalFusion.step()", 'trace["events"]'): {"missing_sensor", "outlier_rejected"},
        ("CanaryScheduler.observe()", "CanaryStep.events"): {"rollout_rejected"},
        ("TopologyState.step()", 'trace["events"]'): {"topology_state_repaired"},
        ("SLOGuardrail.audit()", 'audit["events"]'): {"unsafe_proposal_projected"},
        ("PredictiveAutoscaler.step()", "last_trace[\"events\"]"): {"replica_bound_active"},
        ("FastTrafficSwitcher.plan()", 'info["events"]'): {"deadline_exceeded"},
        ("WeightedLoadBalancer.allocate()", 'info["events"]'): {"bounded_ls_residual"},
        ("StabilityGuard.step()", 'trace["events"]'): {"stability_violation"},
        ("SREControlStack.step()", 'entry["runtime"]["events"]'): {"adapter_exception"},
    }

