"""§10 End-to-end "gan" pipeline — putting all nine mechanisms together.

Flow:

    1. ``TrueSkillRater``         estimate mu, sigma
    2. ``HiddenScoreExtractor``   fuse hidden behaviour score
    3. ``SynergyGNN``             score candidate teams' synergy
    4. ``DynamicK`` + ``HandicapElo``   adjusted expected win probability
    5. ``EntropyMatcher``         keep only configs with high outcome entropy
    6. ``EOMMMatcher``            pick the config maximising retention
    7. ``ChurnRiskMonitor``       if churn risk is high, bias toward easier configs
    8. ``BPSession``              suggested BP mixed strategy (opt-in)

The pipeline returns a ``trace`` dict that is trivially serialisable to JSON.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional

import numpy as np

from .dynamic_k import DynamicK
from .entropy_match import EntropyMatcher
from .eomm import EOMMMatcher
from .handicap import HandicapElo
from .gnn_synergy import SynergyGNN, SynergyGraph
from .pca_hidden import HiddenScoreExtractor
from .survival import ChurnRiskMonitor
from .trueskill import TrueSkillRater
from .types import MatchConfig, Player


@dataclass
class GanPipeline:
    rater: TrueSkillRater = field(default_factory=TrueSkillRater)
    dynamic_k: DynamicK = field(default_factory=DynamicK)
    handicap: HandicapElo = field(default_factory=HandicapElo)
    entropy: EntropyMatcher = field(default_factory=EntropyMatcher)
    eomm: EOMMMatcher = field(default_factory=EOMMMatcher)
    churn: ChurnRiskMonitor = field(default_factory=ChurnRiskMonitor)
    synergy_graph: SynergyGraph = field(default_factory=SynergyGraph)
    synergy_gnn: SynergyGNN = field(default_factory=SynergyGNN)
    hidden: HiddenScoreExtractor = field(default_factory=lambda: HiddenScoreExtractor(n_components=2))
    # When churn level == "alarm" we prefer softer opponents for the focal player.
    soft_match_bias: float = 0.15
    _player_cache: Dict[str, Player] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _synergy_score(self, team: List[Player]) -> float:
        ids = [p.id for p in team]
        nodes, A = self.synergy_graph.adjacency()
        if not nodes or A.shape[0] == 0:
            return 0.0
        idx = {n: i for i, n in enumerate(nodes)}
        # Build feature matrix from ratings.
        feats = np.array([[p.rating.mu, p.rating.sigma] for p in self._all_players(nodes)])
        H = self.synergy_gnn.forward(feats, A)
        score = 0.0
        n = 0
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                if a in idx and b in idx:
                    score += self.synergy_gnn.synergy_score(H, idx[a], idx[b])
                    n += 1
        return score / max(n, 1)

    def _all_players(self, ids: List[str]) -> List[Player]:
        # Looks up cached player objects if we tracked them. If not, emit stubs.
        out = []
        for pid in ids:
            p = self._player_cache.get(pid)
            if p is None:
                p = Player(id=pid)
            out.append(p)
        return out

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def register(self, players: Iterable[Player]) -> None:
        for p in players:
            self._player_cache[p.id] = p

    def next_match(
        self,
        focal: Player,
        candidates: Iterable[MatchConfig],
        history_features: Optional[List[float]] = None,
    ) -> Dict:
        candidates = list(candidates)
        if not candidates:
            raise ValueError("no candidate matches provided")

        # 1 & 2: skill + hidden score already baked into focal.rating.
        # 3: synergy-aware filter — compute per-candidate synergy deltas.
        syn_scores = [self._synergy_score(c.team_a) - self._synergy_score(c.team_b)
                      for c in candidates]

        # 4: adjusted expected win probability.
        adj_probs = []
        r_focal = focal.rating.mu
        for c in candidates:
            # Rating of the *opponent* team (team_b by convention: focal on team_a).
            r_opp = sum(p.rating.mu for p in c.team_b) / max(len(c.team_b), 1)
            penalty = self.handicap.penalty(focal.win_streak, focal.loss_streak)
            e = self.handicap.expected_win(r_focal, r_opp, penalty)
            adj_probs.append(e)

        # 5: entropy filter.
        acceptable_idx = [i for i, c in enumerate(candidates)
                          if self.entropy.is_acceptable(c)]
        if not acceptable_idx:
            # fall back: pick the highest entropy.
            best = self.entropy.find_best_match(candidates)
            acceptable_idx = [candidates.index(best)] if best is not None else list(range(len(candidates)))

        # 6: EOMM retention argmax inside the acceptable set.
        history = history_features or [
            float(focal.win_streak),
            float(focal.loss_streak),
            float(focal.total_matches),
            0.0,
        ]
        sub_candidates = [candidates[i] for i in acceptable_idx]
        chosen = self.eomm.best(history, sub_candidates)

        # 7: churn monitor — if the player is at risk, soften the chosen match.
        churn_p = self.churn.predict(history)
        level = self.churn.level(churn_p)
        if level == "alarm":
            # Prefer the acceptable candidate with the lowest expected win rate for focal's *opponents*
            # (equivalently: highest expected win rate for focal).
            softest_idx = max(acceptable_idx, key=lambda i: adj_probs[i])
            chosen = candidates[softest_idx]

        # 8: K-factor for the stake of this match.
        k_now = self.dynamic_k.k(focal.win_streak)

        trace = {
            "focal": focal.id,
            "n_candidates": len(candidates),
            "synergy_scores": syn_scores,
            "adj_win_prob": adj_probs,
            "acceptable_idx": acceptable_idx,
            "chosen_team_a": [p.id for p in chosen.team_a],
            "chosen_team_b": [p.id for p in chosen.team_b],
            "churn_prob": churn_p,
            "churn_level": level,
            "k_factor": k_now,
        }
        return trace
