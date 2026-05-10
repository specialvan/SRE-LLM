"""Tests for the CBF-QP filter (§3.2)."""

from auto_decide.cbf import CBFQPFilter, DistanceBarrier, make_obstacle_barriers
from auto_decide.dynamics import BicycleModel, CircleObstacle, Manifold
from auto_decide.types import Control, State


def test_filter_passes_through_safe_command():
    dyn = BicycleModel()
    manifold = Manifold(obstacles=[CircleObstacle(100.0, 0.0, 2.0)])
    cbf = CBFQPFilter(barriers=make_obstacle_barriers(manifold, margin=1.0),
                      dynamics=dyn, alpha=1.0)
    s = State(px=0, py=0, psi=0, v=10.0, a=0.0, mu=1.0)
    u_nom = Control(steer=0.0, jerk=0.0)
    u_safe, info = cbf.filter(s, u_nom)
    assert info["status"] == "nom_ok"
    assert u_safe.jerk == u_nom.jerk


def test_filter_brakes_when_facing_obstacle():
    dyn = BicycleModel()
    manifold = Manifold(obstacles=[CircleObstacle(8.0, 0.0, 2.0)])
    cbf = CBFQPFilter(barriers=make_obstacle_barriers(manifold, margin=1.5),
                      dynamics=dyn, alpha=2.0)
    # Driving straight at 15 m/s, right at the obstacle → unsafe command
    s = State(px=0, py=0, psi=0, v=15.0, a=3.0, mu=1.0)
    u_nom = Control(steer=0.0, jerk=5.0)
    u_safe, info = cbf.filter(s, u_nom)
    # Either we got refined jerk ≤ nom (decelerate), or fallback brake
    assert u_safe.jerk <= u_nom.jerk
    assert info["status"] in {"qp_ok", "fallback_brake"}
