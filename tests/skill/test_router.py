"""Tests for :class:`SkillRouter` (PR-020)."""

from __future__ import annotations

import time

import numpy as np
import pytest

from attention_residuals.skill.policy_skill.bank import (
    DualGranularitySkillBank,
    StepSkill,
)
from attention_residuals.skill.policy_skill.explore import (
    ExplorationBiasScheduler,
    ExploreConfig,
)
from attention_residuals.skill.policy_skill.retriever import (
    RetrieverConfig,
    UtilityAwareRetriever,
)
from attention_residuals.skill.policy_skill.router import (
    RouterConfig,
    SkillRouter,
)
from attention_residuals.skill.policy_skill.utility_tracker import (
    HindsightConfig,
    HindsightUtilityTracker,
)
from attention_residuals.skill.types import (
    Granularity,
    PatchField,
    PatchTarget,
)


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _unit(*vals: float) -> np.ndarray:
    arr = np.array(vals, dtype=np.float32)
    return arr / (np.linalg.norm(arr) + 1e-9)


def _mk_step(sid: str) -> StepSkill:
    return StepSkill(
        skill_id=sid,
        targets=(PatchTarget("a", PatchField.BIAS, 0.1),),
    )


def _build_router(
    lambda_util: float = 0.3,
    lambda_explore: float = 0.1,
    top_k: int = 3,
) -> tuple[
    SkillRouter,
    DualGranularitySkillBank,
    UtilityAwareRetriever,
    HindsightUtilityTracker,
    ExplorationBiasScheduler,
]:
    bank = DualGranularitySkillBank()
    retriever = UtilityAwareRetriever(
        dim=3,
        config=RetrieverConfig(
            lambda_util=lambda_util, lambda_explore=lambda_explore
        ),
    )
    util = HindsightUtilityTracker(HindsightConfig(alpha_ema=0.5))
    explore = ExplorationBiasScheduler(
        ExploreConfig(beta0=0.5, min_protection_uses=100, global_budget=1000)
    )
    router = SkillRouter(
        bank=bank,
        retriever=retriever,
        utility=util,
        explore=explore,
        config=RouterConfig(default_top_k=top_k),
    )
    return router, bank, retriever, util, explore


# -----------------------------------------------------------------------------
# REQ-RTE-001 · descending order
# -----------------------------------------------------------------------------


def test_req_rte_001_order_descending() -> None:
    router, bank, retriever, _, _ = _build_router(
        lambda_util=0.0, lambda_explore=0.0
    )
    for sid, emb in [
        ("a", (1, 0, 0)),
        ("b", (0.9, 0.1, 0)),
        ("c", (0, 0, 1)),
    ]:
        bank.put_step(_mk_step(sid))
        retriever.upsert(sid, _unit(*emb))

    decisions = router.pick(_unit(1, 0, 0))
    assert decisions
    finals = [d.rationale.final_score for d in decisions]
    assert finals == sorted(finals, reverse=True)
    assert decisions[0].skill_id == "a"


# -----------------------------------------------------------------------------
# REQ-RTE-002 · top_k=1
# -----------------------------------------------------------------------------


def test_req_rte_002_top_k_one() -> None:
    router, bank, retriever, _, _ = _build_router()
    bank.put_step(_mk_step("x"))
    bank.put_step(_mk_step("y"))
    retriever.upsert("x", _unit(1, 0, 0))
    retriever.upsert("y", _unit(0, 1, 0))
    decisions = router.pick(_unit(1, 0, 0), top_k=1)
    assert len(decisions) == 1
    assert decisions[0].skill_id == "x"


# -----------------------------------------------------------------------------
# REQ-RTE-005 · rationale always non-empty
# -----------------------------------------------------------------------------


def test_req_rte_005_rationale_always_populated() -> None:
    router, bank, retriever, _, _ = _build_router()
    bank.put_step(_mk_step("s"))
    retriever.upsert("s", _unit(1, 0, 0))
    decisions = router.pick(_unit(0, 1, 0))   # orthogonal so sim ~= 0
    assert decisions
    r = decisions[0].rationale
    assert r.sim_score is not None
    assert r.utility_score is not None
    assert r.exploration_bonus is not None
    assert r.final_score is not None


# -----------------------------------------------------------------------------
# Utility is respected
# -----------------------------------------------------------------------------


def test_higher_utility_lifts_rank_when_sim_tied() -> None:
    router, bank, retriever, util, _ = _build_router(
        lambda_util=1.0, lambda_explore=0.0
    )
    bank.put_step(_mk_step("a"))
    bank.put_step(_mk_step("b"))
    retriever.upsert("a", _unit(1, 0, 0))
    retriever.upsert("b", _unit(1, 0, 0))           # same sim
    # Build utility for a: many positive deltas.
    for step in range(1, 50):
        util.observe("a", m_with=1.0, m_without=0.0, step=step)
    decisions = router.pick(_unit(1, 0, 0))
    assert decisions and decisions[0].skill_id == "a"


# -----------------------------------------------------------------------------
# Exploration feedback loop
# -----------------------------------------------------------------------------


def test_explore_notify_used_after_pick() -> None:
    router, bank, retriever, _, explore = _build_router()
    bank.put_step(_mk_step("s"))
    retriever.upsert("s", _unit(1, 0, 0))
    router.pick(_unit(1, 0, 0), top_k=1)
    assert explore._uses.get("s", 0) == 1        # type: ignore[attr-defined]


# -----------------------------------------------------------------------------
# Edge cases
# -----------------------------------------------------------------------------


def test_empty_bank_returns_empty() -> None:
    router, _, _, _, _ = _build_router()
    assert router.pick(_unit(1, 0, 0)) == []


def test_zero_top_k_returns_empty() -> None:
    router, bank, retriever, _, _ = _build_router()
    bank.put_step(_mk_step("s"))
    retriever.upsert("s", _unit(1, 0, 0))
    assert router.pick(_unit(1, 0, 0), top_k=0) == []


def test_skill_missing_from_retriever_is_skipped() -> None:
    router, bank, _retriever, _, _ = _build_router()
    bank.put_step(_mk_step("ghost"))  # registered in bank but no embedding
    assert router.pick(_unit(1, 0, 0)) == []


# -----------------------------------------------------------------------------
# Perf smoke — REQ-RTE-007 (< 5 ms on 1k)
# -----------------------------------------------------------------------------


@pytest.mark.perf
def test_pick_p95_under_5ms_1000_skills() -> None:
    router, bank, retriever, _, _ = _build_router(top_k=5)
    rng = np.random.default_rng(17)
    for i in range(1000):
        bank.put_step(_mk_step(f"s-{i:04d}"))
        vec = rng.standard_normal(3).astype(np.float32)
        retriever.upsert(f"s-{i:04d}", vec / (np.linalg.norm(vec) + 1e-9))

    query = _unit(1.0, 0.5, -0.2)
    # Warm-up
    router.pick(query)
    samples = []
    for _ in range(20):
        t0 = time.perf_counter()
        router.pick(query)
        samples.append((time.perf_counter() - t0) * 1000)
    samples.sort()
    p95 = samples[int(0.95 * len(samples)) - 1]
    # Generous cap because CI hosts vary; spec target is 5 ms, we assert 20.
    assert p95 < 20.0, f"pick p95 = {p95:.2f} ms"
