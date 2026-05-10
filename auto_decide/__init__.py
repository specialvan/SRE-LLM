"""auto_decide — decision dynamics under Lyapunov hard constraints.

Package entry points mirror the sections of the source article:

- ``graph``       — §1.1 interaction intent graph G_I = (V_I, E_I)
- ``dynamics``    — §1.2 bicycle dynamics on a nonlinear manifold
- ``potential``   — §1.3 constrained gradient flow ẋ = -∇φ(x)
- ``lyapunov``    — §2.1 Lyapunov stability dV/dt ≤ 0
- ``reachable``   — §2.2 forward reachable set R(x₀, T)
- ``game``        — §2.3 incomplete-information game / safety redundancy
- ``invariant``   — §3.1 control invariant set operator T_inv
- ``cbf``         — §3.2 control barrier function h(x) & CBF-QP
- ``planner``     — §4   end-to-end structural planner
- ``trace``       — structured trace schema and JSONL serialization
"""

from .types import State, Control, AgentType
from .graph import Node, Edge, InteractionIntentGraph
from .dynamics import BicycleModel, Obstacle, CircleObstacle, Manifold
from .potential import PotentialField
from .lyapunov import QuadraticLyapunov, StabilityMonitor
from .reachable import ReachableSet, DeadZoneDetector
from .cbf import (BarrierFunction, BrakingDistanceBarrier, DistanceBarrier,
                  CBFQPFilter)
from .invariant import ControlInvariantOperator
from .game import BeliefState, WorstCaseGame
from .planner import StructuralPlanner
from .trace import TRACE_SCHEMA_VERSION, build_trace_record

__all__ = [
    "State", "Control", "AgentType",
    "Node", "Edge", "InteractionIntentGraph",
    "BicycleModel", "Obstacle", "CircleObstacle", "Manifold",
    "PotentialField",
    "QuadraticLyapunov", "StabilityMonitor",
    "ReachableSet", "DeadZoneDetector",
    "BarrierFunction", "DistanceBarrier", "BrakingDistanceBarrier",
    "CBFQPFilter",
    "ControlInvariantOperator",
    "BeliefState", "WorstCaseGame",
    "StructuralPlanner",
    "TRACE_SCHEMA_VERSION", "build_trace_record",
]

__version__ = "0.1.0"
