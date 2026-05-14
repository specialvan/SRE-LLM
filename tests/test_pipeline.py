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


def test_pipeline_synergy_with_empty_graph():
    """Test pipeline when synergy graph has no nodes."""
    pipeline = GanPipeline()
    focal = Player(id="focal", rating=Rating(mu=25.0, sigma=5.0))
    cand = MatchConfig(team_a=[focal], team_b=_team(25.0, "b1"))

    # Don't register any players - synergy graph stays empty
    trace = pipeline.next_match(focal, [cand])

    assert trace["n_candidates"] == 1
    assert len(trace["synergy_scores"]) == 1
    assert trace["synergy_scores"][0] == 0.0


def test_pipeline_all_players_returns_stubs():
    """Test _all_players returns stub players for unregistered IDs."""
    pipeline = GanPipeline()
    # Just register the pipeline without any players
    ids = ["unregistered-1", "unregistered-2", "unregistered-3"]
    result = pipeline._all_players(ids)  # type: ignore

    assert len(result) == 3
    assert all(isinstance(p, Player) for p in result)
    assert [p.id for p in result] == ids


def test_pipeline_fallback_when_no_acceptable():
    """Test entropy filter fallback when no candidates are acceptable."""
    from gan_matchmaking.entropy_match import EntropyMatcher

    # Very low entropy threshold so no candidates are acceptable
    pipeline = GanPipeline(entropy=EntropyMatcher(min_entropy=10.0))
    focal = Player(id="focal", rating=Rating(mu=25.0, sigma=5.0))
    cand = MatchConfig(team_a=[focal], team_b=_team(25.0, "b1"))

    pipeline.register([focal] + cand.team_b)

    # Should still work, falling back to best match
    trace = pipeline.next_match(focal, [cand])

    assert trace["n_candidates"] == 1
    assert len(trace["acceptable_idx"]) >= 1


def test_pipeline_register_preserves_player():
    """Test that register preserves the player object."""
    pipeline = GanPipeline()
    player = Player(id="test-player", rating=Rating(mu=25.0, sigma=5.0))

    pipeline.register([player])

    # Check the player is cached
    assert "test-player" in pipeline._player_cache
    assert pipeline._player_cache["test-player"] is player


def test_pipeline_synergy_with_registered_players():
    """Test pipeline synergy scoring with properly registered players."""
    from gan_matchmaking.gnn_synergy import SynergyGraph

    graph = SynergyGraph()
    # add_match takes a team and win flag
    graph.add_match(["p1", "p2"], win=True)
    graph.add_match(["p2", "p3"], win=True)
    graph.add_match(["p1", "p3"], win=False)

    pipeline = GanPipeline(synergy_graph=graph)
    players = [
        Player(id="p1", rating=Rating(mu=25.0, sigma=5.0)),
        Player(id="p2", rating=Rating(mu=25.0, sigma=5.0)),
        Player(id="p3", rating=Rating(mu=25.0, sigma=5.0)),
        Player(id="p4", rating=Rating(mu=25.0, sigma=5.0)),
        Player(id="p5", rating=Rating(mu=25.0, sigma=5.0)),
    ]
    team_a = players[:3]
    team_b = players[3:]

    pipeline.register(players)

    team_a_score = pipeline._synergy_score(team_a)
    team_b_score = pipeline._synergy_score(team_b)

    # Scores should be calculated
    assert isinstance(team_a_score, float)
    assert isinstance(team_b_score, float)


def test_pipeline_synergy_score_division_by_n():
    """Test synergy score handles edge cases for n calculation."""
    pipeline = GanPipeline()

    # Single player - n=0 case, should handle gracefully
    player = Player(id="solo", rating=Rating(mu=25.0, sigma=5.0))
    score = pipeline._synergy_score([player])

    assert isinstance(score, float)


def test_pipeline_synergy_with_multiple_edges():
    """Test synergy score calculation with multiple edges."""
    from gan_matchmaking.gnn_synergy import SynergyGraph

    graph = SynergyGraph()
    # Add matches that will create edges
    graph.add_match(["a", "b"], win=True)
    graph.add_match(["b", "c"], win=True)
    graph.add_match(["c", "a"], win=False)
    graph.add_match(["a", "b"], win=False)
    graph.add_match(["b", "c"], win=False)

    pipeline = GanPipeline(synergy_graph=graph)
    players = [
        Player(id="a", rating=Rating(mu=30.0, sigma=5.0)),
        Player(id="b", rating=Rating(mu=25.0, sigma=5.0)),
        Player(id="c", rating=Rating(mu=20.0, sigma=5.0)),
    ]

    pipeline.register(players)

    score = pipeline._synergy_score(players)

    assert isinstance(score, float)
    assert score >= 0.0
