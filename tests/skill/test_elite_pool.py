"""Tests for :class:`ElitePool` (PR-015)."""

from __future__ import annotations

import random

import pytest

from attention_residuals.skill.governance.elite_pool import (
    Elite,
    ElitePool,
    ElitePoolConfig,
    EvictionEvent,
    MemberState,
)


# -----------------------------------------------------------------------------
# Capacity and admit flow
# -----------------------------------------------------------------------------


def test_req_vrf_005_capacity_respected_under_random_input() -> None:
    rng = random.Random(1)
    pool = ElitePool(ElitePoolConfig(capacity=8, min_probation_steps=0), rng=rng)
    for i in range(200):
        pool.try_admit(Elite(f"v{i}", score=rng.random()), step=i)
        # Graduate probations each step to keep ELITE pool actively contested.
        pool.evict_probation_breakers(step=i)
        assert len(pool) <= 8


def test_admit_into_empty_is_probation() -> None:
    pool = ElitePool(ElitePoolConfig(capacity=2))
    assert pool.try_admit(Elite("v1", score=0.5)) is None
    assert pool.member_states()["v1"] is MemberState.PROBATION


def test_weaker_candidate_rejected_when_full() -> None:
    pool = ElitePool(ElitePoolConfig(capacity=2, min_probation_steps=0))
    pool.try_admit(Elite("v1", score=0.9), step=0)
    pool.try_admit(Elite("v2", score=0.8), step=1)
    # Let them graduate.
    pool.evict_probation_breakers(step=2)
    weaker = Elite("v3", score=0.1)
    assert pool.try_admit(weaker, step=3) is None
    assert "v3" not in pool.member_states()


def test_stronger_candidate_evicts_weakest_elite() -> None:
    pool = ElitePool(ElitePoolConfig(capacity=2, min_probation_steps=0))
    pool.try_admit(Elite("v1", score=0.9), step=0)
    pool.try_admit(Elite("v2", score=0.5), step=0)
    pool.evict_probation_breakers(step=1)

    ev = pool.try_admit(Elite("v3", score=0.95), step=2)
    assert isinstance(ev, EvictionEvent)
    assert ev.evicted_id == "v2"           # weakest elite
    assert ev.replaced_by_id == "v3"
    assert "v2" not in pool.member_states()
    assert "v3" in pool.member_states()


# -----------------------------------------------------------------------------
# Probation protection (REQ-VRF-007)
# -----------------------------------------------------------------------------


def test_req_vrf_007_probation_protects_low_score() -> None:
    pool = ElitePool(ElitePoolConfig(capacity=2, min_probation_steps=10))
    pool.try_admit(Elite("elite_strong", score=0.9), step=0)
    pool.try_admit(Elite("elite_medium", score=0.5), step=0)
    # Both are in probation — strong ELITE is empty.
    assert pool.member_states()["elite_strong"] is MemberState.PROBATION
    # Incoming with higher score than the LOW-SCORING member must NOT evict
    # because there is no ELITE member to replace.
    ev = pool.try_admit(Elite("boss", score=0.99), step=3)
    assert ev is None
    # The probation members stay put until window elapses.
    assert "elite_strong" in pool.member_states()
    assert "elite_medium" in pool.member_states()


def test_probation_breaker_evicted_when_window_closes() -> None:
    pool = ElitePool(
        ElitePoolConfig(
            capacity=2, min_probation_steps=5, probation_survival_min=0.3
        )
    )
    pool.try_admit(Elite("winner", score=0.9), step=0)
    pool.try_admit(Elite("loser", score=0.1), step=0)  # below survival min
    # Before window: no evict
    assert pool.evict_probation_breakers(step=2) == []
    events = pool.evict_probation_breakers(step=6)
    ids_out = {e.evicted_id for e in events}
    assert ids_out == {"loser"}
    assert "loser" not in pool.member_states()
    # winner graduated to ELITE
    assert pool.member_states()["winner"] is MemberState.ELITE


# -----------------------------------------------------------------------------
# Drop (redundancy detector / manual evict)
# -----------------------------------------------------------------------------


def test_drop_emits_event_and_removes() -> None:
    pool = ElitePool(ElitePoolConfig(capacity=2, min_probation_steps=0))
    pool.try_admit(Elite("v1", score=0.5), step=0)
    ev = pool.drop("v1", reason="duplicate_of_v9")
    assert ev is not None and ev.evicted_id == "v1" and ev.reason == "duplicate_of_v9"
    assert pool.member_states() == {}


def test_drop_missing_is_noop() -> None:
    pool = ElitePool()
    assert pool.drop("ghost") is None


# -----------------------------------------------------------------------------
# Idempotency & inspection
# -----------------------------------------------------------------------------


def test_re_admit_is_refresh_not_duplicate() -> None:
    pool = ElitePool()
    assert pool.try_admit(Elite("v1", score=0.5)) is None
    assert pool.try_admit(Elite("v1", score=0.8)) is None  # refresh
    assert len(pool) == 1
    assert pool.member_states() == {"v1": MemberState.PROBATION}


def test_capacity_validation() -> None:
    with pytest.raises(ValueError):
        ElitePool(ElitePoolConfig(capacity=0))


def test_elite_and_probation_id_lists() -> None:
    pool = ElitePool(ElitePoolConfig(capacity=3, min_probation_steps=2))
    pool.try_admit(Elite("a", 0.6), step=0)
    pool.try_admit(Elite("b", 0.7), step=0)
    pool.try_admit(Elite("c", 0.8), step=0)
    pool.evict_probation_breakers(step=3)
    assert set(pool.elite_ids()) == {"a", "b", "c"}
    assert pool.probation_ids() == []
