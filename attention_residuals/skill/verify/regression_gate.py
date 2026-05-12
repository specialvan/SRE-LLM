"""Regression gate · PR-008.

Refined spec: ``skill-research/refined/PR-008-skill-regression-gate-refined.md``.

Consumes :class:`VerifyResult` produced by PR-007 and returns a
:class:`GateVerdict` in ``{ADMIT, QUARANTINE, ROLLBACK_REQUIRED}``.

Four rules, checked in order:

1. **core 0-regression** — ``core_pass_rate ≥ regression_pass_rate_floor``
2. **divergence ceiling** — ``avg_divergence ≤ divergence_ceiling``
3. **holdout pass** — if miss → QUARANTINE (or ROLLBACK if configured)
4. **all pass** → ADMIT

`promote_new_tests` accepts the verifier's derived tests into the
holdout suite (never the core).

Requirements:

* REQ-VRF-003 · ADMIT ⇔ core_pass==1 AND div ≤ ceiling AND hold ≥ floor
* REQ-VRF-004 · regression → ROLLBACK
* REQ-VRF-010 · promote_new_tests into holdout only
* REQ-VRF-011 · reasons list always non-empty
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, List, Mapping, Optional, Sequence, Tuple

from attention_residuals.skill.verify.shadow_verifier import (
    ReplayCase,
    VerifyResult,
)

_LOGGER = logging.getLogger(__name__)


class GateDecision(str, Enum):
    ADMIT = "admit"
    QUARANTINE = "quarantine"
    ROLLBACK_REQUIRED = "rollback"


@dataclass
class GateConfig:
    """Gate defaults align with ADR-005 (safe by default)."""

    regression_pass_rate_floor: float = 1.0
    holdout_pass_rate_floor: float = 0.9
    divergence_ceiling: float = 0.15
    quarantine_on_holdout_miss: bool = True


@dataclass(frozen=True)
class GateVerdict:
    decision: GateDecision
    core_pass_rate: float
    holdout_pass_rate: float
    divergence: float
    reasons: Tuple[str, ...]


class _Suite:
    """Mutable, dict-backed replay suite (id → case)."""

    def __init__(self) -> None:
        self._cases: dict[str, ReplayCase] = {}
        self._version = 0

    def add(self, case: ReplayCase) -> bool:
        if case.case_id in self._cases:
            return False
        self._cases[case.case_id] = case
        self._version += 1
        return True

    def remove(self, case_id: str) -> bool:
        if case_id in self._cases:
            del self._cases[case_id]
            self._version += 1
            return True
        return False

    def __len__(self) -> int:
        return len(self._cases)

    def __iter__(self):
        return iter(self._cases.values())

    @property
    def version(self) -> int:
        return self._version


class SkillRegressionGate:
    """Suite manager + decision arbiter."""

    def __init__(self, config: Optional[GateConfig] = None) -> None:
        self._cfg = config or GateConfig()
        self._core = _Suite()
        self._holdout = _Suite()

    # -------------------------------------------------- suite management

    def add_core_case(self, case: ReplayCase) -> bool:
        return self._core.add(case)

    def add_holdout_case(self, case: ReplayCase) -> bool:
        return self._holdout.add(case)

    def promote_new_tests(self, cases: Iterable[ReplayCase]) -> int:
        """Absorb verifier-derived cases into the HOLDOUT suite only."""
        added = 0
        for c in cases:
            if self._holdout.add(c):
                added += 1
        return added

    def core_cases(self) -> List[ReplayCase]:
        return list(self._core)

    def holdout_cases(self) -> List[ReplayCase]:
        return list(self._holdout)

    def core_size(self) -> int:
        return len(self._core)

    def holdout_size(self) -> int:
        return len(self._holdout)

    # -------------------------------------------------- arbitration

    def decide(self, result: VerifyResult) -> GateVerdict:
        """Apply rules R1–R4 in order; return a :class:`GateVerdict`."""
        reasons: List[str] = []
        core_pass = float(result.diagnostics.get("train_pass_rate", 0.0))
        holdout_pass = float(result.diagnostics.get("holdout_pass_rate", 1.0))
        # Prefer max divergence as the worst-case signal; fall back to avg.
        divergence = float(
            result.diagnostics.get(
                "max_divergence", result.diagnostics.get("avg_divergence", 0.0)
            )
        )

        # Rule 1: core 0-regression (strict).
        if core_pass + 1e-9 < self._cfg.regression_pass_rate_floor:
            reasons.append(
                f"core pass rate {core_pass:.2%} "
                f"< floor {self._cfg.regression_pass_rate_floor:.2%}"
            )
            return GateVerdict(
                decision=GateDecision.ROLLBACK_REQUIRED,
                core_pass_rate=core_pass,
                holdout_pass_rate=holdout_pass,
                divergence=divergence,
                reasons=tuple(reasons),
            )

        # Rule 2: divergence ceiling.
        if divergence > self._cfg.divergence_ceiling + 1e-9:
            reasons.append(
                f"divergence {divergence:.4f} "
                f"> ceiling {self._cfg.divergence_ceiling:.4f}"
            )
            return GateVerdict(
                decision=GateDecision.ROLLBACK_REQUIRED,
                core_pass_rate=core_pass,
                holdout_pass_rate=holdout_pass,
                divergence=divergence,
                reasons=tuple(reasons),
            )

        # Rule 3: holdout miss.
        if holdout_pass + 1e-9 < self._cfg.holdout_pass_rate_floor:
            decision = (
                GateDecision.QUARANTINE
                if self._cfg.quarantine_on_holdout_miss
                else GateDecision.ROLLBACK_REQUIRED
            )
            reasons.append(
                f"holdout pass rate {holdout_pass:.2%} "
                f"< floor {self._cfg.holdout_pass_rate_floor:.2%}"
            )
            return GateVerdict(
                decision=decision,
                core_pass_rate=core_pass,
                holdout_pass_rate=holdout_pass,
                divergence=divergence,
                reasons=tuple(reasons),
            )

        # Rule 4: all clear.
        reasons.append("all checks passed")
        return GateVerdict(
            decision=GateDecision.ADMIT,
            core_pass_rate=core_pass,
            holdout_pass_rate=holdout_pass,
            divergence=divergence,
            reasons=tuple(reasons),
        )


__all__ = [
    "GateConfig",
    "GateDecision",
    "GateVerdict",
    "ReplayCase",
    "SkillRegressionGate",
]
