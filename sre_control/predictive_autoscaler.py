"""§6 MPC adapter — predictive autoscaler.

SRE problem
-----------
Standard HPA is reactive: when CPU > 80% it scales. That's one-step
LQR without the L. An MPC-based autoscaler instead:

  1. Predicts the next N minutes of traffic using an AR model.
  2. Minimises ``Σ (SLO violation)² + λ · Σ (cost)²`` over the horizon.
  3. Only applies the first action (``replicas_next``), then re-plans.

The booster MPC works on a double integrator; here we work on a
scalar plant ``replicas_{k+1} = replicas_k + u_k`` with a nonlinear
capacity mapping ``capacity = replicas · per_replica_rps``.

We keep the plant linear (double integrator with ``replicas`` and
``rps_served``) to stay inside the QuadraticMPC envelope — and push
the nonlinearities into the cost through a shaping weight that grows
as the replicas approach their hard cap.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from numbers import Integral
import numpy as np

from starship.mpc import LinearDiscretizer, QuadraticMPC
from .events import make_event
from .exceptions import AdapterInputError


@dataclass
class PredictiveAutoscaler:
    """Linear MPC over (replicas, rps_served).

    Control variable ``u`` = number of replicas to add or remove per
    control step (we discretise to whole replicas externally). The
    plant model is ``replicas_{k+1} = replicas_k + u``, and RPS served
    tracks replicas × per_replica_rps up to a forecasted demand.
    """

    horizon: int = 12                  # steps (e.g. 12 × 5 s = 1 min)
    dt: float = 5.0                    # seconds per step
    per_replica_rps: float = 100.0
    replicas_min: int = 2
    replicas_max: int = 100
    max_step: int = 5                  # |u| ≤ max_step per control step
    q_slo: float = 50.0                # weight on SLO violation
    r_cost: float = 1.0                # weight on extra replicas
    q_terminal: float = 100.0

    _mpc: QuadraticMPC = field(init=False, repr=False)
    last_trace: dict = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        A = np.array([[0.0, 0.0], [0.0, 0.0]])   # zero-order plant
        B = np.array([[1.0 / self.dt], [self.per_replica_rps / self.dt]])
        Ad, Bd = LinearDiscretizer(A, B).zoh(self.dt)

        Q = np.diag([self.r_cost, self.q_slo])   # penalise replicas & SLO
        R = np.array([[0.2]])
        P = np.diag([self.r_cost, self.q_terminal])
        self._mpc = QuadraticMPC(
            A=Ad, B=Bd, Q=Q, R=R, P=P,
            N=self.horizon,
            u_min=np.array([-float(self.max_step)]),
            u_max=np.array([+float(self.max_step)]),
        )

    # ------------------------------------------------------------------
    def step(self, current_replicas: int, observed_rps: float,
             forecast_rps: float) -> int:
        """Compute the next replica count.

        ``forecast_rps`` is the expected arrival rate after ``dt`` s.
        The MPC returns a ``u`` ∈ [-max_step, +max_step] we round to
        the nearest integer and bound to [min, max].
        """
        if (
            isinstance(current_replicas, bool)
            or not isinstance(current_replicas, Integral)
            or int(current_replicas) < 0
        ):
            raise AdapterInputError(
                'current_replicas must be a non-negative integer'
            )
        current_replicas = int(current_replicas)
        if isinstance(observed_rps, bool):
            raise AdapterInputError('observed_rps must be non-negative and finite')
        observed_rps = float(observed_rps)
        if not np.isfinite(observed_rps) or observed_rps < 0.0:
            raise AdapterInputError('observed_rps must be non-negative and finite')
        if isinstance(forecast_rps, bool):
            raise AdapterInputError('forecast_rps must be non-negative and finite')
        forecast_rps = float(forecast_rps)
        if not np.isfinite(forecast_rps) or forecast_rps < 0.0:
            raise AdapterInputError('forecast_rps must be non-negative and finite')

        # Shift the reference into the error frame: we want the plant's
        # rps_served to match the forecast.
        target_replicas = forecast_rps / self.per_replica_rps
        err_state = np.array([
            current_replicas - target_replicas,
            observed_rps - forecast_rps,
        ])
        u = float(self._mpc.step(err_state)[0])
        raw_next = int(round(current_replicas + u))
        next_replicas = int(np.clip(
            raw_next, self.replicas_min, self.replicas_max))
        local_states = ["solve"]
        if raw_next != next_replicas:
            local_states.append("clip")
        local_states.append("integerize")

        events = []
        if next_replicas in (self.replicas_min, self.replicas_max):
            events.append(make_event(
                stage="PredictiveAutoscaler",
                kind="replica_bound_active",
                detail="next replica count is at a hard bound",
                safe_action="return bounded integer replicas",
                next_replicas=next_replicas,
                replicas_min=self.replicas_min,
                replicas_max=self.replicas_max,
            ))
        self.last_trace = {
            "target_replicas": float(target_replicas),
            "raw_control": float(u),
            "raw_next_replicas": int(raw_next),
            "next_replicas": int(next_replicas),
            "local_states": local_states,
            "events": events,
        }
        return next_replicas
