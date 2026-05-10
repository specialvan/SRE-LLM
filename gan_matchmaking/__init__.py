"""gan_matchmaking — engineering implementation of the "Honor of Kings GAN mechanism" article.

Modules mirror the nine mathematical mechanisms described in the article:

- ``trueskill``      — §1 Bayesian skill rating  ``s ~ N(mu, sigma^2)``
- ``eomm``           — §2 Engagement-optimized matchmaking ``max E[P(Retain|M,H_t)]``
- ``dynamic_k``      — §3 Dynamic K-factor       ``K = Kmax / (1 + e^{-lam(streak-theta)})``
- ``pca_hidden``     — §4 PCA hidden score       ``X^T X v = lam v``
- ``gnn_synergy``    — §5 GNN synergy graph      ``h^{l+1} = ReLU(Wh + sum Wij hj)``
- ``handicap``       — §6 Handicap Elo           ``E_A = 1/(1+10^{(dR+Penalty)/400})``
- ``entropy_match``  — §7 Information entropy    ``max H = -sum p log2 p``
- ``survival``       — §8 Survival analysis      ``h(t|X) = h0(t) exp(beta^T X)``
- ``minimax_bp``     — §9 Minimax BP game        ``min_y max_x U = max_x min_y U``
- ``pipeline``       — end-to-end "gan" pipeline (game-world demo)
- ``core``           — cross-cutting infrastructure (config, logging, metrics, …)
- ``sre``            — SRE-vocabulary domain layer + self-iteration pipeline
"""

from .types import Player, MatchResult, MatchConfig, Rating
from .trueskill import TrueSkillRater
from .eomm import EOMMMatcher, RetentionModel
from .dynamic_k import DynamicK
from .pca_hidden import HiddenScoreExtractor
from .gnn_synergy import SynergyGraph, SynergyGNN
from .handicap import HandicapElo
from .entropy_match import EntropyMatcher
from .survival import CoxModel, ChurnRiskMonitor
from .minimax_bp import zero_sum_nash, BPSession
from .pipeline import GanPipeline

from . import core  # noqa: F401  (exposed for downstream consumers)
from . import sre   # noqa: F401
from . import persistence  # noqa: F401

__all__ = [
    "Player", "MatchResult", "MatchConfig", "Rating",
    "TrueSkillRater",
    "EOMMMatcher", "RetentionModel",
    "DynamicK",
    "HiddenScoreExtractor",
    "SynergyGraph", "SynergyGNN",
    "HandicapElo",
    "EntropyMatcher",
    "CoxModel", "ChurnRiskMonitor",
    "zero_sum_nash", "BPSession",
    "GanPipeline",
    "core", "sre",
]

__version__ = "0.2.0"
