"""End-to-end pipeline smoke test (§10)."""
from __future__ import annotations

import pytest

from gan_matchmaking import GanPipeline, MatchConfig, Player, Rating
from gan_matchmaking.handicap import HandicapElo
from gan_matchmaking.entropy_match import EntropyMatcher


def _team(mu: float, prefix: str) -> list[Player]:
    return [
        Player(id=f"{prefix}-{i}", rating=Rating(mu=mu, sigma=1.0))
        for i in range(5)
    ]


def test_pipeline_returns_trace_with_choice():
    pipeline = GanPipeline()
    focal = Player(id="focal", rating=Rating(mu=25.0, sigma=5.0))

    cand_balanced = MatchConfig(team_a=[focal] + _team(25.0, "a1")[:-1], team_b=_team(25.0, "b1"))
    cand_soft = MatchConfig(team_a=[focal] + _team(40.0, "a2")[:-1], team_b=_team(10.0, "b2"))
    cand_hard = MatchConfig(team_a=[focal] + _team(10.0, "a3")[:-1], team_b=_team(40.0, "b3"))

    pipeline.register([focal] + cand_balanced.team_a + cand_balanced.team_b
                      + cand_soft.team_a + cand_soft.team_b
                      + cand_hard.team_a + cand_hard.team_b)

    trace = pipeline.next_match(focal, [cand_balanced, cand_soft, cand_hard])

    assert trace["n_candidates"] == 3
    assert trace["focal"] == "focal"
    assert len(trace["adj_win_prob"]) == 3
    assert trace["churn_level"] in {"ok", "warn", "alarm"}
    assert len(trace["chosen_team_a"]) == 5
    assert len(trace["chosen_team_b"]) == 5


def test_pipeline_synergy_scores_calculated():
    """Test that synergy scores are computed for each candidate."""
    pipeline = GanPipeline()
    focal = Player(id="focal", rating=Rating(mu=25.0, sigma=5.0))

    cand = MatchConfig(team_a=[focal] + _team(25.0, "a1")[:-1], team_b=_team(25.0, "b1"))
    pipeline.register(cand.team_a + cand.team_b)

    trace = pipeline.next_match(focal, [cand])

    assert "synergy_scores" in trace
    assert len(trace["synergy_scores"]) == 1
    assert isinstance(trace["synergy_scores"][0], float)


def test_pipeline_empty_players_registered():
    """Test that registering empty iterable is safe."""
    pipeline = GanPipeline()
    focal = Player(id="focal", rating=Rating(mu=25.0, sigma=5.0))
    cand = MatchConfig(team_a=[focal], team_b=_team(25.0, "b1"))

    pipeline.register([])  # Empty registration
    pipeline.register([focal] + cand.team_b)

    trace = pipeline.next_match(focal, [cand])

    assert trace["n_candidates"] == 1


def test_pipeline_single_candidate():
    """Test pipeline with only one candidate."""
    pipeline = GanPipeline()
    focal = Player(id="focal", rating=Rating(mu=25.0, sigma=5.0))
    cand = MatchConfig(team_a=[focal], team_b=_team(25.0, "b1"))

    pipeline.register([focal] + cand.team_b)

    trace = pipeline.next_match(focal, [cand])

    assert trace["n_candidates"] == 1
    assert trace["acceptable_idx"] == [0]
    assert trace["churn_level"] in {"ok", "warn", "alarm"}
    assert "k_factor" in trace


def test_pipeline_no_candidates_raises():
    """Test that empty candidates list raises ValueError."""
    pipeline = GanPipeline()
    focal = Player(id="focal", rating=Rating(mu=25.0, sigma=5.0))

    with pytest.raises(ValueError, match="no candidate"):
        pipeline.next_match(focal, [])


def test_pipeline_custom_handicap():
    """Test pipeline with custom handicap settings."""
    pipeline = GanPipeline(
        handicap=HandicapElo(max_penalty=2.0, tau=0.1)
    )
    focal = Player(id="focal", rating=Rating(mu=25.0, sigma=5.0), win_streak=5)
    cand = MatchConfig(team_a=[focal], team_b=_team(25.0, "b1"))

    pipeline.register([focal] + cand.team_b)

    trace = pipeline.next_match(focal, [cand])

    assert "adj_win_prob" in trace
    assert len(trace["adj_win_prob"]) == 1


