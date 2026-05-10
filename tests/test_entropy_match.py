"""Tests for entropy-based matchmaking (§7)."""
from __future__ import annotations

from gan_matchmaking import EntropyMatcher, MatchConfig, Player, Rating
from gan_matchmaking.entropy_match import binary_entropy


def test_binary_entropy_boundaries():
    assert binary_entropy(0.5) == 1.0
    assert binary_entropy(0.0) == 0.0
    assert binary_entropy(1.0) == 0.0


def _team(mu: float, n: int = 5) -> list[Player]:
    return [Player(id=f"p{i}-{mu}", rating=Rating(mu=mu, sigma=1.0)) for i in range(n)]


def test_prefers_balanced_match():
    em = EntropyMatcher(min_entropy=0.0)
    balanced = MatchConfig(team_a=_team(25.0), team_b=_team(25.0))
    lopsided = MatchConfig(team_a=_team(40.0), team_b=_team(10.0))
    best = em.find_best_match([balanced, lopsided])
    assert best is balanced


def test_min_entropy_filter_rejects_lopsided():
    em = EntropyMatcher(min_entropy=0.9)
    lopsided = MatchConfig(team_a=_team(40.0), team_b=_team(10.0))
    assert not em.is_acceptable(lopsided)
