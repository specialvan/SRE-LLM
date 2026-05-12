"""Tests for :class:`ConservativeCommit` (PR-014).

Covers REQ-KNE-007, REQ-KNE-010, REQ-SEC-006.
"""

from __future__ import annotations

import pytest

from attention_residuals.skill.governance.conservative import (
    CommitVerdict,
    ConservativeCommit,
    ConservativeConfig,
    ConservativeRule,
)
from attention_residuals.skill.types import (
    CommitDecision,
    OverrideInfo,
    PatchField,
    PatchTarget,
)


# -----------------------------------------------------------------------------
# R1 FLOOR_MONOTONE
# -----------------------------------------------------------------------------


def test_req_kne_007_floor_decrease_rejected() -> None:
    cc = ConservativeCommit()
    prev = [PatchTarget("sig", PatchField.FLOOR, 0.30)]
    new = [PatchTarget("sig", PatchField.FLOOR, 0.25)]
    v = cc.check(prev, new)
    assert v.decision is CommitDecision.REJECT
    assert v.offenders[0].rule is ConservativeRule.FLOOR_MONOTONE


def test_floor_increase_accepted() -> None:
    cc = ConservativeCommit()
    prev = [PatchTarget("sig", PatchField.FLOOR, 0.30)]
    new = [PatchTarget("sig", PatchField.FLOOR, 0.35)]
    v = cc.check(prev, new)
    assert v.decision is CommitDecision.ACCEPT


def test_floor_decrease_allowed_by_config_flag() -> None:
    cc = ConservativeCommit(ConservativeConfig(allow_floor_decrease=True))
    prev = [PatchTarget("sig", PatchField.FLOOR, 0.30)]
    new = [PatchTarget("sig", PatchField.FLOOR, 0.25)]
    assert cc.check(prev, new).decision is CommitDecision.ACCEPT


# -----------------------------------------------------------------------------
# R2 CEILING_MONOTONE
# -----------------------------------------------------------------------------


def test_ceiling_increase_rejected() -> None:
    cc = ConservativeCommit()
    prev = [PatchTarget("sig", PatchField.CEILING, -0.10)]
    new = [PatchTarget("sig", PatchField.CEILING, -0.05)]  # loosening ceiling
    v = cc.check(prev, new)
    assert v.decision is CommitDecision.REJECT
    assert v.offenders[0].rule is ConservativeRule.CEILING_MONOTONE


def test_ceiling_decrease_accepted() -> None:
    cc = ConservativeCommit()
    prev = [PatchTarget("sig", PatchField.CEILING, -0.10)]
    new = [PatchTarget("sig", PatchField.CEILING, -0.15)]
    assert cc.check(prev, new).decision is CommitDecision.ACCEPT


# -----------------------------------------------------------------------------
# R3 BIAS_STEP_CAP
# -----------------------------------------------------------------------------


def test_bias_step_over_cap_rejected() -> None:
    cc = ConservativeCommit(ConservativeConfig(bias_step_cap=0.1))
    prev = [PatchTarget("sig", PatchField.BIAS, 0.0)]
    new = [PatchTarget("sig", PatchField.BIAS, 0.25)]
    v = cc.check(prev, new)
    assert v.decision is CommitDecision.REJECT
    assert v.offenders[0].rule is ConservativeRule.BIAS_STEP_CAP


def test_bias_step_within_cap_accepted() -> None:
    cc = ConservativeCommit(ConservativeConfig(bias_step_cap=0.1))
    prev = [PatchTarget("sig", PatchField.BIAS, 0.2)]
    new = [PatchTarget("sig", PatchField.BIAS, 0.28)]
    assert cc.check(prev, new).decision is CommitDecision.ACCEPT


# -----------------------------------------------------------------------------
# R4 TEMPERATURE_STEP_CAP
# -----------------------------------------------------------------------------


