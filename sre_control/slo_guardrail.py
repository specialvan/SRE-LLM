"""§4 Cone + magnitude filter adapter — SLO guardrail.

SRE problem
-----------
Any upstream AI/ML component (predictive autoscaler, anomaly-driven
re-router, LLM-driven capacity planner) emits *candidate* actions.
You **must** project them to a feasible set before dispatch.

Feasible set for traffic control
--------------------------------

    ‖u‖ ≤ u_max                   (per-window global RPS cap)
    n̂ᵀ u ≥ ‖u‖ · cos θ_max         (routing direction must stay within
                                    θ_max of the nominal distribution)

This is *literally* the thrust cone from §4 — the adapter reuses the
closed-form ``ConeQPFilter`` so the filter is O(1) on the hot path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from starship.thrust_constraints import ConeQPFilter, pointing_cone_constraint
from .events import make_event


@dataclass
class SLOGuardrail:
    """Feasible-set projection for AI-proposed traffic/routing actions.

    ``nominal_direction`` — the safe baseline traffic distribution the
                            guardrail trusts (e.g. current weighted RR).
    ``theta_max_deg``      — how far a proposal is allowed to rotate
                            the distribution vector in one step.
    ``magnitude_cap``      — global RPS cap across the whole cluster.
    """

    nominal_direction: np.ndarray = field(
        default_factory=lambda: np.array([1.0, 0.0, 0.0]))
    theta_max_deg: float = 15.0
    magnitude_cap: float = 10_000.0
    magnitude_floor: float = 0.0

    _filter: ConeQPFilter = field(init=False, repr=False)

    def __post_init__(self) -> None:
        n = self.nominal_direction / (np.linalg.norm(
            self.nominal_direction) + 1e-12)
        self._filter = ConeQPFilter(
            n_hat=n,
            theta_max=np.deg2rad(self.theta_max_deg),
            T_max=self.magnitude_cap,
            T_min=self.magnitude_floor,
        )

    # ------------------------------------------------------------------
    def approve(self, proposal: Sequence[float]) -> np.ndarray:
        """Project the proposal onto the feasible set.

        Returns the safe action exactly like :meth:`ConeQPFilter.filter`.
        """
        return self._filter.filter(proposal)

    # ------------------------------------------------------------------
    def audit(self, proposal: Sequence[float]) -> dict:
        """Return a structured trace the on-call can attach to change-logs."""
        proposal = np.asarray(proposal, dtype=float)
        cone_margin_before = pointing_cone_constraint(
            proposal, self._filter.n_hat, self._filter.theta_max)
        magnitude_before = float(np.linalg.norm(proposal))

        safe = self._filter.filter(proposal)
        cone_margin_after = pointing_cone_constraint(
            safe, self._filter.n_hat, self._filter.theta_max)
        cone_violated = cone_margin_before < -1e-4
        magnitude_violated = magnitude_before > self.magnitude_cap
        projection_distance = float(np.linalg.norm(proposal - safe))
        events = []
        if cone_violated or magnitude_violated:
            events.append(make_event(
                stage="SLOGuardrail",
                kind="unsafe_proposal_projected",
                detail="proposal violated cone or magnitude constraints",
                safe_action="execute only the projected action",
            ))

        return {
            "proposal":               proposal.tolist(),
            "approved":               safe.tolist(),
            "cone_violated_before":   cone_violated,
            "magnitude_violated_before": magnitude_violated,
            "cone_margin_before":     cone_margin_before,
            "cone_margin_after":      cone_margin_after,
            "projection_distance":    projection_distance,
            "local_states":           ["candidate", "projected", "approved"]
                                      if projection_distance > 1e-9
                                      else ["candidate", "approved"],
            "events":                 events,
        }
