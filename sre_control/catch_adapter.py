"""SRE wrapper for catch-phase bounded allocation.

``starship.catch_controller`` remains a physical-layer primitive.  This
module is the migration-layer wrapper: it exposes the same bounded-LS
residual discipline in SRE vocabulary and emits SRE runtime events
without requiring ``starship/`` to import ``sre_control/``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from .weighted_balancer import Instance, WeightedLoadBalancer


@dataclass
class CatchLoadAdapter:
    """Translate catch-allocation semantics to an SRE load-split trace.

    The adapter deliberately delegates the solve to
    :class:`WeightedLoadBalancer`, because that class already owns the
    bounded least-squares contract.  This wrapper adds only the review
    boundary: SRE naming, JSON-safe trace shape, and a source tag that
    makes clear this is a migration-layer example rather than a SpaceX
    implementation claim.
    """

    instances: list[Instance]
    source: str = "sre_wrapper_for_catch_allocation"
    _balancer: WeightedLoadBalancer = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._balancer = WeightedLoadBalancer(self.instances)

    def allocate(
        self, request_demand: float, placement_target: Sequence[float]
    ) -> dict[str, object]:
        """Allocate request load and expose residuals instead of hiding them."""
        shares, info = self._balancer.allocate(request_demand, placement_target)
        local_states = list(info["local_states"])
        local_states.append("sre_catch_wrapper")

        return {
            "source": self.source,
            "request_demand": float(request_demand),
            "placement_target": np.asarray(placement_target, dtype=float).tolist(),
            "shares": shares.tolist(),
            "rps_residual": float(info["rps_residual"]),
            "rps_residual_fraction": float(info["rps_residual_fraction"]),
            "zone_residual": [float(value) for value in info["zone_residual"]],
            "demand_satisfied": bool(info["demand_satisfied"]),
            "saturation": [bool(value) for value in info["saturation"]],
            "cost": float(info["cost"]),
            "local_states": local_states,
            "events": list(info["events"]),
        }
