"""Tests for :class:`UtilityAwareRetriever` (PR-021)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from attention_residuals.skill.policy_skill.retriever import (
    RetrieverConfig,
    Scored,
    UtilityAwareRetriever,
)


def _unit(*vals: float) -> np.ndarray:
    arr = np.array(vals, dtype=np.float32)
    return arr / (np.linalg.norm(arr) + 1e-9)


# -----------------------------------------------------------------------------
# sim-only (λ=0, β=0) — REQ-RTE-004
# -----------------------------------------------------------------------------


def test_req_rte_004_lambda_zero_degenerates_to_sim() -> None:
    retriever = UtilityAwareRetriever(
        dim=3,
        config=RetrieverConfig(lambda_util=0.0, lambda_explore=0.0),
    )
    retriever.upsert("a", _unit(1, 0, 0))
    retriever.upsert("b", _unit(0, 1, 0))
    scored = retriever.rank(_unit(1, 0, 0))
    assert scored[0].skill_id == "a"
    assert math.isclose(scored[0].score, scored[0].sim)


# -----------------------------------------------------------------------------
# Scoring composition — REQ-RTE-003
# -----------------------------------------------------------------------------


def test_req_rte_003_score_formula() -> None:
    retriever = UtilityAwareRetriever(
        dim=2,
        config=RetrieverConfig(lambda_util=0.5, lambda_explore=0.2),
    )
    retriever.upsert("a", _unit(1, 0))
    scored = retriever.rank(
        _unit(1, 0),
        utilities={"a": 1.0},
        exploration={"a": 1.0},
    )
    assert scored
    # sim ≈ 1.0 + 0.5 · 1.0 + 0.2 · 1.0 = 1.7
    assert math.isclose(scored[0].score, 1.7, rel_tol=1e-5)


def test_top_k_returns_only_k() -> None:
    retriever = UtilityAwareRetriever(dim=2, config=RetrieverConfig(lambda_util=0, lambda_explore=0))
    retriever.upsert("a", _unit(1, 0))
    retriever.upsert("b", _unit(0.9, 0.1))
    retriever.upsert("c", _unit(-1, 0))
    scored = retriever.rank(_unit(1, 0), top_k=2)
    assert len(scored) == 2
    # Order stable: sim-closest first.
    assert scored[0].skill_id == "a"
    assert scored[1].skill_id == "b"


def test_candidates_filter_is_respected() -> None:
    retriever = UtilityAwareRetriever(dim=2, config=RetrieverConfig(lambda_util=0, lambda_explore=0))
    retriever.upsert("a", _unit(1, 0))
    retriever.upsert("b", _unit(0, 1))
    retriever.upsert("c", _unit(1, 1))
    scored = retriever.rank(_unit(1, 0), candidates=["b", "c"])
    ids = [s.skill_id for s in scored]
    assert "a" not in ids
    assert set(ids) == {"b", "c"}


# -----------------------------------------------------------------------------
# Upsert / remove / contains (REQ-RTE-008)
# -----------------------------------------------------------------------------


def test_upsert_replaces_existing_embedding() -> None:
    retriever = UtilityAwareRetriever(dim=2)
    retriever.upsert("s", _unit(1, 0))
    retriever.upsert("s", _unit(0, 1))
    scored = retriever.rank(_unit(0, 1))
    assert scored and scored[0].skill_id == "s"
    assert math.isclose(scored[0].sim, 1.0, rel_tol=1e-5)


def test_remove_compacts_storage() -> None:
    retriever = UtilityAwareRetriever(dim=2)
    retriever.upsert("a", _unit(1, 0))
    retriever.upsert("b", _unit(0, 1))
    retriever.remove("a")
    assert not retriever.contains("a")
    assert retriever.contains("b")
    assert len(retriever) == 1


def test_empty_retriever_returns_empty_list() -> None:
    retriever = UtilityAwareRetriever(dim=2)
    assert retriever.rank(_unit(1, 0)) == []


def test_dim_mismatch_rejected() -> None:
    retriever = UtilityAwareRetriever(dim=3)
    with pytest.raises(ValueError):
        retriever.upsert("a", np.ones(2, dtype=np.float32))
    with pytest.raises(ValueError):
        retriever.rank(np.ones(2, dtype=np.float32))


def test_grows_past_initial_capacity() -> None:
    retriever = UtilityAwareRetriever(
        dim=2, config=RetrieverConfig(initial_capacity=4)
    )
    # Different angles so each embedding is distinct.
    for i in range(10):
        angle = (i + 1) / 11.0 * math.pi
        retriever.upsert(f"s{i}", _unit(math.cos(angle), math.sin(angle)))
    assert len(retriever) == 10
    # Query pointing mostly in the direction of s0 (smallest angle).
    scored = retriever.rank(
        _unit(math.cos(math.pi / 11.0), math.sin(math.pi / 11.0))
    )
    assert scored[0].skill_id == "s0"
