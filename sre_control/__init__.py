"""sre_control — SRE-native adapters around the starship control primitives.

Each module here is a **thin wrapper** around one of the ``starship``
modules. The mechanism is identical; only the I/O vocabulary changes:

    starship side                 SRE side
    ─────────────────────         ─────────────────────
    thrust bounds                 pool connection bounds
    reference trajectory          traffic-split trajectory
    attitude on SO(3)             ring position / version state
    pointing cone                 SLO guardrail
    radar + IMU + vision          metrics + traces + RUM
    horizon QP                    predictive autoscaler
    bang-bang flip                min-time blue/green switch
    thrust allocation             weighted load balancer

The goal is to make it trivial to *compose* an end-to-end SRE control
loop out of eight parameterised primitives rather than re-deriving the
math each time.
"""

from .pool_planner import PoolCapacityPlanner
from .canary_scheduler import CanaryScheduler, CanaryStep
from .topology_state import TopologyState
from .slo_guardrail import SLOGuardrail
from .signal_fusion import SignalFusion, Signal
from .predictive_autoscaler import PredictiveAutoscaler
from .fast_switcher import FastTrafficSwitcher
from .weighted_balancer import WeightedLoadBalancer, Instance
from .stack import SREControlStack
from .events import (EVENT_COUNTEREXAMPLES, REQUIRED_EVENT_FIELDS,
                     make_event, validate_event)

__all__ = [
    "PoolCapacityPlanner",
    "CanaryScheduler", "CanaryStep",
    "TopologyState",
    "SLOGuardrail",
    "SignalFusion", "Signal",
    "PredictiveAutoscaler",
    "FastTrafficSwitcher",
    "WeightedLoadBalancer", "Instance",
    "SREControlStack",
    "EVENT_COUNTEREXAMPLES", "REQUIRED_EVENT_FIELDS",
    "make_event", "validate_event",
]

__version__ = "0.1.0"
