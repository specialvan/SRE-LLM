"""Tests for :class:`DualGranularitySkillBank` (PR-018)."""

from __future__ import annotations

import pytest

from attention_residuals.skill.policy_skill.bank import (
    DualGranularitySkillBank,
    StepSkill,
    TaskSkill,
)
from attention_residuals.skill.types import (
    Granularity,
    PatchField,
    PatchTarget,
    SkillRecord,
    Stage,
)


def _mk_step(sid: str, trigger=None) -> StepSkill:
    return StepSkill(
        skill_id=sid,
        targets=(PatchTarget("a", PatchField.BIAS, 0.1),),
        trigger=dict(trigger or {}),
    )


def _mk_task(sid: str) -> TaskSkill:
    return TaskSkill(
        skill_id=sid,
        horizon_ticks=60,
        objective_template="minimize p99 over horizon",
        params={"target": 0.3},
    )


def test_put_and_get_step() -> None:
    bank = DualGranularitySkillBank()
    s = _mk_step("s1")
    bank.put_step(s)
    assert bank.get_step("s1") == s
    assert bank.get_task("s1") is None


def test_put_and_get_task() -> None:
    bank = DualGranularitySkillBank()
    t = _mk_task("t1")
    bank.put_task(t)
    assert bank.get_task("t1") == t
    assert bank.get_step("t1") is None


def test_remove_hits_both_sides() -> None:
    bank = DualGranularitySkillBank()
    bank.put_step(_mk_step("shared"))
    bank.put_task(_mk_task("shared"))
    assert bank.remove("shared") is True
    assert bank.get_step("shared") is None
    assert bank.get_task("shared") is None


def test_query_filters_by_granularity() -> None:
    bank = DualGranularitySkillBank()
    bank.put_step(_mk_step("step-a"))
    bank.put_step(_mk_step("step-b"))
    bank.put_task(_mk_task("task-a"))
    all_pairs = bank.query()
    assert len(all_pairs) == 3
    only_tasks = bank.query(granularity=Granularity.TASK)
    assert {sid for sid, _ in only_tasks} == {"task-a"}
    only_steps = bank.query(granularity=Granularity.STEP)
    assert {sid for sid, _ in only_steps} == {"step-a", "step-b"}


def test_query_trigger_match_respects_own_trigger() -> None:
    bank = DualGranularitySkillBank()
    bank.put_step(_mk_step("east", trigger={"region": 0.0}))
    bank.put_step(_mk_step("west", trigger={"region": 1.0}))
    bank.put_step(_mk_step("anywhere"))                # no trigger = wildcard
    pairs = bank.query(
        granularity=Granularity.STEP, trigger_match={"region": 0.0}
    )
    ids = {sid for sid, _ in pairs}
    assert "east" in ids and "anywhere" in ids
    assert "west" not in ids


def test_from_skill_record_registers_step() -> None:
    bank = DualGranularitySkillBank()
    record = SkillRecord(
        skill_id="from-repo",
        version="v1",
        tenant="default",
        stage=Stage.ACTIVE,
        meta={},
        targets=(PatchTarget("a", PatchField.BIAS, 0.05),),
        tags=frozenset({"elite"}),
    )
    step = bank.from_skill_record(record)
    assert bank.get_step("from-repo") is step
    assert "elite" in step.tags


def test_len_sums_both_indices() -> None:
    bank = DualGranularitySkillBank()
    assert len(bank) == 0
    bank.put_step(_mk_step("s1"))
    bank.put_task(_mk_task("t1"))
    assert len(bank) == 2
