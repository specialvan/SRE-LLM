"""Tests for :class:`Trace2SkillMiner` (PR-001)."""

from __future__ import annotations

import numpy as np
import pytest

from attention_residuals.sre_control import AuditRecord
from attention_residuals.skill.trajectory.merger import MustAttendSnapshot
from attention_residuals.skill.trajectory.miner import (
    MinerConfig,
    Trace2SkillMiner,
)
from attention_residuals.skill.types import PatchField


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


def _mk_audit(
    step: int,
    *,
    weights: list[float],
    signals: list[str],
    loss: float = 0.0,
    context: dict | None = None,
) -> AuditRecord:
    ctx = dict(context or {})
    ctx.setdefault("slo_breach", loss)
    return AuditRecord(
        step=step,
        signal_names=list(signals),
        weights=np.asarray(weights, dtype=float),
        action=np.zeros(1),
        context=ctx,
    )


# -----------------------------------------------------------------------------
# REQ-EVD-004: produce candidate when support ≥ min
# -----------------------------------------------------------------------------


def test_req_evd_004_floor_underattention_yields_candidate() -> None:
    # error_budget has registered floor 0.25 but the combiner gives it
    # only ~0.05 in high-cost records → FloorUpRule should fire.
    snapshot = MustAttendSnapshot(
        floors={"error_budget": 0.25}, registry_hash="reg-v1"
    )
    signals = ["cost", "error_budget"]
    records: list[AuditRecord] = []
    for i in range(40):
        loss = 4.0 if i < 25 else 0.2
        # Under-attended error_budget during the high-loss segment.
        w_err = 0.05 if loss > 2 else 0.4
        w_cost = 1.0 - w_err
        records.append(
            _mk_audit(i, weights=[w_cost, w_err], signals=signals, loss=loss)
        )

    miner = Trace2SkillMiner(
        config=MinerConfig(
            support_min=5, cost_quantile=0.5, cluster_k_max=1
        )
    )
    candidates = miner.mine(records, snapshot)
    assert candidates, "expected at least one candidate"
    # At least one candidate should propose error_budget.floor+
    assert any(
        any(
            t.signal_name == "error_budget" and t.field is PatchField.FLOOR and t.delta > 0
            for t in c.targets
        )
        for c in candidates
    )


# -----------------------------------------------------------------------------
# REQ-EVD-005: deterministic patch_id
# -----------------------------------------------------------------------------


def test_req_evd_005_same_input_same_patch_id() -> None:
    snapshot = MustAttendSnapshot(
        floors={"error_budget": 0.25}, registry_hash="reg-v1"
    )
    signals = ["cost", "error_budget"]
    records = [
        _mk_audit(i, weights=[0.95, 0.05], signals=signals, loss=3.0)
        for i in range(20)
    ]
    miner = Trace2SkillMiner(
        config=MinerConfig(support_min=5, cost_quantile=0.5, cluster_k_max=1)
    )
    c1 = miner.mine(records, snapshot)
    c2 = miner.mine(records, snapshot)
    assert [c.patch_id for c in c1] == [c.patch_id for c in c2]


# -----------------------------------------------------------------------------
# REQ-EVD-006: reject floor violations
# -----------------------------------------------------------------------------


def test_req_evd_006_infeasible_floor_candidate_dropped() -> None:
    # Two signals with registered floors already summing to 0.95;
    # adding any new +floor of ≥0.06 must be dropped.
    snapshot = MustAttendSnapshot(
        floors={"a": 0.50, "b": 0.45}, registry_hash="reg-v1"
    )
    # Force the cluster to under-attend a third signal "c" (floor=0 in
    # snapshot so FloorUpRule won't fire) — we instead construct a
    # cluster where FloorUpRule fires on "a" (under-attended) by 0.10.
    signals = ["a", "b"]
    records = [
        _mk_audit(i, weights=[0.02, 0.98], signals=signals, loss=3.0)
        for i in range(20)
    ]
    miner = Trace2SkillMiner(
        config=MinerConfig(support_min=5, cost_quantile=0.5, cluster_k_max=1)
    )
    out = miner.mine(records, snapshot)
    # Even though a single target +0.05 is feasible on its own
    # (0.50+0.45+0.05 = 1.00), any combination pushing over 1.0 must be
    # dropped. Concretely the miner must never emit a candidate whose
    # floor deltas sum with snapshot.floors to > 1.
    for c in out:
        total = snapshot.total_floor() + sum(
            t.delta for t in c.targets if t.field is PatchField.FLOOR
        )
        assert total <= 1.0 + 1e-9


