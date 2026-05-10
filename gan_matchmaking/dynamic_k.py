"""§3 Dynamic K-Factor (streak-dependent K).

Article formula (image-2.png):

    K(streak) = K_max / (1 + exp(-lam · (streak - theta)))

Interpretation: as ``streak`` grows, K can be shaped either way. The "matchmaking
anti-streak" folklore corresponds to ``K`` *shrinking* when you win many in a row,
so a win gives you fewer points and a loss costs you more. We model that as a
logistic with a *negative* effective slope on wins (parameter ``penalize_wins``).
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class DynamicK:
    k_max: float = 32.0
    k_min: float = 4.0
    lam: float = 0.7
    theta: float = 5.0
    penalize_wins: bool = True

    def k(self, streak: int) -> float:
        """Return the K-factor given the current win-streak length.

        If ``penalize_wins`` is True, K decays from ``k_max`` toward ``k_min`` as the
        streak grows, matching the article's claim that streak protection
        wanes exponentially.
        """
        if self.penalize_wins:
            # Logistic decay: at streak<<theta -> k_max, streak>>theta -> k_min.
            s = 1.0 / (1.0 + math.exp(self.lam * (streak - self.theta)))
            return self.k_min + (self.k_max - self.k_min) * s
        # Symmetric logistic *growth* variant, kept for completeness.
        s = 1.0 / (1.0 + math.exp(-self.lam * (streak - self.theta)))
        return self.k_min + (self.k_max - self.k_min) * s

    def delta_rating(self, expected: float, actual: float, streak: int) -> float:
        """Return Elo-style delta = ``K(streak) · (actual - expected)``."""
        return self.k(streak) * (actual - expected)
