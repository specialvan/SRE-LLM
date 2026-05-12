"""Tests for :class:`ExplorationBiasScheduler` (PR-022)."""

from __future__ import annotations

import math

import pytest

from attention_residuals.skill.policy_skill.explore import (
    ExplorationBiasScheduler,
    ExploreConfig,
)


def test_protection_window_keeps_beta_at_beta0() -> None:
    sch = ExplorationBiasScheduler(
        ExploreConfig(beta0=0.5, min_protection_uses=5, global_budget=100)
    )
    for _ in range(5):
        sch.notify_used("s")
    assert math.isclose(sch.raw_beta("s"), 0.5)


def test_beta_decays_after_protection() -> None:
    sch = ExplorationBiasScheduler(
        ExploreConfig(beta0=1.0, min_protection_uses=5, global_budget=100)
    )
    for _ in range(15):
        sch.notify_used("s")
    # n=15, decay divisor = sqrt(max(1, 15-5)) = sqrt(10).
    assert math.isclose(sch.raw_beta("s"), 1.0 / math.sqrt(10), rel_tol=1e-6)


def test_global_budget_scales_proportionally() -> None:
    sch = ExplorationBiasScheduler(
        ExploreConfig(beta0=1.0, min_protection_uses=0, global_budget=1.0)
    )
    # Three skills immediately past protection with similar β.
    for sid in ("a", "b", "c"):
        for _ in range(5):
            sch.notify_used(sid)
    snap = sch.snapshot()
    total = sum(snap.values())
    assert total <= 1.0 + 1e-9
    # All three skills should shrink proportionally; nobody monopolises.
    values = list(snap.values())
    assert max(values) - min(values) < 1e-6


def test_snapshot_respects_budget_when_total_low() -> None:
    sch = ExplorationBiasScheduler(
        ExploreConfig(beta0=0.1, min_protection_uses=0, global_budget=10.0)
    )
    sch.notify_used("s1")
    snap = sch.snapshot()
    # Total β for one skill with β0=0.1 and n=1 is small; budget huge.
    assert abs(snap["s1"] - 0.1) < 1e-9


def test_forget_clears_state() -> None:
    sch = ExplorationBiasScheduler()
    sch.notify_used("s")
    sch.forget("s")
    assert len(sch) == 0
    assert sch.raw_beta("s") == sch.default_beta()


def test_rejects_bad_config() -> None:
    with pytest.raises(ValueError):
        ExplorationBiasScheduler(ExploreConfig(beta0=-0.1))
    with pytest.raises(ValueError):
        ExplorationBiasScheduler(ExploreConfig(min_protection_uses=-1))
    with pytest.raises(ValueError):
        ExplorationBiasScheduler(ExploreConfig(global_budget=0))


def test_zero_beta_config_is_noop() -> None:
    sch = ExplorationBiasScheduler(
        ExploreConfig(beta0=0.0, min_protection_uses=0, global_budget=1.0)
    )
    sch.notify_used("s")
    assert sch.raw_beta("s") == 0.0
    assert sch.effective_beta("s") == 0.0
