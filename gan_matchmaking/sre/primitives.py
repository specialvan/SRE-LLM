"""Reusable SRE control primitives extracted from the nine GAN mechanisms.

The project started from matchmaking / rating / decision algorithms. This
catalog names the engineering capability each mechanism contributes so other
SRE loops can reuse the same pattern without inheriting the game vocabulary.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class ControlPrimitive:
    mechanism: str
    capability: str
    pattern: str
    runtime_stage: str
    code_refs: Tuple[str, ...]
    inputs: Tuple[str, ...]
    outputs: Tuple[str, ...]
    production_status: str
    compounding_use: str


CONTROL_PRIMITIVES: Tuple[ControlPrimitive, ...] = (
    ControlPrimitive(
        mechanism="TrueSkill",
        capability="belief_state_estimator",
        pattern="Bayesian reliability belief with uncertainty carried forward",
        runtime_stage="observe_release",
        code_refs=("gan_matchmaking/trueskill.py", "gan_matchmaking/sre/self_iteration.py"),
        inputs=("release outcome", "prior mu/sigma", "streaks"),
        outputs=("updated mu", "updated sigma", "confidence lower bound"),
        production_status="production",
        compounding_use="Turns every release outcome into durable service reliability memory.",
    ),
    ControlPrimitive(
        mechanism="EOMM",
        capability="objective_aware_strategy_ranker",
        pattern="Rank actions by expected retention of the control objective",
        runtime_stage="stage.eomm",
        code_refs=("gan_matchmaking/eomm.py", "gan_matchmaking/training/retention.py"),
        inputs=("history vector", "candidate strategy features", "retention artifact"),
        outputs=("chosen candidate", "candidate scores", "artifact/fallback source"),
        production_status="mixed",
        compounding_use="Converts historical outcomes into better strategy choice over time.",
    ),
    ControlPrimitive(
        mechanism="Dynamic K",
        capability="adaptive_gain_scheduler",
        pattern="Reduce update or rollout aggressiveness as success streak grows",
        runtime_stage="stage.adjusted_probs",
        code_refs=("gan_matchmaking/dynamic_k.py",),
        inputs=("win streak", "gain bounds", "decay parameters"),
        outputs=("k factor",),
        production_status="production",
        compounding_use="Prevents good recent history from creating unbounded confidence.",
    ),
    ControlPrimitive(
        mechanism="PCA",
        capability="latent_signal_compressor",
        pattern="Compress high-dimensional telemetry into an auditable latent score",
        runtime_stage="stage.pca",
        code_refs=("gan_matchmaking/pca_hidden.py",),
        inputs=("telemetry vector", "current reliability belief"),
        outputs=("hidden norm", "fused score", "telemetry key order"),
        production_status="production",
        compounding_use="Makes noisy metrics comparable across decisions without hiding the raw trace.",
    ),
    ControlPrimitive(
        mechanism="GNN",
        capability="graph_blast_radius_scorer",
        pattern="Propagate dependency graph evidence into local risk context",
        runtime_stage="stage.synergy",
        code_refs=("gan_matchmaking/gnn_synergy.py",),
        inputs=("dependency graph", "co-release history", "node features"),
        outputs=("synergy score", "dependency count"),
        production_status="mixed",
        compounding_use="Turns repeated co-release outcomes into dependency-aware rollout judgment.",
    ),
    ControlPrimitive(
        mechanism="Handicap",
        capability="risk_adjusted_probability_scorer",
        pattern="Apply contextual penalties before converting score gaps to probabilities",
        runtime_stage="stage.adjusted_probs",
        code_refs=("gan_matchmaking/handicap.py",),
        inputs=("service rating", "candidate rating", "streak penalty"),
        outputs=("adjusted success probability",),
        production_status="production",
        compounding_use="Keeps rollout odds honest when recent behavior or blast radius changes.",
    ),
    ControlPrimitive(
        mechanism="Entropy",
        capability="information_value_gate",
        pattern="Prefer actions that still produce useful signal under uncertainty",
        runtime_stage="stage.entropy",
        code_refs=("gan_matchmaking/entropy_match.py",),
        inputs=("candidate probabilities", "minimum entropy"),
        outputs=("acceptable candidate indexes", "fallback marker"),
        production_status="production",
        compounding_use="Avoids spending canary or shadow capacity on tests that cannot teach the loop.",
    ),
    ControlPrimitive(
        mechanism="Cox Survival",
        capability="time_to_incident_forecaster",
        pattern="Estimate probability of an adverse event within a fixed horizon",
        runtime_stage="stage.risk",
        code_refs=("gan_matchmaking/survival.py", "gan_matchmaking/training/cox.py"),
        inputs=("risk feature vector", "horizon", "Cox artifact"),
        outputs=("incident probability", "risk level"),
        production_status="mixed",
        compounding_use="Turns release observations into an explicit forecast gate for GO/CANARY/HOLD.",
    ),
    ControlPrimitive(
        mechanism="Minimax BP",
        capability="adversarial_policy_arbitrator",
        pattern="Resolve competing objectives by optimizing against worst-case response",
        runtime_stage="auxiliary",
        code_refs=("gan_matchmaking/minimax_bp.py",),
        inputs=("payoff matrix", "objective weights"),
        outputs=("mixed strategy", "game value"),
        production_status="research",
        compounding_use="Gives a future policy layer a disciplined way to balance feature velocity and SLO loss.",
    ),
)


def list_control_primitives() -> Tuple[ControlPrimitive, ...]:
    """Return the stable nine-mechanism primitive catalog."""
    return CONTROL_PRIMITIVES


def primitive_by_mechanism(mechanism: str) -> ControlPrimitive:
    """Find one primitive by mechanism name."""
    normalized = mechanism.strip().lower()
    for primitive in CONTROL_PRIMITIVES:
        if primitive.mechanism.lower() == normalized:
            return primitive
    raise KeyError(mechanism)
