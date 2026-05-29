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

from .exceptions import AdapterInputError
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
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("source must be a non-empty string")
        self.source = self.source.strip()
        self._balancer = WeightedLoadBalancer(self.instances)

    def _validate_placement_target(self, placement_target: Sequence[float]) -> np.ndarray:
        target = np.asarray(placement_target, dtype=float)
        expected_dim = len(self._balancer.instances[0].zone_vector)
        if target.ndim != 1 or target.size != expected_dim:
            raise AdapterInputError('placement_target dimension mismatch')
        if not np.isfinite(target).all():
            raise AdapterInputError('non-finite placement_target')
        return target

    def allocate(
        self, request_demand: float, placement_target: Sequence[float]
    ) -> dict[str, object]:
        """Allocate request load and expose residuals instead of hiding them."""
        request_demand_value = float(request_demand)
        if not np.isfinite(request_demand_value):
            raise AdapterInputError("non-finite request_demand")
        if request_demand_value < 0.0:
            raise AdapterInputError("negative request_demand")
        placement_target_arr = self._validate_placement_target(placement_target)
        shares, info = self._balancer.allocate(
            request_demand_value,
            placement_target_arr,
        )
        local_states = list(info["local_states"])
        local_states.append("sre_catch_wrapper")

        return {
            "source": self.source,
            "request_demand": request_demand_value,
            "placement_target": placement_target_arr.tolist(),
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
