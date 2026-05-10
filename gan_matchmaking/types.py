"""Common data types shared across matchmaking modules."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Rating:
    """TrueSkill-style rating, a Gaussian over latent skill.

    Mathematical object: ``s ~ N(mu, sigma^2)``.
    """
    mu: float = 25.0
    sigma: float = 25.0 / 3.0

    @property
    def conservative(self) -> float:
        """A ranking-friendly scalar: ``mu - 3 sigma``."""
        return self.mu - 3.0 * self.sigma


@dataclass
class Player:
    """A player in the matchmaking system."""
    id: str
    rating: Rating = field(default_factory=Rating)
    # Recent history used by dynamic K / handicap / survival modules.
    win_streak: int = 0
    loss_streak: int = 0
    total_matches: int = 0
    # Optional behavioral feature vector (walk patterns, KDA, participation ratio...).
    behavior: Optional[List[float]] = None


@dataclass
class MatchResult:
    """Result of a single match."""
    team_a: List[str]
    team_b: List[str]
    score_a: float  # 1.0 = A wins, 0.0 = B wins, 0.5 = draw.
    duration_minutes: float = 0.0


@dataclass
class MatchConfig:
    """Candidate match configuration: two teams pre-assembled by the matchmaker."""
    team_a: List[Player]
    team_b: List[Player]
