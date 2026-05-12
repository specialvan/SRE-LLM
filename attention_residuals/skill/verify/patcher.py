"""Skill patcher · PR-006.

Refined spec: ``skill-research/refined/PR-006-*``.

Given a ``MergedSkillPatch`` and a list of ``VerifierFinding``, propose
a bounded set of ``SkillVariant``s that:

* adjust only targets pointed at by the findings' ``offending_signals``,
* move in the direction suggested by ``suggested_direction`` (sign),
* bound each step by ``cfg.max_delta_per_step``,
* obey the conservative rules (no floor decrease, no ceiling increase),
* stay inside the ``MustAttendSnapshot`` budget,
* are deterministically hashed and deduplicated by content.

This is a **pure-functional** component modulo the optional drift guard
hook — perfect for unit tests.

Requirements:

* REQ-KNE-004 · variants ≤ K
* REQ-KNE-005 · |target.delta - base.delta| ≤ max_delta_per_step
* REQ-KNE-006 · guard.DEFER/DENY → no variant this round
* REQ-KNE-012 · variant.derived_from is never null (except initial)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from attention_residuals.skill.trajectory.merger import MustAttendSnapshot
from attention_residuals.skill.types import (
    MergedSkillPatch,
    PatchField,
    PatchTarget,
    SkillVariant,
    VerifierFinding,
    compute_patch_id,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class PatcherConfig:
    """Patcher defaults; conservative-first per ADR-005."""

    max_variants_per_round: int = 5
    max_delta_per_step: float = 0.05
    # The conservative rules (R1 floor+, R2 ceiling-) are the patcher's
    # hard guardrails; this flag only exists for deliberate loosening
    # in test harnesses.
    respect_conservative: bool = True


class DriftGuardProtocol:
    """Duck-typed interface the patcher will consult before emitting."""

    def admit(self, patch_id: str) -> str:  # "allow" | "defer" | "deny"
        ...


class SkillPatcher:
    """Generate variants of a merged patch, steered by verifier findings."""

    def __init__(
        self,
        config: Optional[PatcherConfig] = None,
        guard: Optional[DriftGuardProtocol] = None,
    ) -> None:
        self._cfg = config or PatcherConfig()
        self._guard = guard
        # Seen variant ids across rounds (dedupe ; REQ-KNE-012).
        self._seen_ids: set[str] = set()

    # -------------------------------------------------- public API

    def propose(
        self,
        base: MergedSkillPatch,
        findings: Sequence[VerifierFinding],
        snapshot: Optional[MustAttendSnapshot] = None,
        generation: int = 0,
    ) -> List[SkillVariant]:
        """Return ≤ ``cfg.max_variants_per_round`` fresh variants.

        If ``guard.admit()`` returns anything other than ``"allow"``
        for the base patch, the patcher returns ``[]`` this round
        (REQ-KNE-006).
        """
        if self._guard is not None:
            decision = self._guard.admit(base.patch_id)
            if decision != "allow":
                _LOGGER.info(
                    "patcher deferring round: guard=%s for %s",
                    decision,
                    base.patch_id,
                )
                return []

        if not findings:
            return []

        snapshot = snapshot or MustAttendSnapshot()
        variants: List[SkillVariant] = []
        for finding in findings:
            for variant in self._variants_from_finding(
                base, finding, snapshot, generation
            ):
                if variant.variant_id in self._seen_ids:
                    continue
                self._seen_ids.add(variant.variant_id)
                variants.append(variant)
                if len(variants) >= self._cfg.max_variants_per_round:
                    return variants
        return variants

    # -------------------------------------------------- helpers

    def _variants_from_finding(
        self,
        base: MergedSkillPatch,
        finding: VerifierFinding,
        snapshot: MustAttendSnapshot,
        generation: int,
    ) -> List[SkillVariant]:
        """Generate 1 variant per (signal,direction) pair in the finding."""
        base_by_key: Dict[Tuple[str, PatchField], PatchTarget] = {
            (t.signal_name, t.field): t for t in base.targets
        }
        offending = set(finding.offending_signals)
        direction = dict(finding.suggested_direction)

        variants: List[SkillVariant] = []
        for signal_name, sign in direction.items():
            if sign == 0 or signal_name not in offending:
                continue
            # Apply to each field that already has a target on this signal.
            # If no target exists, synthesize one on the BIAS field (the
            # most general adjustment surface).
            fields_to_touch = [
                field for (name, field) in base_by_key if name == signal_name
            ]
            if not fields_to_touch:
                fields_to_touch = [PatchField.BIAS]
            for field_ in fields_to_touch:
                adjusted = self._adjust_target(
                    base_by_key.get((signal_name, field_)),
                    signal_name,
                    field_,
                    sign,
                    finding,
                    snapshot,
                )
                if adjusted is None:
                    continue
                variant_targets = list(base.targets)
                # replace-or-append
                replaced = False
                for idx, t in enumerate(variant_targets):
                    if t.signal_name == signal_name and t.field == field_:
                        variant_targets[idx] = adjusted
                        replaced = True
                        break
                if not replaced:
                    variant_targets.append(adjusted)

                variant_id = compute_patch_id(tuple(variant_targets), {})
                variants.append(
                    SkillVariant(
                        variant_id=variant_id,
                        source_patch_id=base.patch_id,
                        targets=tuple(variant_targets),
                        derived_from=finding.finding_id,
                        generation=generation,
                    )
                )
        return variants

    def _adjust_target(
        self,
        base_target: Optional[PatchTarget],
        signal_name: str,
        field_: PatchField,
        sign: int,
        finding: VerifierFinding,
        snapshot: MustAttendSnapshot,
    ) -> Optional[PatchTarget]:
        """Return a new :class:`PatchTarget` or ``None`` if the adjustment
        would violate a hard rule (conservative / must-attend)."""
        base_delta = base_target.delta if base_target is not None else 0.0
        step = self._cfg.max_delta_per_step * sign
        new_delta = base_delta + step

        # Conservative pre-filter (R1, R2) — guard mode only.
        if self._cfg.respect_conservative:
            if field_ is PatchField.FLOOR and step < 0:
                return None
            if field_ is PatchField.CEILING and step > 0:
                return None

        # Clamp into the field's valid range.
        if field_ is PatchField.FLOOR:
            new_delta = max(0.0, min(1.0, new_delta))
        elif field_ is PatchField.CEILING:
            new_delta = max(-1.0, min(0.0, new_delta))

        if abs(new_delta - base_delta) < 1e-9:
            return None  # no effective movement

        # Must-attend feasibility: floor delta must fit remaining budget.
        if field_ is PatchField.FLOOR:
            projected = snapshot.total_floor() + (new_delta - base_delta)
            if projected > 1.0 + 1e-9:
                return None

        rationale = (
            f"derived from {finding.finding_id} "
            f"(sign={sign:+d}, severity={finding.severity:.2f})"
        )[:200]
        return PatchTarget(
            signal_name=signal_name,
            field=field_,
            delta=float(new_delta),
            rationale=rationale,
        )


__all__ = [
    "DriftGuardProtocol",
    "PatcherConfig",
    "SkillPatcher",
]
