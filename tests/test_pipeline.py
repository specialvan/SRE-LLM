"""End-to-end pipeline smoke test (§10)."""
from __future__ import annotations

from gan_matchmaking import GanPipeline, MatchConfig, Player, Rating


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