def test_temperature_cap() -> None:
    cc = ConservativeCommit(ConservativeConfig(temperature_step_cap=0.2))
    prev = [PatchTarget("sig", PatchField.TEMPERATURE, 1.0)]
    over = [PatchTarget("sig", PatchField.TEMPERATURE, 1.3)]
    ok = [PatchTarget("sig", PatchField.TEMPERATURE, 1.15)]
    assert cc.check(prev, over).decision is CommitDecision.REJECT
    assert cc.check(prev, ok).decision is CommitDecision.ACCEPT


# -----------------------------------------------------------------------------
# Override (REQ-SEC-006)
# -----------------------------------------------------------------------------


def test_override_converts_reject_to_overridden() -> None:
    cc = ConservativeCommit()
    prev = [PatchTarget("sig", PatchField.FLOOR, 0.30)]
    new = [PatchTarget("sig", PatchField.FLOOR, 0.25)]
    override = OverrideInfo(operator="alice", reason="emergency", ticket_id="SRE-42")
    v = cc.check(prev, new, override=override)
    assert v.decision is CommitDecision.OVERRIDDEN
    assert v.override == override
    assert len(v.offenders) == 1


def test_override_missing_operator_raises() -> None:
    cc = ConservativeCommit()
    # Must have a real violation so the OVERRIDDEN path gets exercised.
    prev = [PatchTarget("s", PatchField.FLOOR, 0.3)]
    new = [PatchTarget("s", PatchField.FLOOR, 0.25)]
    with pytest.raises(ValueError, match="operator"):
        cc.check(
            prev,
            new,
            override=OverrideInfo(operator="", reason="r", ticket_id="SRE-1"),
        )


def test_override_bad_ticket_format_raises() -> None:
    cc = ConservativeCommit()
    prev = [PatchTarget("s", PatchField.FLOOR, 0.3)]
    new = [PatchTarget("s", PatchField.FLOOR, 0.25)]
    for bad in ("ABC123", "abc-123", "1-ABC", "SRE_42"):
        with pytest.raises(ValueError, match="ticket_id"):
            cc.check(
                prev,
                new,
                override=OverrideInfo("alice", "r", bad),
            )


# -----------------------------------------------------------------------------
# Multi-violation enumeration + purity
# -----------------------------------------------------------------------------


def test_multiple_violations_all_enumerated() -> None:
    cc = ConservativeCommit(ConservativeConfig(bias_step_cap=0.1))
    prev = [
        PatchTarget("s1", PatchField.FLOOR, 0.4),
        PatchTarget("s2", PatchField.BIAS, 0.0),
    ]
    new = [
        PatchTarget("s1", PatchField.FLOOR, 0.3),  # R1
        PatchTarget("s2", PatchField.BIAS, 0.3),   # R3
    ]
    v = cc.check(prev, new)
    rules = {o.rule for o in v.offenders}
    assert rules == {ConservativeRule.FLOOR_MONOTONE, ConservativeRule.BIAS_STEP_CAP}


def test_idempotent_no_change_accepted() -> None:
    cc = ConservativeCommit()
    same = [
        PatchTarget("a", PatchField.FLOOR, 0.2),
        PatchTarget("b", PatchField.CEILING, -0.1),
        PatchTarget("c", PatchField.BIAS, 0.05),
    ]
    assert cc.check(same, list(same)).decision is CommitDecision.ACCEPT


def test_check_is_pure_no_side_effects() -> None:
    cc = ConservativeCommit()
    prev = [PatchTarget("x", PatchField.FLOOR, 0.3)]
    new = [PatchTarget("x", PatchField.FLOOR, 0.25)]
    v1 = cc.check(prev, new)
    v2 = cc.check(prev, new)
    assert v1 == v2


# -----------------------------------------------------------------------------
# Verdict JSON-ability (smoke test)
# -----------------------------------------------------------------------------


def test_verdict_fields_are_plain() -> None:
    cc = ConservativeCommit()
    prev = [PatchTarget("x", PatchField.FLOOR, 0.3)]
    new = [PatchTarget("x", PatchField.FLOOR, 0.25)]
    v = cc.check(prev, new)
    # Just touch fields to ensure they are the declared types.
    assert isinstance(v.decision, CommitDecision)
    assert isinstance(v.reason, str) and v.reason
    assert all(isinstance(o.message, str) for o in v.offenders)
