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
        b = np.concatenate([[rps_demand],
                            np.asarray(zone_target, dtype=float)])
        lb = np.array([i.rps_min for i in self.instances])
        ub = np.array([i.rps_max for i in self.instances])
        res = lsq_linear(A, b, bounds=(lb, ub))
        shares = res.x
        realised = A @ shares
        info = {
            "rps_residual":   float(abs(realised[0] - rps_demand)),
            "zone_residual":  np.abs(realised[1:] - zone_target).tolist(),
            "saturation":     [(shares[i] >= ub[i] - 1e-6)
                                or (shares[i] <= lb[i] + 1e-6)
                                for i in range(len(self.instances))],
            "cost":           float(res.cost),
        }
        return shares, info
