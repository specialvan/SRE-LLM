"""Tests for ``attention_residuals.skill.types``.

Validates:

* REQ-DAT-001..008 (dataclass invariants, round-trip, hash stability)
* REQ-EVD-005     (deterministic patch_id)
"""

from __future__ import annotations

import pytest

from attention_residuals.skill.types import (
    SCHEMA_VERSION,
    BlastRadius,
    ChangeKind,
    ConflictReason,
    EventKind,
    Granularity,
    MergeConflict,
    MergedSkillPatch,
    OverrideInfo,
    PatchField,
    PatchTarget,
    RoutingDecision,
    RoutingRationale,
    SkillOpsEvent,
    SkillPatchCandidate,
    SkillRecord,
    SkillVariant,
    SkillVersion,
    Stage,
    VerifierFinding,
    compute_patch_id,
    compute_version_id,
)


# -----------------------------------------------------------------------------
# PatchTarget
# -----------------------------------------------------------------------------


def test_req_dat_004_patchtarget_field_enum_required() -> None:
    with pytest.raises(ValueError):
        PatchTarget(signal_name="x", field="floor", delta=0.1, rationale="")  # type: ignore[arg-type]


def test_req_dat_005_rationale_length_limit() -> None:
    with pytest.raises(ValueError):
        PatchTarget(
            signal_name="x",
            field=PatchField.BIAS,
            delta=0.0,
            rationale="y" * 201,
        )


def test_req_dat_004_floor_range_guard() -> None:
    with pytest.raises(ValueError):
        PatchTarget(signal_name="x", field=PatchField.FLOOR, delta=-0.1)
    with pytest.raises(ValueError):
        PatchTarget(signal_name="x", field=PatchField.FLOOR, delta=1.5)


def test_req_dat_004_ceiling_range_guard() -> None:
    with pytest.raises(ValueError):
        PatchTarget(signal_name="x", field=PatchField.CEILING, delta=0.1)
    with pytest.raises(ValueError):
        PatchTarget(signal_name="x", field=PatchField.CEILING, delta=-1.5)


def test_req_dat_002_patchtarget_roundtrip() -> None:
    t = PatchTarget(
        signal_name="error_budget",
        field=PatchField.FLOOR,
        delta=0.05,
        rationale="why not",
    )
    d = t.to_dict()
    assert d["_schema"] == SCHEMA_VERSION
    assert PatchTarget.from_dict(d) == t


# -----------------------------------------------------------------------------
# compute_patch_id / compute_version_id
# -----------------------------------------------------------------------------


def test_req_evd_005_patch_id_deterministic() -> None:
    a = PatchTarget("s1", PatchField.BIAS, 0.2)
    b = PatchTarget("s2", PatchField.FLOOR, 0.1)
    trig = {"x": 1.0, "y": 2.0}
    id1 = compute_patch_id((a, b), trig)
    id2 = compute_patch_id((b, a), dict(trig))  # reordered input
    assert id1 == id2


def test_req_evd_005_patch_id_sensitive_to_change() -> None:
    a = PatchTarget("s1", PatchField.BIAS, 0.2)
    b = PatchTarget("s1", PatchField.BIAS, 0.25)
    assert compute_patch_id((a,), {}) != compute_patch_id((b,), {})


def test_version_id_excludes_timestamp() -> None:
    vid1 = compute_version_id(
        "skill-1", (PatchTarget("a", PatchField.BIAS, 0.1),), ("p1",), "alice"
    )
    vid2 = compute_version_id(
        "skill-1", (PatchTarget("a", PatchField.BIAS, 0.1),), ("p1",), "alice"
    )
    assert vid1 == vid2
    # But author or parents change it
    vid3 = compute_version_id(
        "skill-1", (PatchTarget("a", PatchField.BIAS, 0.1),), ("p2",), "alice"
    )
    assert vid1 != vid3


# -----------------------------------------------------------------------------
# SkillPatchCandidate
# -----------------------------------------------------------------------------


def test_skillpatchcandidate_rejects_wrong_id() -> None:
    t = PatchTarget("s", PatchField.BIAS, 0.1)
    with pytest.raises(ValueError):
        SkillPatchCandidate(
            patch_id="deadbeefdeadbeef",
            trigger={},
            targets=(t,),
            evidence_steps=(1, 2),
            support=2,
            avg_cost_before=0.3,
            score=0.6,
            registry_hash="abc",
        )


def test_skillpatchcandidate_roundtrip() -> None:
    t = PatchTarget("s", PatchField.BIAS, 0.1)
    c = SkillPatchCandidate(
        patch_id=compute_patch_id((t,), {"x": 0.5}),
        trigger={"x": 0.5},
        targets=(t,),
        evidence_steps=(1, 2, 3),
        support=3,
        avg_cost_before=1.5,
        score=4.5,
        registry_hash="reg-hash-1",
    )
    assert SkillPatchCandidate.from_dict(c.to_dict()) == c


# -----------------------------------------------------------------------------
# BlastRadius (REQ-DAT-008)
# -----------------------------------------------------------------------------


