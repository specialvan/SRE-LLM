"""Tests for :class:`HindsightUtilityTracker` (PR-019) and TCA extension."""

from __future__ import annotations

import math

import numpy as np
import pytest

from attention_residuals.sre_math import TemporalCreditAssigner
from attention_residuals.skill.policy_skill.utility_tracker import (
    HindsightConfig,
    HindsightUtilityTracker,
    UtilitySnapshot,
)


# -----------------------------------------------------------------------------
# EMA convergence (Def 3)
# -----------------------------------------------------------------------------


def test_observe_converges_to_positive_delta() -> None:
    tracker = HindsightUtilityTracker(
        HindsightConfig(alpha_ema=0.2, clip_delta=2.0)
    )
    for step in range(1, 200):
        tracker.observe("good", m_with=1.2, m_without=0.2, step=step)
    snap = tracker.snapshot("good")
    # α=0.2, constant delta=+1 ⇒ u_ema → 1.0 exponentially.
    assert abs(snap.utility_ema - 1.0) < 0.05
    assert snap.n_observed == 199


def test_observe_converges_to_negative_delta() -> None:
    tracker = HindsightUtilityTracker(HindsightConfig(alpha_ema=0.2))
    for step in range(1, 200):
        tracker.observe("bad", m_with=0.1, m_without=0.9, step=step)
    snap = tracker.snapshot("bad")
    assert snap.utility_ema < -0.5


def test_clip_delta_prevents_blow_up() -> None:
    tracker = HindsightUtilityTracker(
        HindsightConfig(alpha_ema=1.0, clip_delta=2.0)
    )
    # Massive single observation; α=1 means utility = clipped delta.
    tracker.observe("ouch", m_with=100.0, m_without=0.0, step=1)
    assert tracker.snapshot("ouch").utility_ema == 2.0  # clamped


# -----------------------------------------------------------------------------
# Same-stream invariant (REQ-RTE-009)
# -----------------------------------------------------------------------------


def test_req_rte_009_monotonic_step_required() -> None:
    tracker = HindsightUtilityTracker(HindsightConfig(alpha_ema=0.1))
    tracker.observe("s", m_with=1.0, m_without=0.0, step=10)
    with pytest.raises(ValueError, match="precedes"):
        tracker.observe("s", m_with=1.0, m_without=0.0, step=5)


def test_strict_same_stream_can_be_disabled() -> None:
    tracker = HindsightUtilityTracker(
        HindsightConfig(alpha_ema=0.1, strict_same_stream=False)
    )
    tracker.observe("s", m_with=1.0, m_without=0.0, step=10)
    tracker.observe("s", m_with=1.0, m_without=0.0, step=5)  # no raise


# -----------------------------------------------------------------------------
# Confidence warmup
# -----------------------------------------------------------------------------


def test_confidence_gated_by_min_uses() -> None:
    tracker = HindsightUtilityTracker(
        HindsightConfig(min_uses_for_judgment=5)
    )
    for i in range(3):
        tracker.observe("s", 1.0, 0.5, step=i + 1)
    assert tracker.snapshot("s").confidence == 0.0
    # Ramp past the floor.
    for i in range(3, 80):
        tracker.observe("s", 1.0, 0.5, step=i + 1)
    snap = tracker.snapshot("s")
    assert snap.confidence > 0.5


def test_empty_snapshot_is_safe() -> None:
    tracker = HindsightUtilityTracker()
    snap = tracker.snapshot("never-seen")
    assert isinstance(snap, UtilitySnapshot)
    assert snap.n_observed == 0
    assert snap.utility_ema == 0.0
    assert snap.confidence == 0.0


# -----------------------------------------------------------------------------
# Input validation
# -----------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_observation_rejected(bad: float) -> None:
    tracker = HindsightUtilityTracker()
    with pytest.raises(ValueError):
        tracker.observe("s", bad, 0.0, step=1)


def test_empty_skill_id_rejected() -> None:
    tracker = HindsightUtilityTracker()
    with pytest.raises(ValueError):
        tracker.observe("", 1.0, 0.5, step=1)


# -----------------------------------------------------------------------------
# TCA integration (ADR-002)
# -----------------------------------------------------------------------------


def test_tca_record_skill_and_attribute_skill() -> None:
    tca = TemporalCreditAssigner(decay=0.9)
    # Record two ordinary signal entries and one skill entry at tick 10.
    tca.record(
        tick=10,
        weights=np.array([0.3, 0.7]),
        losses=np.array([1.0, 2.0]),
        signal_names=["p99", "cost"],
    )
    tca.record_skill(
        tick=10,
        skill_id="boost-budget",
        signals=[("error_budget", 0.8), ("cost", 0.2)],
        loss=1.5,
    )
    all_entries = tca.attribute(incident_tick=10, window=10)
    assert len(all_entries) == 4  # 2 signal + 2 skill-signal
    skill_entries = tca.attribute_skill(incident_tick=10, window=10)
    assert all(e.signal_name.startswith("skill:boost-budget|") for e in skill_entries)


def test_utility_tracker_forwards_to_tca_as_loss() -> None:
    tca = TemporalCreditAssigner(decay=0.95)
    tracker = HindsightUtilityTracker(
        HindsightConfig(alpha_ema=0.5, clip_delta=2.0),
        tca=tca,
    )
    # Bad skill (utility turns negative) → should register loss in TCA.
    tracker.observe(
        "regret",
        m_with=0.0,
        m_without=1.0,
        step=5,
        signals=[("cost", 1.0)],
    )
    entries = tca.attribute_skill(incident_tick=5, window=5)
    assert entries
    assert entries[0].signal_name == "skill:regret|signal:cost"
    assert entries[0].loss == 1.0   # -delta clipped to positive


def test_utility_tracker_no_loss_attributed_for_positive_utility() -> None:
    tca = TemporalCreditAssigner(decay=0.95)
    tracker = HindsightUtilityTracker(tca=tca)
    tracker.observe(
        "winner",
        m_with=1.0,
        m_without=0.0,
        step=5,
        signals=[("error_budget", 1.0)],
    )
    entries = tca.attribute_skill(incident_tick=5, window=5)
    # Positive utility ⇒ zero loss attributed ⇒ score = 0 for everything.
    assert all(e.loss == 0.0 for e in entries)


def test_utility_snapshot_reset() -> None:
    tracker = HindsightUtilityTracker(HindsightConfig(alpha_ema=0.5))
    for i in range(10):
        tracker.observe("s", 1.0, 0.0, step=i + 1)
    assert tracker.snapshot("s").n_observed == 10
    tracker.reset()
    assert tracker.snapshot("s").n_observed == 0
