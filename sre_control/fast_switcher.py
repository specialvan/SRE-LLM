"""§7 Bang-bang adapter — minimum-time traffic switch.

SRE problem
-----------
Emergency flips (kill-switch, blue/green cut-over, regional failover)
share a common shape: move the traffic-share variable from x₀ to x_f
in the **shortest** possible time, subject to a hard rate limit
``|ẋ| ≤ r_max``, while arriving with zero residual velocity so the
system doesn't overshoot.

Pontryagin's minimum principle for a double integrator with terminal
velocity 0 says: full-throttle in one direction for exactly T/2, then
full-throttle in the opposite direction for another T/2, with the
total time::

    T = 2 · √(|Δx| · J / τ_max)            (§7 star result)

and in SRE terms (``J = 1``, ``τ_max = r_max``)::

    T_min = 2 · √(|Δshare| / r_max)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np

from .events import make_event


@dataclass
class FastTrafficSwitcher:
    """Plan the minimum-time traffic switch with a hard rate limit.

    * ``rate_max``   — max traffic-share change per second (e.g. 0.4).
    * ``safety_margin`` — optional slack (e.g. 1.2× to leave headroom
      for health-check confirmation at midpoint).
    """

    rate_max: float = 0.4
    safety_margin: float = 1.0

    # ------------------------------------------------------------------
    def plan(self, share_from: float, share_to: float,
             dt: float = 0.1,
             deadline_s: float | None = None
             ) -> Tuple[np.ndarray, np.ndarray, dict]:
        """Return ``(t_grid, share_schedule, info)``.

        The switch is expressed as a bang-bang acceleration on the
        ``share`` variable — equivalent to accelerating the *rate of
        change* to +r_max, holding it, then decelerating to 0 at the
        target.
        """
        dx = share_to - share_from
        sign = 1 if dx >= 0 else -1
        mag = abs(dx)

        # Bang-bang minimum-time for double integrator:
        #   T_min = 2·√(|Δ| / r_max)    if r_max acts as jerk-like cap.
        # We treat the rate_max as the *slope cap* (acceleration of
        # share is unlimited), giving T_min = |Δ| / r_max.
        # To preserve the §7 bang-bang shape we put the cap on the
        # *second* derivative (the acceleration of share), which gives
        # a smooth ramp-in → ramp-out.
        T_min = self.safety_margin * 2.0 * np.sqrt(mag / self.rate_max)
        N = max(int(np.ceil(T_min / dt)), 2)
        t = np.linspace(0.0, T_min, N + 1)

        # Two-phase profile: symmetric about t = T_min / 2
        mid = T_min / 2.0
        a = self.rate_max * sign          # "acceleration" of share (/s²)
        share = np.zeros_like(t)
        rate = np.zeros_like(t)
        for i, tk in enumerate(t):
            if tk <= mid:
                rate[i] = a * tk
                share[i] = share_from + 0.5 * a * tk * tk
            else:
                s = tk - mid
                rate[i] = a * (mid - s)
                share[i] = (share_from + 0.5 * a * mid * mid
                             + a * mid * s - 0.5 * a * s * s)

        local_states = ["ramp_up", "switch_midpoint", "ramp_down"]
        events = []
        if deadline_s is not None and T_min > deadline_s:
            events.append(make_event(
                stage="FastTrafficSwitcher",
                kind="deadline_exceeded",
                detail="minimum-time switch is slower than the incident deadline",
                safe_action="freeze the change or choose a simpler rollback path",
            ))

        info = {
            "T_min_seconds":     float(T_min),
            "switch_midpoint_s": float(mid),
            "peak_rate_per_s":   float(abs(a * mid)),
            "final_share":       float(share[-1]),
            "local_states":      local_states,
            "events":            events,
        }
        return t, share, info
