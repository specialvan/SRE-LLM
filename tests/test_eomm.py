"""Tests for EOMM (§2)."""
from __future__ import annotations

import numpy as np

from gan_matchmaking import EOMMMatcher, MatchConfig, Player, Rating, RetentionModel


def _team(mu: float) -> list[Player]:
    return [Player(id=f"p{mu}-{i}", rating=Rating(mu=mu, sigma=1.0)) for i in range(5)]


def test_argmax_retention_picks_higher_prob_config():
    # Craft a retention model that rewards larger gap (team_a stronger).
    model = RetentionModel()
    # features = [h0..h3, gap, total_sigma, mu_a, mu_b]  (8 dims)
    model.weights = np.array([0, 0, 0, 0, 1.0, 0, 0, 0])
    model.bias = 0.0

    strong_vs_weak = MatchConfig(team_a=_team(40.0), team_b=_team(10.0))
    balanced = MatchConfig(team_a=_team(25.0), team_b=_team(25.0))

    matcher = EOMMMatcher(model=model, epsilon=0.0)
    chosen = matcher.best([0, 0, 0, 0], [strong_vs_weak, balanced])
    assert chosen is strong_vs_weak


def test_fit_reduces_loss():
    model = RetentionModel()
    histories = [[0.0, 0.0, 0.0, 0.0]] * 4
    cfgs = [
        MatchConfig(team_a=_team(40.0), team_b=_team(10.0)),
        MatchConfig(team_a=_team(10.0), team_b=_team(40.0)),
        MatchConfig(team_a=_team(40.0), team_b=_team(10.0)),
        MatchConfig(team_a=_team(10.0), team_b=_team(40.0)),
    ]
    retained = [1, 0, 1, 0]
    model.fit(histories, cfgs, retained, iters=500, lr=0.05)
    # After fit, positive-labelled configs should have higher prob than negatives.
    p_pos = model.prob(histories[0], cfgs[0])
    p_neg = model.prob(histories[1], cfgs[1])
    assert p_pos > p_neg
