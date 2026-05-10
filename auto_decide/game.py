"""Incomplete-information game & safety redundancy — §2.3.

The article argues that under unobservable intents the planner must
hedge against worst-case opponents. This module provides:

- :class:`BeliefState` — categorical belief over an agent's intent.
- :class:`WorstCaseGame` — returns the minimum safety buffer required
  when every neighbour plays their worst-case intent (for us).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Tuple

import numpy as np


# ---------------------------------------------------------------------------
# Belief state
# ---------------------------------------------------------------------------

@dataclass
class BeliefState:
    """Categorical belief over an opponent's high-level intent.

    Entropy reflects how uncertain we are; high entropy ⇒ larger buffer.
    """
    distribution: Dict[str, float] = field(default_factory=lambda: {
        "straight": 0.5, "left": 0.2, "right": 0.2, "yield": 0.1,
    })

    def entropy(self) -> float:
        probs = np.array(list(self.distribution.values()), dtype=float)
        probs = probs / max(probs.sum(), 1e-9)
        probs = np.clip(probs, 1e-9, 1.0)
        return float(-(probs * np.log(probs)).sum())

    def max_entropy(self) -> float:
        return float(np.log(max(len(self.distribution), 1)))

    def uncertainty(self) -> float:
        """Normalised entropy ∈ [0, 1]."""
        me = self.max_entropy()
        return self.entropy() / me if me > 1e-9 else 0.0


# ---------------------------------------------------------------------------
# Worst-case game
# ---------------------------------------------------------------------------

@dataclass
class WorstCaseGame:
    """Compute the safety buffer recommended by the §2.3 argument.

    The buffer grows with:
      - relative velocity (closing speed);
      - number of interacting agents;
      - belief-state uncertainty (entropy).

    The exact form is a simple convex combination — it is *not* claiming
    to approximate a true Nash equilibrium, only to enforce the kind of
    redundancy the article demands.
    """

    base_buffer: float = 3.0      # minimum car-to-car distance, meters
    speed_gain: float = 1.2       # meters per (m/s) of closing speed
    entropy_gain: float = 2.0     # meters per unit normalised entropy

    def safe_buffer(self, rel_speed: float,
                    belief: BeliefState) -> float:
        return float(
            self.base_buffer
            + max(rel_speed, 0.0) * self.speed_gain
            + belief.uncertainty() * self.entropy_gain
        )

    def aggregate_buffer(self,
                         rel_speeds: Iterable[float],
                         beliefs: Iterable[BeliefState]) -> float:
        """Take the max over all opponents (worst-case)."""
        rs = list(rel_speeds)
        bs = list(beliefs)
        if not rs or not bs:
            return self.base_buffer
        return max(self.safe_buffer(r, b) for r, b in zip(rs, bs))
