"""Predictive-brake nominal policy (AI-02).

``PredictiveBrakePolicy`` wraps the baseline ``GradientPolicy`` with a
short look-ahead over the same barriers used by the CBF filter. If the
nominal command would drive the predicted trajectory too close to a
barrier, the policy throttles jerk before the hard gates need to fall
back to emergency braking.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional

from ..cbf import BarrierFunction
from ..dynamics import BicycleModel
from ..graph import InteractionIntentGraph
from ..types import Control, State


@dataclass
class PredictiveBrakePolicy:
    """Wrap a nominal policy with a CBF-aware pre-brake guard.

    This is still a *nominal* policy: it never executes commands
    directly, and it does not weaken CBF / T_inv. It simply tries to
    offer the safety layer a candidate action that is less likely to
    require fallback.
    """

    inner: Callable[[State, Optional[InteractionIntentGraph]], Control]
    barriers: List[BarrierFunction]
    dynamics: BicycleModel
    t_lookahead: float = 0.8
    rollout_dt: float = 0.1
    risk_margin: float = 0.5
    brake_jerk: float = -3.0

    def __call__(self,
                 state: State,
                 graph: Optional[InteractionIntentGraph] = None) -> Control:
        u = self.inner(state, graph)
        if not self.barriers:
            return u

        steps = max(1, int(round(self.t_lookahead / self.rollout_dt)))
        controls = [u] * steps
        trajectory = self.dynamics.rollout(state, controls, dt=self.rollout_dt)

        at_risk = any(
            barrier.h(predicted) < self.risk_margin
            for predicted in trajectory[1:]
            for barrier in self.barriers
        )
        if not at_risk:
            return u
        return Control(steer=u.steer, jerk=min(u.jerk, self.brake_jerk))
