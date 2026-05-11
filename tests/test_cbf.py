"""Tests for the CBF-QP filter (§3.2)."""

from auto_decide.cbf import (
    BrakingDistanceBarrier,
    CBFQPFilter,
    make_obstacle_barriers,
)
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


def test_braking_distance_barrier_inflates_with_speed_and_low_mu():
    obstacle = CircleObstacle(30.0, 0.0, 2.0)
    barrier = BrakingDistanceBarrier(obstacle, safety_margin=1.5)

    slow_high_mu = State(px=0, py=0, psi=0, v=8.0, a=0.0, mu=1.0)
    fast_high_mu = State(px=0, py=0, psi=0, v=12.0, a=0.0, mu=1.0)
    fast_low_mu = State(px=0, py=0, psi=0, v=12.0, a=0.0, mu=0.35)

    assert barrier.h(fast_high_mu) < barrier.h(slow_high_mu)
    assert barrier.h(fast_low_mu) < barrier.h(fast_high_mu)
    assert barrier.h(fast_low_mu) < 0.0


def test_low_friction_turns_nominal_acceleration_into_brake():
    dyn = BicycleModel()
    manifold = Manifold(obstacles=[CircleObstacle(40.0, 0.0, 2.0)])
    cbf = CBFQPFilter(
        barriers=make_obstacle_barriers(manifold, margin=1.5),
        dynamics=dyn,
        alpha=3.0,
    )
    u_nom = Control(steer=0.0, jerk=5.0)

    high_mu = State(px=0, py=0, psi=0, v=12.0, a=0.0, mu=1.0)
    low_mu = State(px=0, py=0, psi=0, v=12.0, a=0.0, mu=0.35)

    high_u, high_info = cbf.filter(high_mu, u_nom)
    low_u, low_info = cbf.filter(low_mu, u_nom)

    assert high_info["status"] == "nom_ok"
    assert high_u.jerk == u_nom.jerk
    assert low_info["status"] in {"qp_ok", "fallback_brake"}
    assert low_u.jerk < 0.0
