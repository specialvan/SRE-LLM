"""§8 Allocation adapter — weighted load balancer with hard caps.

SRE problem
-----------
A global rate of RPS must be split across N instances so that::

    sum(share_i) = rps_demand                     (first moment)
    sum(share_i · zone_vector_i) = zone_target    (second moment)

subject to per-instance capacity ``share_i ∈ [min_i, max_i]``.

Naively using the pseudo-inverse (``pinv(A) · demand``) gives a LS
solution that violates box constraints. The booster's
``ThrustAllocator`` — which handles exactly this over-constrained
LS-with-bounds problem — maps 1:1 to weighted load balancing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Sequence, Tuple

import numpy as np
from scipy.optimize import lsq_linear

from .events import make_event
from .exceptions import AdapterInputError, RecoverableControlError


@dataclass
class Instance:
    """Single back-end instance participating in the weighted pool."""
    name: str
    zone_vector: np.ndarray       # shape (k,) — e.g. (cost, latency_cost)
    rps_min: float
    rps_max: float


@dataclass
class WeightedLoadBalancer:
    """Bounded least-squares allocation for (rps, zone-objective).

    The ``allocate`` call solves the same optimisation problem as
    :class:`starship.catch_controller.ThrustAllocator`, but over SRE
    units: RPS split, per-instance box, and a user-supplied zone
    objective such as "keep the east/west split near 55/45".
    """

    instances: List[Instance]

    def __post_init__(self) -> None:
        if not self.instances:
            raise ValueError("instances must not be empty")
        expected_dim = len(np.asarray(self.instances[0].zone_vector))
        for inst in self.instances:
            zone_vector = np.asarray(inst.zone_vector, dtype=float)
            if len(zone_vector) != expected_dim:
                raise ValueError(
                    "all instance zone_vector dimensions must match"
                )
            if not np.isfinite(zone_vector).all():
                raise ValueError("finite zone_vector required")
            if not np.isfinite([inst.rps_min, inst.rps_max]).all():
                raise ValueError("finite rps bounds required")
            if inst.rps_min > inst.rps_max:
                raise ValueError("rps_min <= rps_max required")
            inst.rps_min = float(inst.rps_min)
            inst.rps_max = float(inst.rps_max)
            inst.zone_vector = zone_vector

    def _matrix(self) -> np.ndarray:
        # Row 0 — global RPS sum constraint.
        # Rows 1..k — zone-vector aggregation.
        rows = [np.ones(len(self.instances))]
        for dim in range(len(self.instances[0].zone_vector)):
            rows.append(np.array([inst.zone_vector[dim]
                                  for inst in self.instances]))
        return np.stack(rows)

    def allocate(self, rps_demand: float,
                 zone_target: Sequence[float]
                 ) -> Tuple[np.ndarray, dict]:
        A = self._matrix()
        rps_demand = float(rps_demand)
        if not np.isfinite(rps_demand):
            raise AdapterInputError("non-finite rps_demand")
        zone_target_arr = np.asarray(zone_target, dtype=float)
        if zone_target_arr.ndim != 1 or zone_target_arr.size != len(self.instances[0].zone_vector):
            raise AdapterInputError("zone_target dimension mismatch")
        if not np.isfinite(zone_target_arr).all():
            raise AdapterInputError("non-finite zone_target")
        b = np.concatenate([[rps_demand], zone_target_arr])
        lb = np.array([i.rps_min for i in self.instances])
        ub = np.array([i.rps_max for i in self.instances])
        try:
            res = lsq_linear(A, b, bounds=(lb, ub))
        except (RuntimeError, ValueError) as exc:
            raise RecoverableControlError(
                f"bounded LS solver failed: {exc}"
            ) from exc
        if not bool(getattr(res, "success", False)):
            message = getattr(res, "message", "unknown solver failure")
            raise RecoverableControlError(
                f"bounded LS solver did not converge: {message}"
            )
        shares = res.x
        realised = A @ shares
        saturation = [bool((shares[i] >= ub[i] - 1e-6)
                           or (shares[i] <= lb[i] + 1e-6))
                      for i in range(len(self.instances))]
        rps_residual = float(abs(realised[0] - rps_demand))
        zone_residual = np.abs(realised[1:] - zone_target_arr).tolist()
        rps_residual_fraction = (
            float(rps_residual / abs(rps_demand)) if abs(rps_demand) > 1e-9 else 0.0
        )
        residual_active = (
            rps_residual > 1e-6
            or any(z > 1e-6 for z in zone_residual)
        )
        demand_satisfied = not residual_active
        events = []
        if any(saturation) or residual_active:
            events.append(make_event(
                stage="WeightedLoadBalancer",
                kind="bounded_ls_residual",
                detail="box constraints or residuals were active",
                safe_action="report residual instead of pretending exact matching",
                rps_residual=rps_residual,
                rps_residual_fraction=rps_residual_fraction,
                zone_residual=zone_residual,
                demand_satisfied=demand_satisfied,
            ))
        local_states = ["solve_ls"]
        if any(saturation):
            local_states.append("saturate")
        if residual_active:
            local_states.append("report_residual")
        info = {
            "rps_residual":   rps_residual,
            "rps_residual_fraction": rps_residual_fraction,
            "zone_residual":  zone_residual,
            "demand_satisfied": demand_satisfied,
            "saturation":     saturation,
            "cost":           float(res.cost),
            "local_states":   local_states,
            "events":         events,
        }
        return shares, info
