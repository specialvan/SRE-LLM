"""§2.1 Lyapunov adapter — service-level self-oscillation guard.

SRE problem
-----------
The starship §2.1 red line is ``dV/dt ≤ 0``.  The SRE-side equivalent is
"my moving-average SLI should not drift monotonically upward for N
consecutive ticks" — the classical sign of a self-oscillating control
loop (PID gain too high, warmup stampede, thrashing cache, etc.).

This wrapper reuses the physics-layer :class:`StabilityMonitor` but
speaks SRE vocabulary: instead of raising on trigger it emits a
`stability_violation` runtime event so the upstream
:class:`SREControlStack` can propagate it into ``runtime.events`` via
the normal event schema. The underlying monitor is a **manual-reset
latch** in this pass: once triggered, it stays triggered until
``reset()`` is called.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np

from starship.stability_monitor import StabilityMonitor, StabilityVerdict

from .exceptions import AdapterInputError
from .events import make_event


def sre_error_budget_V(
    *,
    latency_target_ms: float,
    latency_scale_ms: float,
    error_rate_target: float,
    error_rate_scale: float,
) -> Callable[[np.ndarray], float]:
    """Build an SRE Lyapunov candidate for service health drift.

    The expected state layout is ``[qps, latency_ms, error_rate, ...]``.
    QPS is intentionally ignored: this guard is about whether SLO burn is
    moving in the wrong direction, not whether traffic is high. Latency and
    error-rate excess are normalized by operator-provided scales, clipped at
    zero so under-budget headroom does not create energy, and squared:

    ``V = max(0, latency-target)^2/scale^2 + max(0, err-target)^2/scale^2``.
    """
    latency_target_ms = float(latency_target_ms)
    if not np.isfinite(latency_target_ms):
        raise ValueError('latency_target_ms must be finite')
    latency_scale_ms = float(latency_scale_ms)
    if not np.isfinite(latency_scale_ms) or latency_scale_ms <= 0:
        raise ValueError("latency_scale_ms must be positive")
    error_rate_target = float(error_rate_target)
    if not np.isfinite(error_rate_target):
        raise ValueError("error_rate_target must be finite")
    error_rate_scale = float(error_rate_scale)
    if not np.isfinite(error_rate_scale) or error_rate_scale <= 0:
        raise ValueError("error_rate_scale must be positive")

    def _V(x: np.ndarray) -> float:
        state = np.asarray(x, dtype=float)
        latency_excess = max(0.0, state[1] - latency_target_ms)
        error_excess = max(0.0, state[2] - error_rate_target)
        latency_term = (latency_excess / latency_scale_ms) ** 2
        error_term = (error_excess / error_rate_scale) ** 2
        return float(latency_term + error_term)

    return _V


@dataclass
class StabilityGuard:
    """Wrap :class:`StabilityMonitor` in SRE-schema language.

    Parameters
    ----------
    V_fn
        Scalar Lyapunov candidate on the fused state.  A common choice
        is ``lambda x: (error_rate − target)^2`` — it's always ≥ 0, ``0``
        at equilibrium, and rises monotonically when the service drifts.
    tolerance, k_violations, window
        Passed straight through to the underlying monitor.
    label
        Human label for the event ``stage`` field (default ``"service"``).
    """

    V_fn: Callable[[np.ndarray], float]
    tolerance: float = 1e-6
    k_violations: int = 3
    window: int = 4
    label: str = "service"

    _monitor: StabilityMonitor = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.tolerance = float(self.tolerance)
        if not np.isfinite(self.tolerance) or self.tolerance < 0.0:
            raise ValueError('tolerance must be non-negative and finite')
        k_violations = float(self.k_violations)
        if not np.isfinite(k_violations) or not k_violations.is_integer():
            raise ValueError('k_violations must be a positive integer')
        self.k_violations = int(k_violations)
        if self.k_violations <= 0:
            raise ValueError('k_violations must be positive')
        window = float(self.window)
        if not np.isfinite(window) or not window.is_integer():
            raise ValueError('window must be a positive integer')
        self.window = int(window)
        if self.window <= 0:
            raise ValueError('window must be positive')
        if not isinstance(self.label, str) or not self.label.strip():
            raise ValueError('label must be a non-empty string')
        self.label = self.label.strip()
        self._monitor = StabilityMonitor(
            V_fn=self.V_fn,
            tolerance=self.tolerance,
            k_violations=self.k_violations,
            window=self.window,
        )

    # ------------------------------------------------------------------
    def reset(self) -> None:
        self._monitor.reset()

    # ------------------------------------------------------------------
    def step(self, x: np.ndarray, t: float) -> dict:
        """Feed one state sample and return a trace dict.

        When the monitor has just flipped from healthy to triggered
        (this tick specifically), emit a ``stability_violation`` event
        with a detail string that differentiates it from adapter
        exceptions. On later ticks the guard reports ``triggered=True``
        and a local ``sustained`` state, but it does not emit duplicate
        events until an explicit :meth:`reset`.
        """
        state = np.asarray(x, dtype=float)
        if not np.isfinite(state).all():
            raise AdapterInputError('non-finite stability state')
        t = float(t)
        if not np.isfinite(t):
            raise AdapterInputError('stability time must be finite')
        was_triggered_before = self._monitor.triggered
        verdict: StabilityVerdict = self._monitor.step(state, t)

        events = []
        local_states = ["observe_V"]
        if verdict.triggered and not was_triggered_before:
            local_states.append("trigger")
            events.append(make_event(
                stage=f"StabilityGuard/{self.label}",
                kind="stability_violation",
                detail=(f"V monitor ({self.label}) triggered after "
                        f"{verdict.consecutive_violations} consecutive ticks "
                        f"with dV/dt > {self.tolerance:.1e}"),
                safe_action=(
                    "surface as DEGRADED signal; downstream controllers "
                    "should stay in conservative mode until an operator "
                    "or test explicitly resets the latched monitor"),
                label=self.label,
                V=verdict.V,
                dV_dt=verdict.dV_dt,
                consecutive_violations=verdict.consecutive_violations,
                tolerance=self.tolerance,
            ))
        elif verdict.triggered:
            local_states.append("sustained")
        elif verdict.violating:
            local_states.append("warning")

        return {
            "V": verdict.V,
            "dV_dt": verdict.dV_dt,
            "violating": verdict.violating,
            "triggered": verdict.triggered,
            "consecutive": verdict.consecutive_violations,
            "local_states": local_states,
            "events": events,
        }

    # ------------------------------------------------------------------
    @property
    def triggered(self) -> bool:
        return self._monitor.triggered
