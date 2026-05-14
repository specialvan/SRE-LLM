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

from .events import make_event


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
        was_triggered_before = self._monitor.triggered
        verdict: StabilityVerdict = self._monitor.step(x, t)

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
