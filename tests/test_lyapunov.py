"""Tests for Lyapunov stability (§2.1)."""

from auto_decide.dynamics import BicycleModel, CircleObstacle, Manifold
from auto_decide.lyapunov import QuadraticLyapunov, StabilityMonitor
from auto_decide.types import Control, State


def _setup(v=10.0, ox=1000.0):
    """Default setup places the obstacle far away so the q_d/d^2 term is
    effectively constant and dV/dt reflects only the velocity error term.
    """
    dyn = BicycleModel()
    manifold = Manifold(obstacles=[CircleObstacle(ox, 0, 2.0)])
    fn = QuadraticLyapunov()
    mon = StabilityMonitor(fn=fn, dynamics=dyn, manifold=manifold,
                           target_speed=10.0)
    state = State(px=0, py=0, psi=0, v=v, a=0.0, mu=1.0)
    return dyn, manifold, mon, state


def test_V_monotonic_with_velocity_error():
    """V should grow as the velocity error grows (pure stability term)."""
    dyn = BicycleModel()
    manifold = Manifold(obstacles=[CircleObstacle(30, 0, 2.0)])
    fn = QuadraticLyapunov()
    mon = StabilityMonitor(fn=fn, dynamics=dyn, manifold=manifold,
                           target_speed=10.0)
    at_target = State(px=0, py=0, psi=0, v=10, a=0, mu=1.0)
    off_target = State(px=0, py=0, psi=0, v=5, a=0, mu=1.0)
    v0 = mon.fn.V_full(at_target, manifold, mon.target_speed)
    v1 = mon.fn.V_full(off_target, manifold, mon.target_speed)
    assert v1 > v0


def test_stable_cruising_has_nonpositive_dV():
    _, _, mon, s = _setup(v=10.0)
    u = Control(steer=0.0, jerk=0.0)
    stable, dv = mon.check(s, u)
    assert stable
    assert dv <= 1e-6


def test_accel_raises_V_when_already_at_target_speed():
    _, _, mon, s = _setup(v=10.0)  # target is 10 too
    u = Control(steer=0.0, jerk=6.0)  # adds velocity error quickly
    _, dv = mon.check(s, u, dt=0.1)
    assert dv > 0
