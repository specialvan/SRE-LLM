"""End-to-end demo: run the "gan pipeline" once on synthetic data.

Usage (from the ``gan/`` directory):

    python -m examples.demo_pipeline

It will print a trace dict per candidate match and also dump it to ``trace.jsonl``.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from gan_matchmaking import (
    GanPipeline,
    MatchConfig,
    Player,
    Rating,
    TrueSkillRater,
)
from gan_matchmaking.gnn_synergy import SynergyGraph


def _team(mu: float, sigma: float, n: int, prefix: str) -> list[Player]:
    return [
        Player(id=f"{prefix}-{i}", rating=Rating(mu=mu, sigma=sigma))
        for i in range(n)
    ]


def _play_some_matches(rater: TrueSkillRater, players: list[Player],
                       synergy: "SynergyGraph", n: int = 50) -> None:
    rng = random.Random(0)
    for _ in range(n):
        shuffled = list(players)
        rng.shuffle(shuffled)
        team_a = shuffled[:5]
        team_b = shuffled[5:10]
        # Probability team A wins proportional to their mu diff.
        mu_a = sum(p.rating.mu for p in team_a)
        mu_b = sum(p.rating.mu for p in team_b)
        p_a = 1.0 / (1.0 + 10.0 ** ((mu_b - mu_a) / 60.0))
        a_wins = rng.random() < p_a
        rater.update(team_a, team_b, 1.0 if a_wins else 0.0)
        synergy.add_match([p.id for p in team_a], win=a_wins)
        synergy.add_match([p.id for p in team_b], win=not a_wins)


def main() -> None:
    pipeline = GanPipeline()
    rater = pipeline.rater

    # Synthesise a small player pool with varied initial skill.
    pool = (
        _team(30.0, 8.0 / 3.0, 5, "pro")
        + _team(25.0, 8.0 / 3.0, 5, "mid")
        + _team(20.0, 8.0 / 3.0, 5, "new")
    )
    _play_some_matches(rater, pool, pipeline.synergy_graph, n=80)

    focal = pool[0]
    focal.win_streak = 6  # pretend they're on a streak.
    focal.total_matches = 30

    # Build three candidate configurations for the next match.
    cand_balanced = MatchConfig(
        team_a=[focal] + pool[1:5],
        team_b=pool[5:10],
    )
    cand_soft = MatchConfig(
        team_a=[focal] + pool[10:14],
        team_b=pool[5:9],
    )
    cand_hard = MatchConfig(
        team_a=[focal] + pool[10:14],
        team_b=pool[1:5],
    )
    candidates = [cand_balanced, cand_soft, cand_hard]

    pipeline.register(pool)

    trace = pipeline.next_match(focal, candidates)

    print("=== Pipeline trace ===")
    print(json.dumps(trace, indent=2, ensure_ascii=False))

    out_path = Path(__file__).with_name("trace.jsonl")
    out_path.write_text(json.dumps(trace, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nTrace written to {out_path}")


if __name__ == "__main__":
    main()
