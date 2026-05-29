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

import numpy as np

from .exceptions import AdapterInputError
from .events import make_event


@dataclass
class CanaryStep:
    from_pct: float
    to_pct: float
    predicted_error_rate: float
    observed_error_rate: float
    trust_region: float
    accepted: bool
    local_states: list[str] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)


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
    _initialised: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self.slo_error_budget = float(self.slo_error_budget)
        if not np.isfinite(self.slo_error_budget) or self.slo_error_budget <= 0:
            raise ValueError('slo_error_budget must be positive')
        self.eta_init = float(self.eta_init)
        if not np.isfinite(self.eta_init) or self.eta_init <= 0:
            raise ValueError('eta_init must be positive')
        self.eta_min = float(self.eta_min)
        if not np.isfinite(self.eta_min) or self.eta_min <= 0:
            raise ValueError('eta_min must be positive')
        self.eta_max = float(self.eta_max)
        if not np.isfinite(self.eta_max) or self.eta_max <= 0:
            raise ValueError('eta_max must be positive')
        if not self.eta_min <= self.eta_init <= self.eta_max:
            raise ValueError('eta_min <= eta_init <= eta_max required')
        self.rho_shrink = float(self.rho_shrink)
        if not np.isfinite(self.rho_shrink) or self.rho_shrink < 0.0:
            raise ValueError('rho_shrink must be non-negative and finite')
        self.rho_grow = float(self.rho_grow)
        if not np.isfinite(self.rho_grow) or self.rho_grow < 0.0:
            raise ValueError('rho_grow must be non-negative and finite')
        if self.rho_shrink > self.rho_grow:
            raise ValueError('rho_shrink <= rho_grow required')
        self._eta = self.eta_init

    def _shrink_eta(self) -> None:
        self._eta = max(self.eta_min, self._eta * 0.5)

    @staticmethod
    def _validate_share(value: float, name: str) -> float:
        value = float(value)
        if not np.isfinite(value):
            raise AdapterInputError(f'{name} must be finite')
        if value < 0.0 or value > 1.0:
            raise AdapterInputError(f'{name} must be within [0, 1]')
        return value

    @staticmethod
    def _validate_error_rate(value: float) -> float:
        value = float(value)
        if not np.isfinite(value):
            raise AdapterInputError('observed_error_rate must be finite')
        if value < 0.0:
            raise AdapterInputError('observed_error_rate must be non-negative')
        return value

    # ------------------------------------------------------------------
    def propose(self, current_share: float) -> float:
        """Return the next share to try (bounded by trust region)."""
        current_share = self._validate_share(current_share, 'current_share')
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
        current_share = self._validate_share(current_share, 'current_share')
        proposed_share = self._validate_share(proposed_share, 'proposed_share')
        observed_error_rate = self._validate_error_rate(observed_error_rate)
        if not self._initialised and abs(current_share - self._last_share) > 1e-9:
            self._initialised = True
            self._last_share = proposed_share
            self._last_err = observed_error_rate
            accepted = observed_error_rate <= self.slo_error_budget
            local_states = ["observe", "initialise"]
            events = []
            if not accepted:
                self._shrink_eta()
                local_states.append("shrink")
                local_states.append("freeze")
                events.append(make_event(
                    stage="CanaryScheduler",
                    kind="rollout_rejected",
                    detail="observed error burned the canary budget",
                    safe_action="shrink trust region and freeze rollout progress",
                    observed_error_rate=observed_error_rate,
                    slo_error_budget=self.slo_error_budget,
                    trust_region=self._eta,
                ))
            return CanaryStep(
                from_pct=current_share,
                to_pct=proposed_share,
                predicted_error_rate=observed_error_rate,
                observed_error_rate=observed_error_rate,
                trust_region=self._eta,
                accepted=accepted,
                local_states=local_states,
                events=events,
            )

        predicted = self._last_err + self._b_est * (proposed_share - self._last_share)

        # improvement ratio ρ: ``actual_gain / predicted_gain``
        actual_gain = self.slo_error_budget - observed_error_rate
        predicted_gain = self.slo_error_budget - predicted
        if abs(predicted_gain) > 1e-9:
            rho = actual_gain / predicted_gain
        else:
            rho = 1.0

        # Adapt η
        local_states = ["observe"]
        events = []
        accepted = observed_error_rate <= self.slo_error_budget
        if not accepted:
            self._shrink_eta()
            local_states.append("shrink")
        elif rho > self.rho_grow:
            self._eta = min(self.eta_max, self._eta * 1.5)
            local_states.append("expand")
        elif rho < self.rho_shrink:
            self._shrink_eta()
            local_states.append("shrink")

        if not accepted:
            local_states.append("freeze")
            events.append(make_event(
                stage="CanaryScheduler",
                kind="rollout_rejected",
                detail="observed error burned the canary budget",
                safe_action="shrink trust region and freeze rollout progress",
                observed_error_rate=observed_error_rate,
                slo_error_budget=self.slo_error_budget,
                trust_region=self._eta,
            ))

        # Every trial produces a usable local slope, even if rollout freezes.
        if proposed_share - current_share > 1e-6:
            self._b_est = (observed_error_rate - self._last_err) / \
                          (proposed_share - current_share)
            self._last_share = proposed_share
            self._last_err = observed_error_rate
            self._initialised = True
            local_states.append("refit" if accepted else "refit_rejected")

        return CanaryStep(
            from_pct=current_share,
            to_pct=proposed_share,
            predicted_error_rate=predicted,
            observed_error_rate=observed_error_rate,
            trust_region=self._eta,
            accepted=accepted,
            local_states=local_states,
            events=events,
        )
