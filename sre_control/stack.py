"""End-to-end SRE control stack — composes all 8 adapters.

The control loop (20 Hz or any chosen rate) mirrors the Starship
recovery pipeline::

    OBSERVE (fuse)  §5 SignalFusion
        ↓
    PLAN            §6 PredictiveAutoscaler  +  §2 CanaryScheduler
        ↓
    GUARD           §4 SLOGuardrail
        ↓
    ALLOCATE        §8 WeightedLoadBalancer
        ↓
    EXECUTE
        ↓
    (optional) §7 FastTrafficSwitcher — emergency flip
    (static)   §1 PoolCapacityPlanner — connection-pool budget
    (static)   §3 TopologyState        — topology manifold

Each adapter is small enough to be tested in isolation; ``stack.py``
simply wires them together so a team can see the end-to-end shape.

Robustness policy
-----------------
Every stage is wrapped in try/except.  If an adapter raises, the stack:

  1. emits a ``stability_violation`` runtime event naming the stage and
     exception text,
  2. appends the matching ``DEGRADED_*`` state,
  3. substitutes a safe fallback for the stage's output so downstream
     stages (especially guardrail + allocator) can keep running,
  4. records the full trace as usual.

The design goal is "any one adapter failing must not crash the tick".
See ``tests/test_contracts.py::test_sre_stack_survives_adapter_exception``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

from .canary_scheduler import CanaryScheduler, CanaryStep
from .events import make_event
from .pool_planner import PoolCapacityPlanner
from .predictive_autoscaler import PredictiveAutoscaler
from .signal_fusion import SignalFusion, Signal
from .slo_guardrail import SLOGuardrail
from .stability_guard import StabilityGuard
from .topology_state import TopologyState
from .fast_switcher import FastTrafficSwitcher
from .weighted_balancer import Instance, WeightedLoadBalancer


@dataclass
class SREControlStack:
    """Composes the 8 adapters into one ``step()`` that returns a trace.

    The concrete use-case is "run a service fleet with a canary, a
    predictive autoscaler, and a guardrail on every tick". Tests in
    ``tests/test_sre_control.py`` and ``tests/test_contracts.py``
    exercise the module contracts and the end-to-end trace shape.
    """

    fusion: SignalFusion
    autoscaler: PredictiveAutoscaler
    guardrail: SLOGuardrail
    balancer: WeightedLoadBalancer
    canary: Optional[CanaryScheduler] = None
    switcher: Optional[FastTrafficSwitcher] = None
    pool: Optional[PoolCapacityPlanner] = None
    topology: Optional[TopologyState] = None
    stability: Optional[StabilityGuard] = None

    trace: List[dict] = field(default_factory=list)
    _tick_index: int = field(default=0, init=False, repr=False)

    # ------------------------------------------------------------------
    @staticmethod
    def _stability_event(stage_label: str, exc: BaseException) -> dict:
        return make_event(
            stage=stage_label,
            kind="stability_violation",
            detail=f"{type(exc).__name__}: {exc}",
            safe_action=(
                "substitute the stage's safe fallback, continue the tick, "
                "and record DEGRADED_<stage>"),
        )

    # ------------------------------------------------------------------
    def step(self, dt: float,
             sensor_readings: list,
             forecast_rps: float,
             current_replicas: int,
             zone_target: np.ndarray,
             nn_proposal: np.ndarray,
             current_canary_share: Optional[float] = None,
             canary_observed_error: Optional[float] = None,
             ) -> dict:
        """Run one control tick and return a structured trace entry.

        Each stage is wrapped in try/except; if any stage raises, the
        tick still produces a trace and the stack surfaces a
        ``stability_violation`` event plus the appropriate DEGRADED_*
        state so the caller can decide whether to alert or retry.
        """
        runtime_states = ["OBSERVING"]
        runtime_events = []

        # ========================= 1) OBSERVE =========================
        try:
            fuse_trace = self.fusion.step(dt, sensor_readings)
            observed_rps = float(self.fusion.state[0])
            if any(not s.get("used", False) for s in fuse_trace["signals"]):
                runtime_states.append("DEGRADED_OBSERVE")
                runtime_events.extend(fuse_trace.get("events", []))
        except Exception as exc:  # noqa: BLE001 — robustness boundary
            fuse_trace = {"x": None, "P_trace": None, "signals": [],
                          "local_states": ["error"],
                          "events": [self._stability_event("SignalFusion", exc)]}
            observed_rps = float(forecast_rps)      # safe fallback
            runtime_states.append("DEGRADED_OBSERVE")
            runtime_events.extend(fuse_trace["events"])

        # ========================= 1b) STABILITY MONITOR (optional) ==
        # Runs between OBSERVE and PLAN.  A triggered monitor feeds a
        # `stability_violation` event + DEGRADED_PLAN so downstream
        # planners know to prefer conservative commands.
        stability_trace: Optional[dict] = None
        if self.stability is not None and self.fusion.state is not None:
            try:
                tick_time = self._tick_index * dt
                stability_trace = self.stability.step(
                    np.asarray(self.fusion.state, dtype=float),
                    t=float(tick_time))
                if stability_trace["events"]:
                    # Fresh trigger this tick
                    runtime_states.append("DEGRADED_PLAN")
                    runtime_events.extend(stability_trace["events"])
                elif stability_trace["triggered"]:
                    # Sustained (no new event, just a reminder)
                    if "DEGRADED_PLAN" not in runtime_states:
                        runtime_states.append("DEGRADED_PLAN")
            except Exception as exc:  # noqa: BLE001
                stability_trace = {"error": f"{type(exc).__name__}: {exc}"}
                runtime_states.append("DEGRADED_PLAN")
                runtime_events.append(
                    self._stability_event("StabilityGuard", exc))

        # ========================= 2) PLAN ============================
        runtime_states.append("PLANNING")
        try:
            next_replicas = self.autoscaler.step(
                current_replicas, observed_rps, forecast_rps)
            if next_replicas in (self.autoscaler.replicas_min,
                                 self.autoscaler.replicas_max):
                runtime_states.append("DEGRADED_PLAN")
                runtime_events.extend(
                    self.autoscaler.last_trace.get("events", []))
        except Exception as exc:  # noqa: BLE001
            # Safe fallback: keep current replica count, don't scale.
            next_replicas = int(np.clip(
                current_replicas,
                self.autoscaler.replicas_min,
                self.autoscaler.replicas_max))
            runtime_states.append("DEGRADED_PLAN")
            runtime_events.append(
                self._stability_event("PredictiveAutoscaler", exc))

        # Canary (optional) — never crash the tick if it fails
        canary_step: Optional[CanaryStep] = None
        if self.canary is not None and current_canary_share is not None:
            try:
                proposed_share = self.canary.propose(current_canary_share)
                if canary_observed_error is not None:
                    canary_step = self.canary.observe(
                        current_canary_share, proposed_share,
                        canary_observed_error)
                    if not canary_step.accepted:
                        runtime_states.append("DEGRADED_PLAN")
                        runtime_events.extend(canary_step.events)
            except Exception as exc:  # noqa: BLE001
                runtime_states.append("DEGRADED_PLAN")
                runtime_events.append(
                    self._stability_event("CanaryScheduler", exc))
                canary_step = None

        # ========================= 3) GUARD ===========================
        runtime_states.append("GUARDING")
        try:
            audit = self.guardrail.audit(nn_proposal)
            safe_action = np.array(audit["approved"])
            if (audit["cone_violated_before"]
                    or audit["magnitude_violated_before"]):
                runtime_states.append("DEGRADED_GUARD")
                runtime_events.extend(audit.get("events", []))
        except Exception as exc:  # noqa: BLE001
            # Safe fallback: zero-action guarantees no SLO burn.
            audit = {"proposal": np.asarray(nn_proposal, dtype=float).tolist(),
                     "approved": [0.0] * int(np.asarray(nn_proposal).size),
                     "cone_violated_before": False,
                     "magnitude_violated_before": False,
                     "cone_margin_before": 0.0,
                     "cone_margin_after":  0.0,
                     "projection_distance": 0.0,
                     "local_states": ["error"],
                     "events": [self._stability_event("SLOGuardrail", exc)]}
            safe_action = np.zeros(int(np.asarray(nn_proposal).size))
            runtime_states.append("DEGRADED_GUARD")
            runtime_events.extend(audit["events"])

        # ========================= 4) ALLOCATE ========================
        runtime_states.append("ALLOCATING")
        try:
            rps_demand = float(np.linalg.norm(safe_action))
            shares, alloc_info = self.balancer.allocate(rps_demand, zone_target)
            residual_active = (
                alloc_info["rps_residual"] > 1e-6
                or any(z > 1e-6 for z in alloc_info["zone_residual"])
            )
            if any(alloc_info["saturation"]) or residual_active:
                runtime_states.append("DEGRADED_ALLOCATE")
                runtime_events.extend(alloc_info.get("events", []))
        except Exception as exc:  # noqa: BLE001
            n = len(self.balancer.instances)
            # Safe fallback: zero shares → upstream LB will route nothing.
            shares = np.zeros(n)
            alloc_info = {"rps_residual": float("nan"),
                          "zone_residual": [],
                          "saturation": [False] * n,
                          "cost": float("nan"),
                          "local_states": ["error"],
                          "events": [self._stability_event(
                              "WeightedLoadBalancer", exc)]}
            runtime_states.append("DEGRADED_ALLOCATE")
            runtime_events.extend(alloc_info["events"])

        runtime_states.append("EXECUTING")

        entry = {
            "dt":                dt,
            "runtime":           {
                "states": runtime_states,
                "degraded": any(state.startswith("DEGRADED")
                                for state in runtime_states),
                "events": runtime_events,
            },
            "state":              fuse_trace,
            "stability":          stability_trace,
            "replicas_current":   current_replicas,
            "replicas_next":      next_replicas,
            "canary":             vars(canary_step) if canary_step else None,
            "guardrail":          audit,
            "alloc_shares":       shares.tolist(),
            "alloc_info":         alloc_info,
        }
        self.trace.append(entry)
        self._tick_index += 1
        return entry
