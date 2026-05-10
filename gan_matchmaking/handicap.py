"""§6 Handicap Elo (streak penalty / compensation).

Article formula (image-5.png):

    E_A = 1 / (1 + 10^{ (R_B - R_A + Penalty) / 400 })

``Penalty`` grows with the player's win-streak, pulling the expected win rate
back toward 50% (and, symmetrically, shrinks / turns negative under a
losing-streak to give the "sweet-match" compensation).
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class HandicapElo:
    # Maximum penalty (in rating points) applied at very long streaks.
    max_penalty: float = 200.0
    # How fast the logistic saturates; ``tau`` controls the streak at which
    # ~50% of max_penalty is reached.
    tau: float = 3.0

    def penalty(self, win_streak: int, loss_streak: int = 0) -> float:
        """Return the additive penalty to R_A in the Elo formula.

        Positive penalty = pull expected win rate *down* (the player is "on fire"
        so the system handicaps them). Negative penalty = "sweet match"
        compensation after losing streak.
        """
        w = self.max_penalty * (1.0 - 1.0 / (1.0 + (win_streak / max(self.tau, 1e-6))))
        l = self.max_penalty * (1.0 - 1.0 / (1.0 + (loss_streak / max(self.tau, 1e-6))))
        return w - l

    @staticmethod
    def expected_win(r_a: float, r_b: float, penalty: float = 0.0) -> float:
        """Elo expected win rate for A, with penalty added to ``R_B - R_A``."""
        # Classical Elo: E_A = 1/(1+10^{(R_B - R_A + Penalty)/400}).
        return 1.0 / (1.0 + 10.0 ** ((r_b - r_a + penalty) / 400.0))

    @staticmethod
    def update(r_a: float, r_b: float, score_a: float, k: float = 32.0,
               penalty: float = 0.0) -> tuple[float, float]:
        """Return updated ratings ``(r_a', r_b')`` for A with given score_a."""
        e_a = HandicapElo.expected_win(r_a, r_b, penalty)
        r_a2 = r_a + k * (score_a - e_a)
        r_b2 = r_b + k * ((1.0 - score_a) - (1.0 - e_a))
        return r_a2, r_b2
