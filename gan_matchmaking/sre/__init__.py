"""SRE domain mapping of the nine "gan" mechanisms.

Each submodule wraps one mechanism in SRE vocabulary and wires it to the
core infrastructure (config, logging, metrics, tracing).

============================ ===================================================
Game-world module             SRE-world mapping
============================ ===================================================
TrueSkill                    Release confidence rating (Gaussian over reliability)
PCA hidden score             Signal compression on release telemetry
GNN synergy                  Service dependency synergy (blast-radius graph)
Dynamic K                    Confidence decay for fast repeated releases
Handicap Elo                 Risk-adjusted success probability
Entropy matcher              Canary shadow entropy — was the test informative?
EOMM                         Release strategy picker (argmax retention-of-SLO)
Survival / Cox               Time-to-incident risk estimator
Minimax BP                   SLO / budget game (feature vs reliability)
============================ ===================================================

The end-to-end :class:`SelfIterationPipeline` in
``gan_matchmaking.sre.self_iteration`` is the actual "self-iterating release
decider" this project was built for.
"""

from .domain import (
    Decision,
    DecisionKind,
    ReleaseCandidate,
    ReleaseContext,
    RiskLevel,
    Service,
)
from .leases import FileLease, LeaseNotAcquiredError, LeaseRefreshLoop
from .self_iteration import SelfIterationPipeline

__all__ = [
    "Decision",
    "FileLease",
    "LeaseNotAcquiredError",
    "LeaseRefreshLoop",
    "DecisionKind",
    "ReleaseCandidate",
    "ReleaseContext",
    "RiskLevel",
    "Service",
    "SelfIterationPipeline",
]
