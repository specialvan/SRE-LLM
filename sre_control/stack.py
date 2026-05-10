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
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

from .canary_scheduler import CanaryScheduler, CanaryStep
from .pool_planner import PoolCapacityPlanner
from .predictive_autoscaler import PredictiveAutoscaler
from .signal_fusion import SignalFusion, Signal
from .slo_guardrail import SLOGuardrail
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

    trace: List[dict] = field(default_factory=list)

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
        """Run one control tick and return a structured trace entry."""
        # 1) Fuse observations
        fuse_trace = self.fusion.step(dt, sensor_readings)
        observed_rps = float(self.fusion.state[0])

        # 2) Plan replicas via MPC autoscaler
        next_replicas = self.autoscaler.step(
            current_replicas, observed_rps, forecast_rps)

        # 3) Canary (optional) with trust-region
        canary_step: Optional[CanaryStep] = None
        if self.canary is not None and current_canary_share is not None:
            proposed_share = self.canary.propose(current_canary_share)
            if canary_observed_error is not None:
                canary_step = self.canary.observe(
                    current_canary_share, proposed_share,
                    canary_observed_error)

        # 4) SLO guardrail — project the NN proposal onto the feasible set
        audit = self.guardrail.audit(nn_proposal)
        safe_action = np.array(audit["approved"])

        # 5) Allocate — weighted load balancer
        rps_demand = float(np.linalg.norm(safe_action))
        shares, alloc_info = self.balancer.allocate(rps_demand, zone_target)

        entry = {
            "dt":                dt,
            "state":              fuse_trace,
            "replicas_current":   current_replicas,
            "replicas_next":      next_replicas,
            "canary":             vars(canary_step) if canary_step else None,
            "guardrail":          audit,
            "alloc_shares":       shares.tolist(),
            "alloc_info":         alloc_info,
        }
        self.trace.append(entry)
        return entry