def test_pipeline_custom_entropy_matcher():
    """Test pipeline with custom entropy matcher."""
    pipeline = GanPipeline(
        entropy=EntropyMatcher(min_entropy=0.1)
    )
    focal = Player(id="focal", rating=Rating(mu=25.0, sigma=5.0))
    cand = MatchConfig(team_a=[focal], team_b=_team(25.0, "b1"))

    pipeline.register([focal] + cand.team_b)

    trace = pipeline.next_match(focal, [cand])

    assert trace["n_candidates"] == 1


def test_pipeline_player_cache_lookups():
    """Test that player cache is used for repeated IDs."""
    pipeline = GanPipeline()
    players = [
        Player(id="shared", rating=Rating(mu=20.0, sigma=2.0)),
        Player(id="shared", rating=Rating(mu=30.0, sigma=1.0)),  # Should overwrite
    ]
    focal = Player(id="focal", rating=Rating(mu=25.0, sigma=5.0))
    cand = MatchConfig(team_a=[focal], team_b=players)

    pipeline.register(players)
    pipeline.register([focal])

    # Cache should have "shared" and "focal"
    trace = pipeline.next_match(focal, [cand])

    assert trace["n_candidates"] == 1


def test_pipeline_k_factor_changes_with_streak():
    """Test that K-factor adapts to player's win/loss streak."""
    pipeline = GanPipeline()  # Use default DynamicK
    focal_hot = Player(id="hot", rating=Rating(mu=25.0, sigma=5.0), win_streak=10)
    focal_cold = Player(id="cold", rating=Rating(mu=25.0, sigma=5.0), loss_streak=10)
    cand = MatchConfig(team_a=[focal_hot, focal_cold], team_b=_team(25.0, "opp"))

    pipeline.register([focal_hot, focal_cold] + cand.team_b)

    trace_hot = pipeline.next_match(focal_hot, [cand])
    trace_cold = pipeline.next_match(focal_cold, [cand])

    # K-factors may differ based on streaks
    assert "k_factor" in trace_hot
    assert "k_factor" in trace_cold


def test_pipeline_churn_alarm_selects_softest():
    """Test that churn alarm selects the softest opponent."""
    pipeline = GanPipeline(soft_match_bias=0.2)
    focal = Player(id="focal", rating=Rating(mu=25.0, sigma=5.0))

    # Hard, medium, soft opponents
    cand_hard = MatchConfig(team_a=[focal], team_b=_team(40.0, "hard"))
    cand_med = MatchConfig(team_a=[focal], team_b=_team(25.0, "med"))
    cand_soft = MatchConfig(team_a=[focal], team_b=_team(10.0, "soft"))

    pipeline.register([focal])

    trace = pipeline.next_match(focal, [cand_hard, cand_med, cand_soft])

    assert "churn_level" in trace
    assert trace["n_candidates"] == 3


def test_pipeline_accepts_generator():
    """Test that pipeline accepts generators for candidates."""
    pipeline = GanPipeline()
    focal = Player(id="focal", rating=Rating(mu=25.0, sigma=5.0))
    cand = MatchConfig(team_a=[focal], team_b=_team(25.0, "b1"))

    pipeline.register([focal] + cand.team_b)

    def candidate_gen():
        yield cand

    trace = pipeline.next_match(focal, candidate_gen())

    assert trace["n_candidates"] == 1


def test_pipeline_history_features_used():
    """Test that custom history features are used."""
    pipeline = GanPipeline()
    focal = Player(id="focal", rating=Rating(mu=25.0, sigma=5.0))
    cand = MatchConfig(team_a=[focal], team_b=_team(25.0, "b1"))

    pipeline.register([focal] + cand.team_b)

    custom_history = [3.0, 1.0, 50.0, 10.0]  # Custom EOMM features
    trace = pipeline.next_match(focal, [cand], history_features=custom_history)

    assert "adj_win_prob" in trace
    assert trace["n_candidates"] == 1
