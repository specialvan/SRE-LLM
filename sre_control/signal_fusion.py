"""§5 EKF adapter — fusing multiple SRE signals into one state.

SRE problem
-----------
Prometheus aggregates, distributed traces and frontend RUM all
observe the same underlying service state but at wildly different
frequencies and noise levels. Today most teams pick one channel as
"truth" and use the others as context. That loses information.

Turning the booster EKF into an SRE signal-fusion layer requires
only one reframing:

    continuous state  x = [qps, latency_ms, cpu_util]
    observation h_i(x) — per sensor, with Jacobian H_i and noise R_i
    process model   f(x) — even a zero-model (RW) helps, provided it's
                           paired with an honest Q.

The same EKF/predict/update equations then fold all streams into a
single estimate with a posterior covariance you can actually alarm on
(unlike rolling averages).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence, Tuple

import numpy as np

from starship.ekf import EKF
from .events import make_event


@dataclass
class Signal:
    """One sensor channel.

    h   — measurement function: R^n → R^m
    H   — Jacobian R^n → R^{m×n}  (None ⇒ numerical)
    R   — measurement noise covariance (m × m)
    name — human label for the audit trail
    """
    name: str
    h: Callable[[np.ndarray], np.ndarray]
    H: Callable[[np.ndarray], np.ndarray]
    R: np.ndarray


@dataclass
class SignalFusion:
    """Multi-source EKF for the service state.

    The default state is ``x = [qps, latency_ms, cpu_util]`` and the
    default process model is an Ornstein-Uhlenbeck pull toward an
    operator-supplied target ``x_ref``. Swap in anything else if you
    already have a physical model of how your service drifts.
    """

    x0: np.ndarray
    P0: np.ndarray
    Q: np.ndarray
    x_ref: np.ndarray                           # pull target
    theta: float = 0.2                          # OU reversion rate
    _ekf: EKF = field(init=False, repr=False)

    def __post_init__(self) -> None:
        def _f(x: np.ndarray, u: np.ndarray, dt: float) -> np.ndarray:
            return x + self.theta * (self.x_ref - x) * dt

        def _F(x: np.ndarray, u: np.ndarray, dt: float) -> np.ndarray:
            n = x.size
            return np.eye(n) * (1.0 - self.theta * dt)

        self._ekf = EKF(
            x=np.array(self.x0, dtype=float),
            P=np.array(self.P0, dtype=float),
            process_noise=np.array(self.Q, dtype=float),
            f=_f, F_jac=_F,
        )

    # ------------------------------------------------------------------
    def step(self, dt: float,
             readings: Sequence[Tuple[Signal, Optional[np.ndarray]]]
             ) -> dict:
        """Advance one step and fold in every available reading.

        Signals with a ``None`` reading are skipped (sensor missing
        that tick). Returns a trace dict suitable for JSONL logging.
        """
        self._ekf.predict(None, dt)
        fused_trace = []
        events = []
        local_states = ["predict"]
        for signal, z in readings:
            if z is None:
                fused_trace.append({"signal": signal.name, "used": False})
                if "skip_update" not in local_states:
                    local_states.append("skip_update")
                events.append(make_event(
                    stage="SignalFusion",
                    kind="missing_sensor",
                    detail=f"{signal.name} reading was absent in this tick",
                    safe_action="skip update and keep posterior prediction",
                ))
                continue
            z = np.asarray(z, dtype=float)
            self._ekf.update(z, signal.h, signal.H, signal.R)
            if "update" not in local_states:
                local_states.append("update")
            fused_trace.append({
                "signal": signal.name, "used": True,
                "residual": float(np.linalg.norm(z - signal.h(self._ekf.x))),
            })

        return {
            "x": self._ekf.x.copy().tolist(),
            "P_trace": float(np.trace(self._ekf.P)),
            "signals": fused_trace,
            "local_states": local_states,
            "events": events,
        }

    # ------------------------------------------------------------------
    @property
    def state(self) -> np.ndarray:
        return self._ekf.x.copy()

    @property
    def covariance(self) -> np.ndarray:
        return self._ekf.P.copy()
