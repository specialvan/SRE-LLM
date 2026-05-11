"""Tests for nominal policy upgrades (AI-02)."""

import numpy as np

from auto_decide.cbf import make_obstacle_barriers
from auto_decide.dynamics import BicycleModel, CircleObstacle, Manifold
from auto_decide.graph import InteractionIntentGraph
from auto_decide.planner import GradientPolicy, StructuralPlanner
from auto_decide.policies import PredictiveBrakePolicy
from auto_decide.potential import PotentialField
from auto_decide.types import State


def _graph() -> InteractionIntentGraph:
    graph = InteractionIntentGraph()
    graph.update()
    return graph


def test_predictive_brake_wraps_gradient_policy():
    manifold = Manifold(obstacles=[CircleObstacle(20.0, 0.0, 2.0)])
    potential = PotentialField(goal=np.array([50.0, 0.0]), w_goal=0.05)
    inner = GradientPolicy(potential, manifold, target_speed=12.0)
    wrapped = PredictiveBrakePolicy(
        inner=inner,
        barriers=make_obstacle_barriers(manifold, margin=1.5),
        dynamics=BicycleModel(),
    )
    state = State(px=0.0, py=0.0, psi=0.0, v=12.0, a=0.0, mu=1.0)

    u = wrapped(state, _graph())

    assert u.jerk <= -2.0


def test_predictive_brake_does_not_brake_when_no_obstacle_nearby():
    manifold = Manifold(obstacles=[CircleObstacle(200.0, 0.0, 2.0)])
    potential = PotentialField(goal=np.array([50.0, 0.0]), w_goal=0.05)
    inner = GradientPolicy(potential, manifold, target_speed=12.0)
    wrapped = PredictiveBrakePolicy(
        inner=inner,
        barriers=make_obstacle_barriers(manifold, margin=1.5),
        dynamics=BicycleModel(),
    )
    state = State(px=0.0, py=0.0, psi=0.0, v=8.0, a=0.0, mu=1.0)

    u_inner = inner(state, _graph())
    u_wrapped = wrapped(state, _graph())

    assert u_wrapped.jerk == u_inner.jerk


def test_structural_planner_auto_wraps_gradient_policy():
    manifold = Manifold(obstacles=[CircleObstacle(20.0, 0.0, 2.0)])
    planner = StructuralPlanner(
        dynamics=BicycleModel(),
        manifold=manifold,
        target_speed=12.0,
    )

    assert isinstance(planner.nominal, PredictiveBrakePolicy)
