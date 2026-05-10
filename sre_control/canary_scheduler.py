"""§2 SCP adapter — canary rollout with adaptive trust region.

SRE problem
-----------
Rolling a new version from 0% to 100% traffic share must respect SLO
in every step. You have no good *model* of the system (linear response
of error-rate to traffic share is unknown), so you linearise locally
around the current split, do a small step, observe the outcome, and
grow/shrink the trust region based on how close the observation
matched the prediction — this is exactly the SCP loop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class CanaryStep:
    from_pct: float
    to_pct: float
    predicted_error_rate: float
    observed_error_rate: float
    trust_region: float
    accepted: bool


@dataclass
class CanaryScheduler:
    """SCP-style canary rollout.

    Keeps a linear model ``error = a + b · share`` (one parameter
    per scalar canary), refits after each step, and adapts the trust
    region ``eta`` using the classical improvement-ratio rule.
    """

    slo_error_budget: float = 0.01       # 1 % max error rate
    eta_init: float = 0.05               # start by nudging 5 %
    eta_min: float = 0.005
    eta_max: float = 0.20
    rho_grow: float = 0.7
    rho_shrink: float = 0.1

    _b_est: float = field(default=0.0, init=False)
    _last_share: float = field(default=0.0, init=False)
    _last_err: float = field(default=0.0, init=False)
    _eta: float = field(default=None, init=False)

    def __post_init__(self) -> None:
        self._eta = self.eta_init

    # ------------------------------------------------------------------
    def propose(self, current_share: float) -> float:
        """Return the next share to try (bounded by trust region)."""
        next_share = current_share + self._eta
        return min(1.0, next_share)

    # ------------------------------------------------------------------
    def observe(self, current_share: float,
                proposed_share: float,
                observed_error_rate: float) -> CanaryStep:
        """Feed back the observed error rate and adjust trust region.

        This is the SCP update: compute the "improvement ratio" between
        the predicted drop in SLO margin and the observed one.
        """
        predicted = self._last_err + self._b_est * (proposed_share - self._last_share)

        # improvement ratio ρ: ``actual_gain / predicted_gain``
        actual_gain = self.slo_error_budget - observed_error_rate
        predicted_gain = self.slo_error_budget - predicted
        if abs(predicted_gain) > 1e-9:
            rho = actual_gain / predicted_gain
        else:
            rho = 1.0

        # Adapt η
        if rho > self.rho_grow:
            self._eta = min(self.eta_max, self._eta * 1.5)
        elif rho < self.rho_shrink:
            self._eta = max(self.eta_min, self._eta * 0.5)

        accepted = observed_error_rate <= self.slo_error_budget

        # If accepted, refit the linear slope
        if accepted and proposed_share - current_share > 1e-6:
            self._b_est = (observed_error_rate - self._last_err) / \
                          (proposed_share - current_share)
            self._last_share = proposed_share
            self._last_err = observed_error_rate

        return CanaryStep(
            from_pct=current_share,
            to_pct=proposed_share,
            predicted_error_rate=predicted,
            observed_error_rate=observed_error_rate,
            trust_region=self._eta,
            accepted=accepted,
        )
