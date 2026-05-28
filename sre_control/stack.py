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
Stages catch only recoverable control-domain errors. If an adapter raises
``RecoverableControlError``, the stack:

  1. emits an ``adapter_exception`` runtime event naming the stage,
     exception type, cause type, and recoverability,
  2. appends the matching ``DEGRADED_*`` state,
  3. substitutes a validated safe fallback for the stage's output so
     downstream stages can keep running,
  4. records the full trace as usual.

Programmer errors such as ``AttributeError`` and ``TypeError`` intentionally
propagate. ``stability_violation`` is reserved for Lyapunov/stability red-lines.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence

import numpy as np

from .canary_scheduler import CanaryScheduler, CanaryStep
from .events import make_event
from .exceptions import AdapterInputError, RecoverableControlError
from .pool_planner import PoolCapacityPlanner
from .predictive_autoscaler import PredictiveAutoscaler
from .signal_fusion import Signal, SignalFusion
from .slo_guardrail import SLOGuardrail
from .stability_guard import StabilityGuard
from .topology_state import TopologyState
from .fast_switcher import FastTrafficSwitcher
from .weighted_balancer import WeightedLoadBalancer
from .stack_contract import stack_data_contract


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
    _elapsed_time: float = field(default=0.0, init=False, repr=False)
    _last_good_alloc_shares: Optional[np.ndarray] = field(
        default=None, init=False, repr=False
    )
    _last_good_alloc_signature: Optional[tuple] = field(
        default=None, init=False, repr=False
    )

    # ------------------------------------------------------------------
    def _allocator_signature(self) -> tuple:
        return tuple(
            (
                inst.name,
                tuple(float(value) for value in inst.zone_vector),
                float(inst.rps_min),
                float(inst.rps_max),
            )
            for inst in self.balancer.instances
        )

    # ------------------------------------------------------------------
    def _can_reuse_last_good_alloc(self) -> bool:
        if self._last_good_alloc_shares is None:
            return False
        current_signature = self._allocator_signature()
        if self._last_good_alloc_signature != current_signature:
            return False
        if self._last_good_alloc_shares.size != len(self.balancer.instances):
            return False
        for share, inst in zip(self._last_good_alloc_shares, self.balancer.instances):
            if not np.isfinite(share):
                return False
            if share < inst.rps_min - 1e-6 or share > inst.rps_max + 1e-6:
                return False
        return True

    # ------------------------------------------------------------------
    @staticmethod
    def _adapter_exception_event(
        stage_label: str, exc: RecoverableControlError, fallback_action: str
    ) -> dict:
        cause_type = (
            "adapter_input" if isinstance(exc, AdapterInputError) else "control_domain"
        )
        adapter_family = stack_data_contract()["event_stage_routes"].get(
            stage_label, "unknown"
        )
        return make_event(
            stage=stage_label,
            kind="adapter_exception",
            detail=f"{type(exc).__name__}: recoverable control-domain failure",
            safe_action=(
                "substitute the stage's validated fallback, continue the tick, "
                "and record DEGRADED_<stage>"
            ),
            exception_type=type(exc).__name__,
            cause_type=cause_type,
            adapter_family=adapter_family,
            fault_family=cause_type,
            fallback_action=fallback_action,
            recoverable=True,
        )

    # ------------------------------------------------------------------
    def step(
        self,
        dt: float,
        sensor_readings: Sequence[tuple[Signal, np.ndarray | None]],
        forecast_rps: float,
        current_replicas: int,
        zone_target: np.ndarray,
        nn_proposal: np.ndarray,
        current_canary_share: Optional[float] = None,
        canary_observed_error: Optional[float] = None,
    ) -> dict:
        """Run one control tick and return a structured trace entry.

        Recoverable control-domain failures still produce a trace with an
        ``adapter_exception`` event plus the appropriate DEGRADED_* state.
        Programmer errors propagate so callers see implementation bugs.
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
        except RecoverableControlError as exc:
            fuse_trace = {
                "x": None,
                "P_trace": None,
                "signals": [],
                "local_states": ["error"],
                "events": [
                    self._adapter_exception_event(
                        "SignalFusion", exc, "use_forecast_rps_for_observed_load"
                    )
                ],
            }
            observed_rps = float(forecast_rps)  # safe fallback
            runtime_states.append("DEGRADED_OBSERVE")
            runtime_events.extend(fuse_trace["events"])

        # ========================= 1b) STABILITY MONITOR (optional) ==
        # Runs between OBSERVE and PLAN.  A triggered monitor feeds a
        # `stability_violation` event + DEGRADED_PLAN so downstream
        # planners know to prefer conservative commands.
        stability_trace: Optional[dict] = None
        if self.stability is not None and fuse_trace.get("x") is not None:
            try:
                tick_time = self._elapsed_time
                stability_trace = self.stability.step(
                    np.asarray(self.fusion.state, dtype=float), t=float(tick_time)
                )
                if stability_trace["events"]:
                    # Fresh trigger this tick
                    runtime_states.append("DEGRADED_PLAN")
                    runtime_events.extend(stability_trace["events"])
                elif stability_trace["triggered"]:
                    # Sustained (no new event, just a reminder)
                    if "DEGRADED_PLAN" not in runtime_states:
                        runtime_states.append("DEGRADED_PLAN")
            except RecoverableControlError as exc:
                stability_trace = {"error": f"{type(exc).__name__}: {exc}"}
                runtime_states.append("DEGRADED_PLAN")
                runtime_events.append(
                    self._adapter_exception_event(
                        "StabilityGuard", exc, "skip_stability_monitor_this_tick"
                    )
                )
        conservative_plan = bool(
            stability_trace is not None and stability_trace.get("triggered", False)
        )

        # ========================= 2) PLAN ============================
        runtime_states.append("PLANNING")
        try:
            if conservative_plan:
                original_max_step = self.autoscaler.max_step
                original_u_min = self.autoscaler._mpc.u_min.copy()
                original_u_max = self.autoscaler._mpc.u_max.copy()
                conservative_step = min(float(original_max_step), 1.0)
                self.autoscaler.max_step = int(conservative_step)
                self.autoscaler._mpc.u_min = np.array([-conservative_step])
                self.autoscaler._mpc.u_max = np.array([conservative_step])
                try:
                    next_replicas = self.autoscaler.step(
                        current_replicas, observed_rps, forecast_rps
                    )
                finally:
                    self.autoscaler.max_step = original_max_step
                    self.autoscaler._mpc.u_min = original_u_min
                    self.autoscaler._mpc.u_max = original_u_max
            else:
                next_replicas = self.autoscaler.step(
                    current_replicas, observed_rps, forecast_rps
                )
            if next_replicas in (
                self.autoscaler.replicas_min,
                self.autoscaler.replicas_max,
            ):
                runtime_states.append("DEGRADED_PLAN")
                runtime_events.extend(self.autoscaler.last_trace.get("events", []))
        except RecoverableControlError as exc:
            # Safe fallback: keep current replica count, don't scale.
            next_replicas = int(
                np.clip(
                    current_replicas,
                    self.autoscaler.replicas_min,
                    self.autoscaler.replicas_max,
                )
            )
            runtime_states.append("DEGRADED_PLAN")
            runtime_events.append(
                self._adapter_exception_event(
                    "PredictiveAutoscaler", exc, "keep_current_replicas"
                )
            )
            self.autoscaler.last_trace = {
                "next_replicas": next_replicas,
                "local_states": ["error"],
                "events": [],
                "fallback": True,
                "fallback_reason": f"{type(exc).__name__}: {exc}",
            }

        # Canary (optional) — never crash the tick if it fails
        canary_step: Optional[CanaryStep] = None
        if (
            self.canary is not None
            and current_canary_share is not None
            and not conservative_plan
        ):
            try:
                proposed_share = self.canary.propose(current_canary_share)
                if canary_observed_error is not None:
                    canary_step = self.canary.observe(
                        current_canary_share, proposed_share, canary_observed_error
                    )
                    if not canary_step.accepted:
                        runtime_states.append("DEGRADED_PLAN")
                        runtime_events.extend(canary_step.events)
            except RecoverableControlError as exc:
                runtime_states.append("DEGRADED_PLAN")
                runtime_events.append(
                    self._adapter_exception_event(
                        "CanaryScheduler", exc, "skip_canary_step"
                    )
                )
                canary_step = None

        # ========================= 3) GUARD ===========================
        runtime_states.append("GUARDING")
        try:
            audit = self.guardrail.audit(nn_proposal)
            safe_action = np.array(audit["approved"])
            if audit["cone_violated_before"] or audit["magnitude_violated_before"]:
                runtime_states.append("DEGRADED_GUARD")
                runtime_events.extend(audit.get("events", []))
        except RecoverableControlError as exc:
            # Safe fallback: zero-action guarantees no SLO burn.
            fallback_size = int(self.guardrail.nominal_direction.size)
            audit = {
                "proposal": [],
                "approved": [0.0] * fallback_size,
                "cone_violated_before": False,
                "magnitude_violated_before": False,
                "cone_margin_before": 0.0,
                "cone_margin_after": 0.0,
                "projection_distance": 0.0,
                "local_states": ["error"],
                "events": [
                    self._adapter_exception_event(
                        "SLOGuardrail", exc, "zero_guardrail_action"
                    )
                ],
            }
            safe_action = np.zeros(fallback_size)
            runtime_states.append("DEGRADED_GUARD")
            runtime_events.extend(audit["events"])

        # ========================= 4) ALLOCATE ========================
        runtime_states.append("ALLOCATING")
        try:
            # Guardrail actions are direction vectors whose L2 norm encodes
            # total demand.  Zone placement is supplied separately through
            # zone_target, so component sums are not treated as RPS demand.
            rps_demand = float(np.linalg.norm(safe_action))
            shares, alloc_info = self.balancer.allocate(rps_demand, zone_target)
            self._last_good_alloc_shares = shares.copy()
            self._last_good_alloc_signature = self._allocator_signature()
            residual_active = alloc_info["rps_residual"] > 1e-6 or any(
                z > 1e-6 for z in alloc_info["zone_residual"]
            )
            if any(alloc_info["saturation"]) or residual_active:
                runtime_states.append("DEGRADED_ALLOCATE")
                runtime_events.extend(alloc_info.get("events", []))
        except RecoverableControlError as exc:
            n = len(self.balancer.instances)
            if self._can_reuse_last_good_alloc():
                shares = self._last_good_alloc_shares.copy()
                fallback_state = "reuse_last_good_shares"
            else:
                shares = np.zeros(n)
                fallback_state = "bootstrap_zero_fallback"
            alloc_info = {
                "rps_residual": None,
                "zone_residual": [],
                "saturation": [False] * n,
                "cost": None,
                "local_states": ["error", fallback_state],
                "events": [
                    self._adapter_exception_event(
                        "WeightedLoadBalancer", exc, fallback_state
                    )
                ],
            }
            runtime_states.append("DEGRADED_ALLOCATE")
            runtime_events.extend(alloc_info["events"])

        runtime_states.append("EXECUTING")

        entry = {
            "dt": dt,
            "runtime": {
                "states": runtime_states,
                "degraded": any(
                    state.startswith("DEGRADED") for state in runtime_states
                ),
                "events": runtime_events,
            },
            "state": fuse_trace,
            "stability": stability_trace,
            "replicas_current": current_replicas,
            "replicas_next": next_replicas,
            "canary": vars(canary_step) if canary_step else None,
            "guardrail": audit,
            "alloc_shares": shares.tolist(),
            "alloc_info": alloc_info,
        }
        self.trace.append(entry)
        self._tick_index += 1
        self._elapsed_time += float(dt)
        return entry