# -----------------------------------------------------------------------------
# REQ-EVD-009: candidate count bounded
# -----------------------------------------------------------------------------


def test_req_evd_009_max_candidates_respected() -> None:
    # Create many distinct high-loss clusters via explicit trigger feature.
    snapshot = MustAttendSnapshot(registry_hash="reg-v1")
    signals = ["a", "b"]
    records: list[AuditRecord] = []
    for cluster_idx in range(10):
        for j in range(5):
            records.append(
                _mk_audit(
                    cluster_idx * 10 + j,
                    weights=[0.02, 0.98],
                    signals=signals,
                    loss=3.0,
                    context={"region": float(cluster_idx), "slo_breach": 3.0},
                )
            )
    miner = Trace2SkillMiner(
        config=MinerConfig(
            support_min=2,
            cost_quantile=0.0,
            cluster_k_max=3,
            max_candidates=2,
            trigger_features=("region",),
        )
    )
    out = miner.mine(records, snapshot)
    assert len(out) <= 2


# -----------------------------------------------------------------------------
# REQ-EVD-010: registry_hash attached
# -----------------------------------------------------------------------------


def test_req_evd_010_registry_hash_propagated() -> None:
    snapshot = MustAttendSnapshot(
        floors={"error_budget": 0.25}, registry_hash="reg-hash-42"
    )
    signals = ["cost", "error_budget"]
    records = [
        _mk_audit(i, weights=[0.95, 0.05], signals=signals, loss=3.0)
        for i in range(20)
    ]
    miner = Trace2SkillMiner(
        config=MinerConfig(support_min=5, cost_quantile=0.5, cluster_k_max=1)
    )
    out = miner.mine(records, snapshot)
    assert out, "expected at least one candidate"
    for c in out:
        assert c.registry_hash == "reg-hash-42"


# -----------------------------------------------------------------------------
# Low-support input is silent
# -----------------------------------------------------------------------------


def test_below_support_min_returns_empty() -> None:
    snapshot = MustAttendSnapshot(
        floors={"error_budget": 0.25}, registry_hash="reg-v1"
    )
    signals = ["cost", "error_budget"]
    records = [
        _mk_audit(i, weights=[0.95, 0.05], signals=signals, loss=3.0)
        for i in range(3)  # far fewer than support_min
    ]
    miner = Trace2SkillMiner(
        config=MinerConfig(support_min=10, cost_quantile=0.5, cluster_k_max=1)
    )
    assert miner.mine(records, snapshot) == []


def test_empty_input_returns_empty() -> None:
    miner = Trace2SkillMiner()
    assert miner.mine([], MustAttendSnapshot()) == []


def test_miner_accepts_config_as_first_positional() -> None:
    """Ergonomic fallback: Trace2SkillMiner(MinerConfig(...)) should Just Work.

    The primary signature is ``(loss_fn, rules, config)`` but spec examples
    in refined/PR-001 show users passing a ``MinerConfig`` first. Regression
    guard against a confusing ``'MinerConfig' is not callable`` crash.
    """
    snapshot = MustAttendSnapshot(registry_hash="reg-v1")
    miner = Trace2SkillMiner(
        MinerConfig(support_min=5, cost_quantile=0.5, cluster_k_max=1)
    )
    assert miner._cfg.support_min == 5
    # Also make sure mine() works through the fallback.
    assert miner.mine([], snapshot) == []


# -----------------------------------------------------------------------------
# Ceiling rule when dominated signal exists
# -----------------------------------------------------------------------------


def test_ceiling_rule_fires_on_dominated_signal() -> None:
    snapshot = MustAttendSnapshot(registry_hash="reg-v1")
    signals = ["dominator", "minor"]
    records = [
        _mk_audit(
            i,
            weights=[0.85, 0.15],  # dominator gets >= 0.6 → rule triggers
            signals=signals,
            loss=3.0,
        )
        for i in range(20)
    ]
    miner = Trace2SkillMiner(
        config=MinerConfig(support_min=5, cost_quantile=0.5, cluster_k_max=1)
    )
    out = miner.mine(records, snapshot)
    assert out
    assert any(
        t.signal_name == "dominator" and t.field is PatchField.CEILING and t.delta < 0
        for c in out
        for t in c.targets
    )
