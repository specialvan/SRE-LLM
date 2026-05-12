"""Conservative commit rule engine · PR-014.

Refined spec: ``skill-research/refined/PR-014-conservative-commit-refined.md``.
ADR-005: conservative by default; opt-out requires explicit config.

This module is **pure functional**: no IO, no clock, no randomness. The
caller (typically :class:`SkillRepository`) is responsible for writing
audit records on ``OVERRIDDEN`` verdicts.

Four rules (R1–R4):

* **R1 FLOOR_MONOTONE_INCREASE** — ``floor`` deltas may only increase.
* **R2 CEILING_MONOTONE_DECREASE** — ``ceiling`` deltas may only decrease.
* **R3 BIAS_STEP_CAP** — ``|Δ bias| ≤ bias_step_cap``.
* **R4 TEMPERATURE_STEP_CAP** — ``|Δ temperature| ≤ temperature_step_cap``.

Requirements satisfied:

* REQ-KNE-007 · floor/ceiling monotone
* REQ-KNE-010 · override audit payload
* REQ-SEC-006 · override field validation
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Sequence, Tuple

from attention_residuals.skill.types import (
    CommitDecision,
    OverrideInfo,
    PatchField,
    PatchTarget,
)

# REQ-SEC-006 · "^[A-Z]+-\d+$" ticket format.
_TICKET_PATTERN = re.compile(r"^[A-Z]+-\d+$")


class ConservativeRule(str, Enum):
    FLOOR_MONOTONE = "floor_monotone_increase"
    CEILING_MONOTONE = "ceiling_monotone_decrease"
    BIAS_STEP_CAP = "bias_step_cap"
    TEMPERATURE_STEP_CAP = "temperature_step_cap"


@dataclass(frozen=True)
class RuleViolation:
    """One rule violation; ``delta`` is the offending step size."""

    rule: ConservativeRule
    signal_name: str
    field: PatchField
    old_value: float
    new_value: float
    delta: float
    message: str


@dataclass(frozen=True)
class CommitVerdict:
    decision: CommitDecision
    offenders: Tuple[RuleViolation, ...]
    reason: str
    override: Optional[OverrideInfo] = None


@dataclass(frozen=True)
class ConservativeConfig:
    """Defaults align with ADR-005 (safe by default)."""

    bias_step_cap: float = 0.1
    temperature_step_cap: float = 0.2
    allow_floor_decrease: bool = False
    allow_ceiling_increase: bool = False


class ConservativeCommit:
    """Pure-functional rule engine for ``previous → proposed`` diffs."""

    _EPS = 1e-9

    def __init__(self, config: Optional[ConservativeConfig] = None) -> None:
        self._cfg = config or ConservativeConfig()

    @property
    def config(self) -> ConservativeConfig:
        return self._cfg

    def check(
        self,
        previous: Sequence[PatchTarget],
        proposed: Sequence[PatchTarget],
        override: Optional[OverrideInfo] = None,
    ) -> CommitVerdict:
        """Evaluate ``proposed`` against ``previous`` using R1–R4."""
        prev_idx = {(t.signal_name, t.field): t for t in previous}
        violations: list[RuleViolation] = []

        for new in proposed:
            old = prev_idx.get((new.signal_name, new.field))
            old_value = old.delta if old is not None else 0.0
            step = new.delta - old_value

            if new.field is PatchField.FLOOR:
                # R1: floor only ≥ unless explicitly allowed.
                if step < -self._EPS and not self._cfg.allow_floor_decrease:
                    violations.append(
                        RuleViolation(
                            rule=ConservativeRule.FLOOR_MONOTONE,
                            signal_name=new.signal_name,
                            field=new.field,
                            old_value=old_value,
                            new_value=new.delta,
                            delta=step,
                            message=(
                                f"floor decreased from {old_value:.4f} to {new.delta:.4f} "
                                f"(Δ={step:+.4f})"
                            ),
                        )
                    )
            elif new.field is PatchField.CEILING:
                # R2: ceiling only ≤ unless explicitly allowed.
                if step > self._EPS and not self._cfg.allow_ceiling_increase:
                    violations.append(
                        RuleViolation(
                            rule=ConservativeRule.CEILING_MONOTONE,
                            signal_name=new.signal_name,
                            field=new.field,
                            old_value=old_value,
                            new_value=new.delta,
                            delta=step,
                            message=(
                                f"ceiling increased from {old_value:.4f} to {new.delta:.4f} "
                                f"(Δ={step:+.4f})"
                            ),
                        )
                    )
            elif new.field is PatchField.BIAS:
                # R3: |step| ≤ cap.
                magnitude = abs(step)
                if magnitude > self._cfg.bias_step_cap + self._EPS:
                    violations.append(
                        RuleViolation(
                            rule=ConservativeRule.BIAS_STEP_CAP,
                            signal_name=new.signal_name,
                            field=new.field,
                            old_value=old_value,
                            new_value=new.delta,
                            delta=step,
                            message=(
                                f"bias step {magnitude:.4f} > cap {self._cfg.bias_step_cap:.4f}"
                            ),
                        )
                    )
            elif new.field is PatchField.TEMPERATURE:
                # R4: |step| ≤ cap.
                magnitude = abs(step)
                if magnitude > self._cfg.temperature_step_cap + self._EPS:
                    violations.append(
                        RuleViolation(
                            rule=ConservativeRule.TEMPERATURE_STEP_CAP,
                            signal_name=new.signal_name,
                            field=new.field,
                            old_value=old_value,
                            new_value=new.delta,
                            delta=step,
                            message=(
                                f"temperature step {magnitude:.4f} "
                                f"> cap {self._cfg.temperature_step_cap:.4f}"
                            ),
                        )
                    )

        if not violations:
            return CommitVerdict(
                decision=CommitDecision.ACCEPT,
                offenders=(),
                reason="ok",
                override=None,
            )

        if override is not None:
            self._validate_override(override)
            return CommitVerdict(
                decision=CommitDecision.OVERRIDDEN,
                offenders=tuple(violations),
                reason="manual override",
                override=override,
            )

        return CommitVerdict(
            decision=CommitDecision.REJECT,
            offenders=tuple(violations),
            reason="; ".join(v.message for v in violations),
            override=None,
        )

    @staticmethod
    def _validate_override(override: OverrideInfo) -> None:
        if not override.operator:
            raise ValueError("override requires non-empty operator")
        if not override.reason:
            raise ValueError("override requires non-empty reason")
        if not _TICKET_PATTERN.fullmatch(override.ticket_id):
            raise ValueError(
                f"ticket_id {override.ticket_id!r} must match {_TICKET_PATTERN.pattern}"
            )


__all__ = [
    "ConservativeCommit",
    "ConservativeConfig",
    "ConservativeRule",
    "CommitVerdict",
    "RuleViolation",
]
