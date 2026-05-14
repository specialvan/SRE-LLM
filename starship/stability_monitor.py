"""§2.1 Lyapunov stability monitor — physical red line.

The article's §2.1 states that any closed-loop controller must keep a
scalar Lyapunov candidate ``V(x)`` non-increasing along trajectories::

    dV(x)/dt ≤ 0       (equilibrium condition)

In practice we evaluate ``V(x_k)`` at each tick and approximate the
derivative by a finite difference over a sliding window.  When the
moving estimate ``dV/dt`` is positive for more than ``k_violations``
consecutive ticks we declare a stability violation. For this pass the
monitor uses **manual-reset latch semantics**: once ``triggered`` flips
to ``True`` it stays true until :meth:`reset` is called. The SRE side
maps that latched red line to ``stability_violation``.

This module is intentionally **generic**:

- It does not know about booster physics.
- ``V_fn`` is an arbitrary callable ``np.ndarray -> float``.
- The default window / threshold can be tuned per-scenario.

That means the same class can monitor:

- booster kinetic+potential energy (physics)
- service-error rate moving average (SRE)
- RL-policy value function along a trajectory (ML)
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Deque, Dict, Optional

import numpy as np


@dataclass
class StabilityVerdict:
    """One-tick assessment returned by :meth:`StabilityMonitor.step`."""

    V: float                    # current Lyapunov value
    dV_dt: Optional[float]      # ``None`` on the very first tick
    violating: bool             # True when dV/dt > tolerance
    consecutive_violations: int
    triggered: bool             # True once consecutive_violations ≥ k
    reason: str = ""


@dataclass
class StabilityMonitor:
    """Sliding-window monitor of ``dV/dt ≤ 0``.

    Parameters
    ----------
    V_fn
        Callable mapping the current state ``x ∈ R^n`` to a scalar
        Lyapunov value.  The callable must be deterministic; the
        monitor does not cache across runs.
    tolerance
        How far above zero ``dV/dt`` may rise before a single tick is
        classified as ``violating``.  A small positive value absorbs
        numerical noise in the finite-difference derivative.
    k_violations
        Number of consecutive violating ticks required to flip
        ``triggered`` from False to True.  The default ``3`` is enough
        to reject single-tick transients while still catching a
        genuine positive-feedback loop within a few seconds at 20 Hz.
        Once ``triggered`` becomes True it remains latched until
        :meth:`reset` is called.
    window
        Number of recent ``V`` samples to retain; used for smoothed
        backward-difference computation.  A window of 2 degenerates to
        a plain ``ΔV/Δt``.
    """

    V_fn: Callable[[np.ndarray], float]
    tolerance: float = 1e-6
    k_violations: int = 3
    window: int = 4

    _history: Deque[float] = field(default_factory=deque, init=False,
                                   repr=False)
    _t_history: Deque[float] = field(default_factory=deque, init=False,
                                     repr=False)
    _consecutive: int = field(default=0, init=False)
    _triggered: bool = field(default=False, init=False)

    # ------------------------------------------------------------------
    def reset(self) -> None:
        self._history.clear()
        self._t_history.clear()
        self._consecutive = 0
        self._triggered = False

    # ------------------------------------------------------------------
    def step(self, x: np.ndarray, t: float) -> StabilityVerdict:
        """Feed one state sample ``x`` at time ``t`` (seconds).

        ``triggered`` is latched: a later non-violating sample clears
        ``consecutive_violations`` but does not clear the trigger bit.
        Operators or higher-level tests must call :meth:`reset` when
        they want to acknowledge recovery.
        """
        V = float(self.V_fn(x))

        if self._history:
            # smoothed backward-difference: use oldest and newest point in
            # the current window to damp per-tick numerical noise.
            V_old = self._history[0]
            t_old = self._t_history[0]
            dt = max(t - t_old, 1e-9)
            dV_dt: Optional[float] = (V - V_old) / dt
        else:
            dV_dt = None

        self._history.append(V)
        self._t_history.append(t)
        while len(self._history) > self.window:
            self._history.popleft()
            self._t_history.popleft()

        violating = dV_dt is not None and dV_dt > self.tolerance
        if violating:
            self._consecutive += 1
        else:
            self._consecutive = 0

        just_triggered = (not self._triggered
                           and self._consecutive >= self.k_violations)
        if just_triggered:
            self._triggered = True

        reason = ""
        if violating:
            reason = (f"dV/dt={dV_dt:.3e} > tol={self.tolerance:.1e} "
                      f"for {self._consecutive} consecutive ticks")

        return StabilityVerdict(
            V=V,
            dV_dt=dV_dt,
            violating=violating,
            consecutive_violations=self._consecutive,
            triggered=self._triggered,
            reason=reason,
        )

    # ------------------------------------------------------------------
    @property
    def triggered(self) -> bool:
        return self._triggered

    @property
    def consecutive_violations(self) -> int:
        return self._consecutive

    def summary(self) -> Dict[str, float]:
        """Compact summary suitable for JSONL trace rows."""
        return {
            "triggered": self._triggered,
            "consecutive_violations": self._consecutive,
            "window_len": len(self._history),
            "tolerance": self.tolerance,
        }


# ---------------------------------------------------------------------------
# Convenience V_fn builders for common starship scenarios
# ---------------------------------------------------------------------------

def kinetic_plus_potential_V(mass: float = 1.0,
                              gravity: float = 9.80665):
    """Standard mechanical energy ``V = ½ m ‖v‖² + m g h``.

    Expects state layout ``x = [px, py, pz, vx, vy, vz, ...]``; only
    the first 6 entries are inspected so the builder works for both
    the 3-DoF toy dynamics and the 13-D ``State6DOF`` layout.
    """
    def _V(x: np.ndarray) -> float:
        v = np.asarray(x[3:6], dtype=float)
        h = float(x[2])
        return 0.5 * mass * float(v @ v) + mass * gravity * h
    return _V


def quadratic_V(Q: np.ndarray, x_ref: Optional[np.ndarray] = None):
    """``V = (x − x_ref)ᵀ Q (x − x_ref)`` for positive-definite Q.

    The default reference is the zero vector.  Useful for SRE-side use
    cases (oscillation detection on latency / error-rate deltas).
    """
    Q = np.asarray(Q, dtype=float)

    def _V(x: np.ndarray) -> float:
        d = np.asarray(x, dtype=float)
        if x_ref is not None:
            d = d - np.asarray(x_ref, dtype=float)
        return float(d @ Q @ d)
    return _V