def test_blast_radius_formula_known_values() -> None:
    br = BlastRadius.compute(
        affected_signals=("p99", "cost"),
        affected_tenants=("east",),
        estimated_traffic_share=0.5,
        total_signals=10,
        total_tenants=3,
    )
    # 0.4 * 2/10 + 0.3 * 1/3 + 0.3 * 0.5 = 0.08 + 0.1 + 0.15 = 0.33
    assert abs(br.blast_score - 0.33) < 1e-9


def test_blast_radius_is_safe_threshold() -> None:
    br = BlastRadius(
        affected_signals=("x",),
        affected_tenants=("a",),
        estimated_traffic_share=0.05,
        blast_score=0.12,
    )
    assert br.is_safe() is True
    assert br.is_safe(threshold=0.1) is False


def test_blast_radius_roundtrip() -> None:
    br = BlastRadius.compute(("a",), ("t",), 0.1)
    assert BlastRadius.from_dict(br.to_dict()) == br


# -----------------------------------------------------------------------------
# SkillVersion / MergeConflict / VerifierFinding
# -----------------------------------------------------------------------------


def test_req_dat_007_skillversion_self_parent_rejected() -> None:
    with pytest.raises(ValueError):
        SkillVersion(
            version_id="v1",
            skill_id="s1",
            parents=("v1",),
            author="a",
            timestamp=0.0,
            summary="",
            change_kind=ChangeKind.CREATE,
            blast_radius=BlastRadius.compute((), (), 0.0),
        )


def test_skillversion_summary_length_cap() -> None:
    with pytest.raises(ValueError):
        SkillVersion(
            version_id="v1",
            skill_id="s1",
            parents=(),
            author="a",
            timestamp=0.0,
            summary="x" * 100,
            change_kind=ChangeKind.CREATE,
            blast_radius=BlastRadius.compute((), (), 0.0),
        )


def test_merge_conflict_roundtrip() -> None:
    c = MergeConflict(
        signal_name="x",
        field="floor",
        candidates=(PatchTarget("x", PatchField.FLOOR, 0.2),),
        reason=ConflictReason.FLOOR_BUDGET_EXCEEDED,
    )
    assert MergeConflict.from_dict(c.to_dict()) == c


def test_verifier_finding_severity_range() -> None:
    with pytest.raises(ValueError):
        VerifierFinding(
            finding_id="f",
            offending_signals=("x",),
            suggested_direction={"x": 0},
            severity=1.5,
        )


def test_verifier_finding_direction_domain() -> None:
    with pytest.raises(ValueError):
        VerifierFinding(
            finding_id="f",
            offending_signals=("x",),
            suggested_direction={"x": 2},
            severity=0.5,
        )


# -----------------------------------------------------------------------------
# SkillRecord key / roundtrip
# -----------------------------------------------------------------------------


def test_req_dat_006_skillrecord_key() -> None:
    r = SkillRecord(
        skill_id="sid",
        version="v1",
        tenant="east",
        stage=Stage.SANDBOX,
        meta={"name": "demo"},
        targets=(PatchTarget("a", PatchField.BIAS, 0.1),),
    )
    assert r.key() == ("sid", "v1", "east")


def test_skillrecord_roundtrip() -> None:
    r = SkillRecord(
        skill_id="sid",
        version="v1",
        tenant="east",
        stage=Stage.ACTIVE,
        meta={"desc": "x"},
        targets=(PatchTarget("a", PatchField.BIAS, 0.1),),
        utility=0.4,
        use_count=5,
        tags=frozenset({"elite"}),
        created_at=123.0,
    )
    assert SkillRecord.from_dict(r.to_dict()) == r


# -----------------------------------------------------------------------------
# MergedSkillPatch / SkillVariant / RoutingDecision / OverrideInfo / Event
# -----------------------------------------------------------------------------


def test_mergedpatch_roundtrip_empty() -> None:
    m = MergedSkillPatch(patch_id="abc", targets=())
    assert MergedSkillPatch.from_dict(m.to_dict()) == m


def test_skillvariant_roundtrip() -> None:
    v = SkillVariant(
        variant_id="vv",
        source_patch_id="src",
        targets=(PatchTarget("a", PatchField.BIAS, 0.1),),
        derived_from="find-1",
        generation=2,
    )
    assert SkillVariant.from_dict(v.to_dict()) == v


def test_routing_decision_roundtrip() -> None:
    d = RoutingDecision(
        skill_id="s",
        version="v",
        confidence=0.9,
        granularity=Granularity.STEP,
        rationale=RoutingRationale(0.5, 0.3, 0.1, 0.9),
    )
    assert RoutingDecision.from_dict(d.to_dict()) == d


def test_override_info_roundtrip() -> None:
    o = OverrideInfo(operator="alice", reason="needed", ticket_id="ABC-123")
    assert OverrideInfo.from_dict(o.to_dict()) == o


def test_event_roundtrip() -> None:
    ev = SkillOpsEvent(
        kind=EventKind.ROUTING_PICK,
        step=42,
        tenant="east",
        payload={"picks": []},
        trace_id="trace-1",
    )
    assert SkillOpsEvent.from_dict(ev.to_dict()) == ev
