"""Skill router · PR-020.

Refined spec: ``skill-research/refined/PR-020-skill-router-refined.md``.

Brings together:

* :class:`DualGranularitySkillBank` — the universe of known skills;
* :class:`UtilityAwareRetriever` — scoring via sim + λ·u + β·bonus;
* :class:`HindsightUtilityTracker` — per-skill utility (read only);
* :class:`ExplorationBiasScheduler` — β bonus + "record used" feedback.

The router is the only hot-path component that has to observe all four.
It emits :class:`RoutingDecision` objects per pick and notifies the
exploration scheduler that the chosen skill was used, so β decays
monotonically.

Requirements:

* REQ-RTE-001 · return ordered list (descending score)
* REQ-RTE-002 · top_k=1 returns exactly one
* REQ-RTE-005 · rationale is always non-empty
* REQ-RTE-007 · pick p95 < 5 ms on 1k skills (via numpy buffer)
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Callable, Iterable, List, Mapping, Optional, Sequence

import numpy as np

from attention_residuals.skill.policy_skill.bank import (
    DualGranularitySkillBank,
    StepSkill,
)
from attention_residuals.skill.policy_skill.explore import (
    ExplorationBiasScheduler,
)
from attention_residuals.skill.policy_skill.retriever import (
    Scored,
    UtilityAwareRetriever,
)
from attention_residuals.skill.policy_skill.utility_tracker import (
    HindsightUtilityTracker,
)
from attention_residuals.skill.types import (
    Granularity,
    RoutingDecision,
    RoutingRationale,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class RouterConfig:
    default_top_k: int = 3
    min_confidence: float = 0.0       # reject picks below this; 0 = accept all
    confidence_temperature: float = 1.0  # softmax over final_score


class SkillRouter:
    """Orchestrates bank + retriever + utility + explore into a pick."""

    def __init__(
        self,
        bank: DualGranularitySkillBank,
        retriever: UtilityAwareRetriever,
        utility: Optional[HindsightUtilityTracker] = None,
        explore: Optional[ExplorationBiasScheduler] = None,
        config: Optional[RouterConfig] = None,
    ) -> None:
        self._bank = bank
        self._retriever = retriever
        self._utility = utility
        self._explore = explore
        self._cfg = config or RouterConfig()

    # ---------------- hot path ----------------

    def pick(
        self,
        query: np.ndarray,
        context: Optional[Mapping[str, float]] = None,
        top_k: Optional[int] = None,
        granularity: Optional[Granularity] = None,
    ) -> List[RoutingDecision]:
        """Return up to ``top_k`` ranked :class:`RoutingDecision` objects."""
        top_k = top_k if top_k is not None else self._cfg.default_top_k
        if top_k <= 0:
            return []

        # 1) candidates from bank — this also filters by trigger match.
        pairs = self._bank.query(
            granularity=granularity, trigger_match=context
        )
        if not pairs:
            return []
        # Router ranks only STEP-skill embeddings; TASK skills need a
        # different scoring surface (see PR-018 notes). We fall back to
        # only STEP until the task-skill routing branch lands.
        step_ids = [sid for sid, g in pairs if g is Granularity.STEP]
        step_ids = [sid for sid in step_ids if self._retriever.contains(sid)]
        if not step_ids:
            return []

        # 2) gather utility + explore snapshots (cheap — dict copy-views).
        utilities: Mapping[str, float] = {}
        if self._utility is not None:
            utilities = self._utility.utilities()
        exploration: Mapping[str, float] = {}
        if self._explore is not None:
            exploration = self._explore.snapshot()

        # 3) score.
        scored = self._retriever.rank(
            query=query,
            utilities=utilities,
            exploration=exploration,
            candidates=step_ids,
            top_k=top_k,
        )
        if not scored:
            return []

        # 4) confidence via softmax over final_score.
        tau = max(self._cfg.confidence_temperature, 1e-9)
        scores = np.asarray([s.score for s in scored], dtype=float)
        shifted = scores - scores.max()
        exp = np.exp(shifted / tau)
        probs = exp / exp.sum() if exp.sum() > 0 else np.full_like(exp, 1.0 / exp.size)

        # 5) build decisions + feedback.
        decisions: List[RoutingDecision] = []
        for s, prob in zip(scored, probs):
            if prob < self._cfg.min_confidence:
                continue
            step_skill = self._bank.get_step(s.skill_id)
            version = _step_version(step_skill)
            rationale = RoutingRationale(
                sim_score=s.sim,
                utility_score=self._cfg_lambda_util() * s.utility,
                exploration_bonus=self._cfg_lambda_explore() * s.explore_bonus,
                final_score=s.score,
            )
            decisions.append(
                RoutingDecision(
                    skill_id=s.skill_id,
                    version=version,
                    confidence=float(prob),
                    granularity=Granularity.STEP,
                    rationale=rationale,
                )
            )
            if self._explore is not None:
                self._explore.notify_used(s.skill_id)
        return decisions

    # ---------------- helpers ----------------

    def _cfg_lambda_util(self) -> float:
        return float(self._retriever._cfg.lambda_util)

    def _cfg_lambda_explore(self) -> float:
        return float(self._retriever._cfg.lambda_explore)


def _step_version(skill: Optional[StepSkill]) -> str:
    """Derive a stable pseudo-version for a :class:`StepSkill`.

    M2 keeps StepSkill decoupled from the version graph; when the router
    eventually reads directly from :class:`SkillRepository` this will be
    replaced with the ACTIVE head. For now we use a placeholder that is
    deterministic from content.
    """
    if skill is None:
        return "unknown"
    if not skill.targets:
        return skill.skill_id
    # Borrow compute_patch_id via the shared helper.
    from attention_residuals.skill.types import compute_patch_id

    return compute_patch_id(skill.targets, dict(skill.trigger))


__all__ = [
    "RouterConfig",
    "SkillRouter",
]
