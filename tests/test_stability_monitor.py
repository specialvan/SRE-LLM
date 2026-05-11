"""Unit tests for §2.1 StabilityMonitor."""

from __future__ import annotations

import numpy as np

from starship.stability_monitor import (StabilityMonitor,
                                         kinetic_plus_potential_V,
                                         quadratic_V)


# ---------------------------------------------------------------------------
# Basic behaviour
# ---------------------------------------------------------------------------

def test_first_tick_produces_no_derivative():
    mon = StabilityMonitor(V_fn=lambda x: float(x[0]))
    v = mon.step(np.array([1.0]), t=0.0)
    assert v.V == 1.0
    assert v.dV_dt is None
    assert v.violating is False
    assert v.triggered is False


def test_monotone_decreasing_never_triggers():
    """V = 10 − t descends monotonically → never violating."""
    mon = StabilityMonitor(V_fn=lambda x: float(x[0]))
    for t in np.linspace(0, 5, 25):
        v = mon.step(np.array([10.0 - t]), t=t)
        assert v.triggered is False


def test_monotone_increasing_triggers_after_k_ticks():
    """V = t rises monotonically → triggered once consecutive ≥ k."""
    mon = StabilityMonitor(V_fn=lambda x: float(x[0]), k_violations=3)
    sawtriggered = False
    for i, t in enumerate(np.linspace(0, 3, 10)):
        v = mon.step(np.array([t]), t=t)
        if i >= 3 and v.triggered:
            sawtriggered = True
    assert sawtriggered is True


def test_single_blip_does_not_trigger():
    """One violating tick inside a descending sequence → no trigger."""
    mon = StabilityMonitor(V_fn=lambda x: float(x[0]), k_violations=3)
    series = [10.0, 9.0, 8.0, 8.5, 7.0, 6.0, 5.0]  # one blip at i=3
    for i, v in enumerate(series):
        verdict = mon.step(np.array([v]), t=float(i))
    assert mon.triggered is False


def test_reset_clears_state():
    mon = StabilityMonitor(V_fn=lambda x: float(x[0]), k_violations=2)
    for i in range(5):
        mon.step(np.array([float(i)]), t=float(i))
    assert mon.triggered is True
    mon.reset()
    assert mon.triggered is False
    assert mon.consecutive_violations == 0


# ---------------------------------------------------------------------------
# Convenience V_fn helpers
# ---------------------------------------------------------------------------

def test_kinetic_plus_potential_V_for_falling_object():
    """Free fall with zero drag conserves energy → dV/dt ≈ 0."""
    V_fn = kinetic_plus_potential_V(mass=1.0, gravity=9.80665)
    mon = StabilityMonitor(V_fn=V_fn, tolerance=1e-3, k_violations=100)
    # x = [px, py, h, vx, vy, v_h]; start at h=100 m with vh=0
    v, h = 0.0, 100.0
    for i in range(20):
        dt = 0.05
        # gravity integration (semi-implicit Euler, energy-preserving)
        v_next = v - 9.80665 * dt
        h_next = h + 0.5 * (v + v_next) * dt
        v, h = v_next, h_next
        state = np.array([0.0, 0.0, h, 0.0, 0.0, v])
        verdict = mon.step(state, t=i * dt)
    # In exact mechanics E is conserved; in numerical integration
    # |dV/dt| should stay small (≪ 1 J/s) and monitor must not trigger.
    assert mon.triggered is False


def test_quadratic_V_reference_frame():
    """V = ‖x − x*‖² drops to 0 as x → x*."""
    V_fn = quadratic_V(Q=np.eye(2), x_ref=np.array([5.0, 5.0]))
    mon = StabilityMonitor(V_fn=V_fn)
    for i in range(10):
        x = np.array([i * 0.5, i * 0.5])     # walk toward [5,5]
        mon.step(x, t=i * 1.0)
    assert mon.triggered is False
