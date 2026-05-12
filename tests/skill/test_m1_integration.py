"""End-to-end M1 integration: miner → merger → repo + conservative + elite.

This test covers the "offline loop" milestone contract:

    audit records
        └─▶ Trace2SkillMiner
                └─▶ HierarchicalPatchMerger
                        └─▶ ConservativeCommit.check (via Repository hook)
                                └─▶ SkillRepository.put + promote
                                        └─▶ ElitePool admits / evicts

If any link breaks the spec invariants (Σfloor ≤ 1, conservative rules,
capacity bound) the test fails.
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from attention_residuals.sre_control import AuditRecord
from attention_residuals.skill.governance import (
    ConservativeCommit,
    ConservativeConfig,
    Elite,
    ElitePool,
    ElitePoolConfig,
    SkillRepository,
    SkillVersionGraph,
)
from attention_residuals.skill.trajectory import (
    HierarchicalPatchMerger,
    MustAttendSnapshot,
    Trace2SkillMiner,
)
from attention_residuals.skill.trajectory.miner import MinerConfig
from attention_residuals.skill.types import (
    BlastRadius,
    ChangeKind,
    PatchField,
    PatchTarget,
    SkillRecord,
    SkillVersion,
    Stage,
    compute_version_id,
)


def _mk_records(n: int = 40) -> list[AuditRecord]:
    signals = ["cost", "error_budget"]
    return [
        AuditRecord(
            step=i,
            signal_names=signals,
            weights=np.array([0.92, 0.08]),
            action=np.zeros(1),
            context={"slo_breach": 3.0 if i < 25 else 0.2},
        )
        for i in range(n)
    ]


def test_offline_loop_ends_with_active_skill(tmp_path) -> None:
    snapshot = MustAttendSnapshot(
        floors={"error_budget": 0.25}, registry_hash="reg-v1"
    )
    miner = Trace2SkillMiner(
        config=MinerConfig(support_min=5, cost_quantile=0.5, cluster_k_max=1)
    )
    merger = HierarchicalPatchMerger(snapshot)
    conservative = ConservativeCommit()

    def hook(prev, proposed) -> None:
        v = conservative.check(prev, proposed)
        if v.decision.value == "reject":
            raise AssertionError(f"conservative rejected: {v.reason}")

    graph = SkillVersionGraph()
    repo = SkillRepository(graph=graph, base_dir=tmp_path, conservative_hook=hook)
    pool = ElitePool(ElitePoolConfig(capacity=8, min_probation_steps=2))

    # --- mine ---
    records = _mk_records(40)
    candidates = miner.mine(records, snapshot)
    assert candidates, "miner should produce candidates on under-attended floor"

    # --- merge ---
    merged = merger.merge(candidates)
    assert merged.targets, "merger should produce at least one target"
    for t in merged.targets:
        # Conservative default: no floor decrease, no ceiling increase.
        if t.field is PatchField.FLOOR:
            assert t.delta >= 0
        if t.field is PatchField.CEILING:
            assert t.delta <= 0

    # --- commit (put) ---
    skill_id = "error-budget-tighten"
    version_id = compute_version_id(skill_id, merged.targets, (), "miner-bot")
    version = SkillVersion(
        version_id=version_id,
        skill_id=skill_id,
        parents=(),
        author="miner-bot",
        timestamp=time.time(),
        summary="distilled from audit",
        change_kind=ChangeKind.CREATE,
        blast_radius=BlastRadius.compute(
            affected_signals=[t.signal_name for t in merged.targets],
            affected_tenants=["east"],
            estimated_traffic_share=0.1,
        ),
    )
    record = SkillRecord(
        skill_id=skill_id,
        version=version_id,
        tenant="east",
        stage=Stage.SANDBOX,
        meta={"desc": "test"},
        targets=merged.targets,
    )
    repo.put(record, version=version)
    repo.promote(skill_id, to_stage=Stage.QUARANTINE, tenant="east")
    repo.promote(skill_id, to_stage=Stage.ACTIVE, tenant="east")

    # --- admit into elite pool ---
    event = pool.try_admit(Elite(variant_id=version_id, score=0.9), step=0)
    assert event is None, "empty pool: should go to probation without eviction"
    pool.evict_probation_breakers(step=10)
    assert version_id in pool.member_states()

    # --- end state invariants ---
    active = repo.get(skill_id, tenant="east")
    assert active.stage is Stage.ACTIVE
    assert active.version == version_id

    # Σfloor budget invariant: Σ(current_floor + delta) ≤ 1
    floor_budget_used = snapshot.total_floor() + sum(
        t.delta for t in merged.targets if t.field is PatchField.FLOOR
    )
    assert floor_budget_used <= 1.0 + 1e-9

    # ElitePool capacity invariant
    assert len(pool) <= pool.capacity


def test_conservative_hook_can_block_regression(tmp_path) -> None:
    """A second put that tries to lower a floor is rejected by the hook."""
    snapshot = MustAttendSnapshot(registry_hash="reg-v1")
    cons = ConservativeCommit()

    hook_blocks_regression: list[str] = []

    def hook(prev, proposed) -> None:
        v = cons.check(prev, proposed)
        if v.decision.value == "reject":
            hook_blocks_regression.append(v.reason)
            raise AssertionError(v.reason)

    graph = SkillVersionGraph()
    repo = SkillRepository(graph=graph, base_dir=tmp_path, conservative_hook=hook)

    skill_id = "s"
    t_ok = (PatchTarget("a", PatchField.FLOOR, 0.10, "first tighten"),)
    v1 = SkillVersion(
        version_id=compute_version_id(skill_id, t_ok, (), "a"),
        skill_id=skill_id,
        parents=(),
        author="a",
        timestamp=0.0,
        summary="first",
        change_kind=ChangeKind.CREATE,
        blast_radius=BlastRadius.compute((), (), 0.0),
    )
    r1 = SkillRecord(skill_id, v1.version_id, "default", Stage.ACTIVE, {}, t_ok)
    repo.put(r1, version=v1)

    # Now try to regress the floor — hook must block.
    t_bad = (PatchTarget("a", PatchField.FLOOR, 0.05, "regress"),)
    v2 = SkillVersion(
        version_id=compute_version_id(skill_id, t_bad, (v1.version_id,), "a"),
        skill_id=skill_id,
        parents=(v1.version_id,),
        author="a",
        timestamp=1.0,
        summary="regress",
        change_kind=ChangeKind.EDIT,
        blast_radius=BlastRadius.compute((), (), 0.0),
    )
    r2 = SkillRecord(skill_id, v2.version_id, "default", Stage.SANDBOX, {}, t_bad)

    with pytest.raises(AssertionError):
        repo.put(r2, version=v2)

    # Index unchanged: only v1 present.
    assert len(repo.list(tenant="default")) == 1
    assert hook_blocks_regression
