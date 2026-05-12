"""M2 · online routing integration.

End-to-end: bank + retriever + utility tracker + explore + router ·
simulating an online loop where a **good** skill is rewarded (high
utility) and a **bad** skill is punished, and verifying that the
router's pick distribution gradually shifts toward the good skill.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from attention_residuals.sre_math import TemporalCreditAssigner
from attention_residuals.skill.policy_skill import (
    DualGranularitySkillBank,
    ExplorationBiasScheduler,
    ExploreConfig,
    HindsightConfig,
    HindsightUtilityTracker,
    RetrieverConfig,
    RouterConfig,
    SkillRouter,
    StepSkill,
    UtilityAwareRetriever,
)
from attention_residuals.skill.types import (
    Granularity,
    PatchField,
    PatchTarget,
)


def _unit(*vals: float) -> np.ndarray:
    arr = np.array(vals, dtype=np.float32)
    return arr / (np.linalg.norm(arr) + 1e-9)


def _mk_step(sid: str) -> StepSkill:
    return StepSkill(
        skill_id=sid,
        targets=(PatchTarget("a", PatchField.BIAS, 0.1),),
    )


def _build_stack():
    bank = DualGranularitySkillBank()
    retriever = UtilityAwareRetriever(
        dim=2,
        config=RetrieverConfig(lambda_util=1.0, lambda_explore=0.1),
    )
    utility = HindsightUtilityTracker(
        HindsightConfig(alpha_ema=0.4, min_uses_for_judgment=5)
    )
    explore = ExplorationBiasScheduler(
        ExploreConfig(beta0=0.5, min_protection_uses=3, global_budget=10.0)
    )
    router = SkillRouter(
        bank=bank,
        retriever=retriever,
        utility=utility,
        explore=explore,
        config=RouterConfig(default_top_k=1),
    )
    # Two skills with very similar embeddings (sim nearly equal).
    bank.put_step(_mk_step("good"))
    bank.put_step(_mk_step("bad"))
    retriever.upsert("good", _unit(1, 0.01))
    retriever.upsert("bad", _unit(1, 0.0))
    return bank, retriever, utility, explore, router


def test_utility_shifts_pick_distribution_toward_good() -> None:
    _bank, _retriever, utility, _explore, router = _build_stack()

    # Training phase: feed observations so utility("good") >> utility("bad").
    for step in range(1, 40):
        utility.observe("good", m_with=1.0, m_without=0.2, step=step)
        utility.observe("bad", m_with=0.3, m_without=0.4, step=step)

    # Run 200 picks; count how often each skill wins top-1.
    query = _unit(1, 0)
    counts = {"good": 0, "bad": 0}
    for _ in range(200):
        d = router.pick(query, top_k=1)
        if d:
            counts[d[0].skill_id] += 1
    # With tied sim + utility dominating, "good" should win most picks.
    assert counts["good"] > counts["bad"]
    assert counts["good"] > 150


def test_router_pick_updates_explore_budget() -> None:
    _bank, _retriever, _utility, explore, router = _build_stack()
    query = _unit(1, 0)
    for _ in range(10):
        router.pick(query, top_k=1)
    snap = explore.snapshot()
    # At least one of the two skills must have been used.
    assert sum(snap.values()) > 0
    assert sum(v for k, v in explore._uses.items()) == 10  # type: ignore[attr-defined]


def test_tca_skill_attribution_end_to_end() -> None:
    """Feed a losing skill through the tracker; TCA exposes it via
    attribute_skill exactly as an incident-reviewer would read it."""
    tca = TemporalCreditAssigner(decay=0.95)
    tracker = HindsightUtilityTracker(
        HindsightConfig(alpha_ema=0.5, clip_delta=2.0),
        tca=tca,
    )
    for step in range(1, 30):
        tracker.observe(
            "guilty",
            m_with=0.0,
            m_without=1.0,
            step=step,
            signals=[("cost", 0.9), ("error_budget", 0.1)],
            context={"tenant": 1.0},
        )
    entries = tca.attribute_skill(incident_tick=29, window=20, top_k=5)
    assert entries
    # The top-scored entry should be the guilty skill-cost pair.
    assert entries[0].signal_name == "skill:guilty|signal:cost"
    assert entries[0].loss > 0


def test_query_granularity_filters_tasks_out_of_picks() -> None:
    """Router currently routes only STEP skills; TASK skills should not
    clobber picks even if registered in the bank."""
    bank, retriever, _utility, _explore, router = _build_stack()
    # Register a task skill; it must NOT appear in pick() results.
    from attention_residuals.skill.policy_skill.bank import TaskSkill

    bank.put_task(TaskSkill("task-x", horizon_ticks=60, objective_template="min p99"))
    query = _unit(1, 0)
    decisions = router.pick(query, top_k=3)
    assert all(d.granularity is Granularity.STEP for d in decisions)
    assert all(d.skill_id != "task-x" for d in decisions)
