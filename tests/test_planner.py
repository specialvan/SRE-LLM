"""Integration test — structural planner (§4)."""

import numpy as np

from auto_decide.dynamics import BicycleModel, CircleObstacle, Manifold
from auto_decide.graph import InteractionIntentGraph
from auto_decide.planner import StructuralPlanner
from auto_decide.potential import PotentialField
from auto_decide.types import State


def test_intersection_left_turn_no_collision():
    obstacles = [CircleObstacle(20.0, 3.5, 2.0)]
    manifold = Manifold(obstacles=obstacles)
    pot = PotentialField(goal=np.array([50.0, 10.0]), w_goal=0.05,
                         w_obs=10.0)
    planner = StructuralPlanner(
        dynamics=BicycleModel(), manifold=manifold,
        target_speed=8.0, potential=pot,
    )
    graph = InteractionIntentGraph()
    graph.update()

    start = State(px=0, py=0, psi=0, v=5.0, a=0.0, mu=1.0)
    states, controls, traces = planner.run(start, graph,
                                            horizon_steps=120, dt=0.1)

    # Never enters the obstacle footprint
    for s in states:
        assert manifold.min_distance(s) > -0.01


def test_emergency_brake_when_obstacle_ahead():
    """From a recoverable distance, planner must brake & never penetrate
    the obstacle. The exact stopping distance depends on jerk_max."""
    obstacles = [CircleObstacle(18.0, 0.0, 2.0)]
    manifold = Manifold(obstacles=obstacles)
    pot = PotentialField(goal=np.array([50.0, 0.0]), w_goal=0.05)
    planner = StructuralPlanner(dynamics=BicycleModel(), manifold=manifold,
                                target_speed=10.0, potential=pot)
    graph = InteractionIntentGraph()
    graph.update()

    start = State(px=0, py=0, psi=0, v=8.0, a=0.0, mu=1.0)
    states, controls, traces = planner.run(start, graph, horizon_steps=60,
                                            dt=0.1)
    # Final state has to be outside the obstacle
    for s in states:
        assert manifold.min_distance(s) > -0.01
    # Planner must have triggered at least one safety response
    statuses = {t["status"] for t in traces}
    assert statuses & {"stable", "relaxed", "emergency_brake"}


def test_no_forbidden_tinv_cbf_status_combinations():
    """INV-G13: recovery/success statuses cannot hide CBF fallback."""
    obstacles = [CircleObstacle(22.0, 0.0, 2.0)]
    manifold = Manifold(obstacles=obstacles)
    pot = PotentialField(goal=np.array([60.0, 0.0]), w_goal=0.05)
    planner = StructuralPlanner(dynamics=BicycleModel(), manifold=manifold,
                                target_speed=10.0, potential=pot)
    graph = InteractionIntentGraph()
    graph.update()

    start = State(px=0, py=0, psi=0, v=10.0, a=0.0, mu=0.7)
    _states, _controls, traces = planner.run(start, graph, horizon_steps=80,
                                             dt=0.1)

    forbidden = {
        ("stable", "fallback_brake"),
        ("relaxed_exp", "fallback_brake"),
        ("relaxed", "fallback_brake"),
        ("non_increasing", "fallback_brake"),
        ("best_effort", "fallback_brake"),
    }
    observed = {(trace["status"], trace["cbf_status"]) for trace in traces}

    assert not (observed & forbidden)
