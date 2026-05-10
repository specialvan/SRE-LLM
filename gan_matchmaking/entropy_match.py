"""§7 Information-entropy matchmaking.

Article formula (image-6.png):

    max_M  H(Outcome) = - ∫ p(θ) log2 p(θ) dθ

For a two-outcome match (win / loss) this reduces to the binary Shannon entropy
of the predicted win probability. The matcher prefers the config whose
predicted outcome is closest to 50/50.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Iterable, List, Tuple

from .types import MatchConfig, Player


def binary_entropy(p: float) -> float:
    """Return ``-p log2 p - (1-p) log2 (1-p)`` with log(0) = 0."""
    if p <= 0.0 or p >= 1.0:
        return 0.0
    return -(p * math.log2(p) + (1.0 - p) * math.log2(1.0 - p))


WinProbFn = Callable[[List[Player], List[Player]], float]


@dataclass
class EntropyMatcher:
    # Minimum acceptable entropy (0..1). Matches below this are rejected.
    min_entropy: float = 0.9
    win_prob_fn: WinProbFn = None  # type: ignore[assignment]

    def _win_prob(self, team_a: List[Player], team_b: List[Player]) -> float:
        if self.win_prob_fn is not None:
            return float(self.win_prob_fn(team_a, team_b))
        # Default Elo-ish win prob using rating.mu with a 10-mu scale.
        mu_a = sum(p.rating.mu for p in team_a)
        mu_b = sum(p.rating.mu for p in team_b)
        return 1.0 / (1.0 + 10.0 ** ((mu_b - mu_a) / (10.0 * max(1, len(team_a)))))

    def score_config(self, cfg: MatchConfig) -> Tuple[float, float]:
        """Return ``(p_a_win, entropy)`` for this configuration."""
        p = self._win_prob(cfg.team_a, cfg.team_b)
        return p, binary_entropy(p)

    def find_best_match(self, candidates: Iterable[MatchConfig]) -> MatchConfig | None:
        """Return the config whose outcome entropy is the highest (most uncertain)."""
        best: MatchConfig | None = None
        best_h = -1.0
        for cfg in candidates:
            _, h = self.score_config(cfg)
            if h > best_h:
                best_h = h
                best = cfg
        return best

    def is_acceptable(self, cfg: MatchConfig) -> bool:
        _, h = self.score_config(cfg)
        return h >= self.min_entropy
