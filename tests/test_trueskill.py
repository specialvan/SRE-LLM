"""Tests for TrueSkill rater (§1)."""
from __future__ import annotations

import random

from gan_matchmaking import Player, TrueSkillRater


def _run_match(rater: TrueSkillRater, winner: Player, loser: Player) -> None:
    rater.update([winner], [loser], 1.0)


def test_sigma_shrinks_with_matches():
    rater = TrueSkillRater()
    a = Player(id="a", rating=rater.new_rating())
    b = Player(id="b", rating=rater.new_rating())
    sigma_initial = a.rating.sigma
    rng = random.Random(42)
    for _ in range(100):
        winner, loser = (a, b) if rng.random() < 0.7 else (b, a)
        _run_match(rater, winner, loser)
    assert a.rating.sigma < sigma_initial
    assert a.rating.sigma < 5.0


def test_stronger_player_has_higher_mu_long_run():
    rater = TrueSkillRater()
    strong = Player(id="strong", rating=rater.new_rating())
    weak = Player(id="weak", rating=rater.new_rating())
    # Strong wins 90% of the time.
    rng = random.Random(7)
    for _ in range(200):
        if rng.random() < 0.9:
            _run_match(rater, strong, weak)
        else:
            _run_match(rater, weak, strong)
    assert strong.rating.mu > weak.rating.mu + 5.0


def test_expected_score_in_zero_one():
    rater = TrueSkillRater()
    a = Player(id="a", rating=rater.new_rating())
    b = Player(id="b", rating=rater.new_rating())
    p = rater.expected_score([a], [b])
    assert 0.4 <= p <= 0.6  # symmetric priors.
