"""§1 Lossless-convexification adapter — connection-pool capacity planner.

SRE problem
-----------
An upstream pool must keep at least ``min_keep_alive`` idle connections
(for health probes) and not exceed ``max_capacity``. When no traffic is
coming the pool is *forced* to ``min_keep_alive`` (not zero) — making
the feasible pool-size set ``{0} ∪ [min_keep_alive, max_capacity]`` —
which is non-convex, exactly like the Raptor thrust lower-bound donut.

Convexification
---------------
Introduce a slack ``sigma`` ∈ [min_keep_alive, max_capacity]; enforce
``pool_size ≤ sigma``.  Optimal solutions automatically saturate σ so
the relaxation is lossless.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PoolCapacityPlanner:
    """Plan the number of open connections over a short horizon.

    Parameters mirror :class:`starship.lossless_convex.LosslessPDG` but
    are renamed to SRE vocabulary:

        rho1  ↔ min_keep_alive   (keep-alive lower bound)
        rho2  ↔ max_capacity     (pool hard cap)
        Isp   ↔ unit_cost        (cost per connection-second)
    """

    min_keep_alive: int = 4
    max_capacity: int = 200
    unit_cost: float = 1.0           # cost / (connection · second)
    horizon_seconds: float = 10.0

    def plan(self, demand_rps_forecast: list[float]
             ) -> tuple[list[int], dict]:
        """Given a per-second RPS forecast, return optimal pool sizes.

        Solves the scalar analogue of the lossless PDG problem:

            min  Σ unit_cost · sigma_k
            s.t. pool_k ≤ sigma_k                 (lossless slack)
                 min_keep_alive ≤ sigma_k ≤ max_capacity
                 pool_k ≥ demand_rps_forecast[k] / rps_per_conn

        For the simple scalar case this has a closed form:
        ``sigma_k = clip(ceil(forecast_k / rps_per_conn), min, max)``.
        """
        rps_per_conn = 100.0
        pool_plan = []
        total_cost = 0.0
        violations_baseline = 0
        violations_after = 0
        baseline_cost = 0.0
        for rps in demand_rps_forecast:
            demanded = rps / rps_per_conn
            # baseline: either 0 or max_capacity (on/off) — this is the
            # non-convex "donut" behaviour we want to fix.
            baseline = 0 if rps < 1e-6 else self.max_capacity
            if 0 < baseline < self.min_keep_alive:
                violations_baseline += 1
            baseline_cost += self.unit_cost * baseline

            # after: lossless convex relaxation
            sigma = max(self.min_keep_alive,
                        min(self.max_capacity, int(demanded) + 1))
            if 0 < sigma < self.min_keep_alive:
                violations_after += 1
            pool_plan.append(sigma)
            total_cost += self.unit_cost * sigma

        info = {
            "total_cost": total_cost,
            "baseline_cost": baseline_cost,
            "cost_saving_pct": (1.0 - total_cost / baseline_cost) * 100
                                if baseline_cost > 0 else 0.0,
            "violations_baseline": violations_baseline,
            "violations_after": violations_after,
        }
        return pool_plan, info
