"""End-to-end structural planner — §4 "给 AI 戴上物理的枷锁".

Wires together:

    perception graph → nominal policy → CBF filter → T_inv → Lyapunov check

Every command produced by :meth:`StructuralPlanner.step` is guaranteed
to respect the Lyapunov hard constraint (or degrade to emergency brake).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

import numpy as np

from .cbf import CBFQPFilter, make_obstacle_barriers
from .dynamics import BicycleModel, Manifold
from .game import BeliefState, WorstCaseGame
from .graph import InteractionIntentGraph, Node
from .invariant import ControlInvariantOperator
from .lyapunov import QuadraticLyapunov, StabilityMonitor
from .potential import PotentialField
from .trace import build_trace_record
from .types import DEFAULT_VEHICLE, Control, State, VehicleParams


# ---------------------------------------------------------------------------
# Default nominal policy: gradient-descent on Φ mapped to (steer, jerk)
# ---------------------------------------------------------------------------

class GradientPolicy:
    """Cheap nominal policy that descends the potential field.

    Acts as a stand-in for a "pretrained NN policy" in demos. It maps the
    desired (px, py) flow direction into a (steer, jerk) command.
    """

    def __init__(self, field: PotentialField,
                 manifold: Manifold,
                 target_speed: float = 15.0,
                 params: VehicleParams = DEFAULT_VEHICLE) -> None:
        self.field = field
        self.manifold = manifold
        self.target_speed = target_speed
        self.params = params

    def __call__(self, state: State,
                 graph: Optional[InteractionIntentGraph] = None) -> Control:
        dir_xy = self.field.flow_direction(state, self.manifold, graph)
        # desired heading
        if np.linalg.norm(dir_xy) < 1e-6:
            desired_psi = state.psi
        else:
            desired_psi = float(np.arctan2(dir_xy[1], dir_xy[0]))
        # wrap to (-pi, pi]
        err = _wrap(desired_psi - state.psi)
        steer = float(np.clip(2.0 * err, -self.params.max_steer,
                              self.params.max_steer))

        # speed controller — P on velocity, jerk-shaped
        v_err = self.target_speed - state.v
        desired_a = float(np.clip(1.5 * v_err, -4.0, 3.0))
        jerk = float(np.clip(2.0 * (desired_a - state.a),
                             -self.params.jerk_max, self.params.jerk_max))
        return Control(steer=steer, jerk=jerk)


def _wrap(x: float) -> float:
    return float((x + np.pi) % (2 * np.pi) - np.pi)


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------

@dataclass
class StructuralPlanner:
    """End-to-end decision planner with Lyapunov hard constraint."""
    dynamics: BicycleModel
    manifold: Manifold
    target_speed: float = 15.0
    params: VehicleParams = DEFAULT_VEHICLE
    potential: PotentialField = field(default_factory=PotentialField)
    lyap: QuadraticLyapunov = field(default_factory=QuadraticLyapunov)
    game: WorstCaseGame = field(default_factory=WorstCaseGame)
    cbf_alpha: float = 3.0
    gamma: float = 0.5
    ego_id: str = "ego"

    # computed lazily in __post_init__
    nominal: Optional[Callable[[State, InteractionIntentGraph], Control]] = None

    def __post_init__(self) -> None:
        if self.nominal is None:
            self.nominal = GradientPolicy(
                self.potential, self.manifold, self.target_speed, self.params
            )
        barriers = make_obstacle_barriers(self.manifold,
                                          margin=self.game.base_buffer)
        self.cbf = CBFQPFilter(barriers=barriers, dynamics=self.dynamics,
                               params=self.params, alpha=self.cbf_alpha)
        self.stability = StabilityMonitor(
            fn=self.lyap, dynamics=self.dynamics, manifold=self.manifold,
            target_speed=self.target_speed,
        )
        self.t_inv = ControlInvariantOperator(
            cbf=self.cbf, stability=self.stability, params=self.params,
            gamma=self.gamma,
        )
        if isinstance(self.nominal, GradientPolicy):
            from .policies import PredictiveBrakePolicy
            self.nominal = PredictiveBrakePolicy(
                inner=self.nominal,
                barriers=self.cbf.barriers,
                dynamics=self.dynamics,
            )

    # ------------------------------------------------------------------
    def step(self, state: State, graph: InteractionIntentGraph,
             dt: float = 0.1,
             step_index: Optional[int] = None) -> Tuple[State, Control, dict]:
        """Advance the ego vehicle by one control cycle."""
        assert self.nominal is not None
        u_nn = self.nominal(state, graph)
        u_safe, info = self.t_inv.apply(state, u_nn)
        next_state = self.dynamics.step(state, u_safe, dt)

        trace = build_trace_record(
            step_index=step_index,
            dt=dt,
            state=state,
            next_state=next_state,
            u_nn=u_nn,
            u_safe=u_safe,
            info=info,
            min_dist=self.manifold.min_distance(state),
        )
        return next_state, u_safe, trace

    # ------------------------------------------------------------------
    def run(self, initial: State, graph: InteractionIntentGraph,
            horizon_steps: int = 80, dt: float = 0.1,
            trace_path: Optional[str] = None
            ) -> Tuple[List[State], List[Control], List[dict]]:
        states: List[State] = [initial]
        controls: List[Control] = []
        traces: List[dict] = []
        cur = initial
        for k in range(horizon_steps):
            cur, u, tr = self.step(cur, graph, dt, step_index=k)
            states.append(cur)
            controls.append(u)
            traces.append(tr)
            if trace_path:
                with open(trace_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(tr, ensure_ascii=False,
                                       allow_nan=False) + "\n")
        return states, controls, traces
