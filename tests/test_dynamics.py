"""Tests for the bicycle model (§1.2)."""

import numpy as np

from auto_decide.dynamics import (BicycleModel, CircleObstacle, Manifold,
                                   RectObstacle)
from auto_decide.types import Control, State


def test_straight_line_constant_speed():
    dyn = BicycleModel()
    s = State(px=0, py=0, psi=0, v=10.0, a=0.0, mu=1.0)
    u = Control(steer=0.0, jerk=0.0)
    s1 = dyn.step(s, u, dt=0.1)
    assert s1.py == 0.0
    assert abs(s1.px - 1.0) < 1e-6
    assert abs(s1.v - 10.0) < 1e-6


def test_friction_envelope_clamped():
    dyn = BicycleModel()
    # mu=0.5 → max |a| ≤ 4.905
    s = State(px=0, py=0, psi=0, v=10.0, a=4.9, mu=0.5)
    u = Control(steer=0.0, jerk=6.0)
    s1 = dyn.step(s, u, dt=0.1)
    assert abs(s1.a) <= 0.5 * 9.81 + 1e-3


def test_manifold_obstacle_detection():
    obs = [CircleObstacle(cx=10, cy=0, radius=2)]
    m = Manifold(obstacles=obs)
    inside = State(px=10, py=0, psi=0, v=5.0, a=0.0, mu=1.0)
    outside = State(px=20, py=0, psi=0, v=5.0, a=0.0, mu=1.0)
    assert not m.is_feasible(inside)
    assert m.is_feasible(outside)
    assert m.min_distance(outside) > 0
