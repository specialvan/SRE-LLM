"""Tests for the structured trace schema."""

import json

import numpy as np

from auto_decide.dynamics import BicycleModel, CircleObstacle, Manifold
from auto_decide.graph import InteractionIntentGraph
from auto_decide.planner import StructuralPlanner
from auto_decide.potential import PotentialField
from auto_decide.trace import TRACE_SCHEMA_VERSION, build_trace_record
from auto_decide.types import Control, State


def test_trace_record_is_json_safe_and_versioned():
    state = State(px=1.0, py=2.0, psi=0.1, v=4.0, a=0.2, mu=1.0)
    next_state = State(px=1.2, py=2.1, psi=0.11, v=4.1, a=0.0, mu=1.0)
    u_nn = Control(steer=0.05, jerk=0.3)
    u_safe = Control(steer=0.02, jerk=-0.1)
    info = {
        "V": 1.25,
        "dV_dt": -0.05,
        "status": "stable",
        "cbf": {
            "status": "qp_ok",
            "slack": float("inf"),
            "violations": [1.0, float("inf")],
        },
    }

    trace = build_trace_record(
        step_index=3,
        dt=0.2,
        state=state,
        next_state=next_state,
        u_nn=u_nn,
        u_safe=u_safe,
        info=info,
        min_dist=4.5,
    )

    assert trace["schema_version"] == TRACE_SCHEMA_VERSION
    assert trace["step"] == 3
    assert abs(trace["t"] - 0.6) < 1e-9
    assert abs(trace["dt"] - 0.2) < 1e-12
    assert trace["cbf_status"] == "qp_ok"
    assert trace["cbf_slack"] is None
    assert trace["cbf_violations"] == [1.0, None]
    json.dumps(trace, allow_nan=False)


def test_planner_run_emits_schema_versioned_jsonl(tmp_path):
    obstacles = [CircleObstacle(20.0, 0.0, 2.0)]
    manifold = Manifold(obstacles=obstacles)
    pot = PotentialField(goal=np.array([50.0, 0.0]), w_goal=0.05)
    planner = StructuralPlanner(
        dynamics=BicycleModel(),
        manifold=manifold,
        target_speed=8.0,
        potential=pot,
    )
    graph = InteractionIntentGraph()
    graph.update()

    start = State(px=0.0, py=0.0, psi=0.0, v=5.0, a=0.0, mu=1.0)
    trace_path = tmp_path / "trace.jsonl"
    states, controls, traces = planner.run(
        start, graph, horizon_steps=3, dt=0.1, trace_path=str(trace_path)
    )

    assert len(states) == 4
    assert len(controls) == 3
    assert len(traces) == 3

    lines = trace_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3

    first = json.loads(lines[0])
    assert first["schema_version"] == TRACE_SCHEMA_VERSION
    assert first["step"] == 0
    assert first["dt"] == 0.1
    assert len(first["state"]) == 6
    assert len(first["u_safe"]) == 2
    assert first["cbf_status"] in {"nom_ok", "qp_ok", "fallback_brake"}
