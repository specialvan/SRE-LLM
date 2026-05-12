"""Shadow verifier · PR-007.

Refined spec: ``skill-research/refined/PR-007-skill-shadow-verifier-refined.md``.

Design principle: the verifier is **harness-driven**. Callers provide
a :class:`VerificationHarness` that knows how to produce (baseline_action,
active_action, divergence) for a given ``ReplayCase`` and a variant's
``targets``. The verifier itself handles:

* iterating the suite + holdout,
* counting pass/fail,
* deriving :class:`VerifierFinding` on failures,
* emitting ``new_tests`` that re-assert the baseline behaviour,
* building a :class:`VerifyResult` with full diagnostics.

A convenience :class:`CombinerHarness` is provided for the common case
where callers want to plug a :class:`WeightedConvexCombiner` directly.

Requirements:

* REQ-VRF-001 · pass ⇔ all cases pass
* REQ-VRF-002 · findings non-empty on fail
* REQ-VRF-008 · parallel when suite ≥ 4 (we keep it serial in v1 but
  the shape is ready for a thread pool swap)
* REQ-VRF-009 · holdout pass-rate computed separately, does NOT feed
  finding generation
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import (
    Any,
    Callable,
    Iterable,
    List,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    Tuple,
)

import numpy as np

from attention_residuals.sre_control import (
    SignalSpec,
    WeightedConvexCombiner,
)
from attention_residuals.sre_safety import CounterfactualExplainer
from attention_residuals.skill.types import (
    PatchField,
    PatchTarget,
    SkillVariant,
    VerifierFinding,
    compute_patch_id,
)

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------

PassCheck = Callable[[np.ndarray, np.ndarray, Mapping[str, Any]], bool]


@dataclass(frozen=True)
class ReplayCase:
    """One replayable scenario.

    ``signals`` are the signal names the harness will evaluate. ``values``
    is one proposed action vector per signal. ``query`` is the combiner
    query. ``expected_pass`` is an optional custom check on
    ``(active_action, baseline_action, context)``; if ``None`` the default
    "active ≈ baseline within tol" is used.
    """

    case_id: str
    signals: Tuple[str, ...]
    query: np.ndarray
    values: Tuple[np.ndarray, ...]
    context: Mapping[str, Any] = field(default_factory=dict)
    expected_pass: Optional[PassCheck] = None
    tolerance: float = 0.1


@dataclass(frozen=True)
class CaseResult:
    """Per-case harness output consumed by the verifier."""

    case_id: str
    baseline_action: np.ndarray
    active_action: np.ndarray
    baseline_weights: np.ndarray
    active_weights: np.ndarray
    divergence: float
    passed: bool
    context: Mapping[str, Any]

    def as_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "baseline_action": [float(x) for x in self.baseline_action],
            "active_action": [float(x) for x in self.active_action],
            "divergence": float(self.divergence),
            "passed": bool(self.passed),
        }


class VerificationHarness(Protocol):
    """Plug-in that knows how to evaluate a single case."""

    def evaluate(
        self,
        case: ReplayCase,
        variant: SkillVariant,
    ) -> CaseResult: ...

    # Optional hook for counterfactual analysis; harness can return
    # ``None`` and the verifier will fall back to a simpler finding.
    def counterfactuals(
        self,
        case: ReplayCase,
        variant: SkillVariant,
    ) -> Optional[Sequence[Tuple[int, np.ndarray]]]:
        """Return ``(signal_index, action_if_signal_absent)`` pairs."""
        ...


@dataclass
class VerifierConfig:
    divergence_saturation: float = 0.5
    case_timeout_seconds: float = 1.0  # reserved for thread-pool version
    parallel_threshold: int = 4
    # Finding severity floor — filter noise.
    min_severity: float = 0.0


@dataclass(frozen=True)
class VerifyResult:
    variant_id: str
    pass_fail: bool
    findings: Tuple[VerifierFinding, ...]
    new_tests: Tuple[ReplayCase, ...]
    diagnostics: Mapping[str, float]
    case_results: Tuple[CaseResult, ...]


# ---------------------------------------------------------------------------
# Shadow verifier
# ---------------------------------------------------------------------------


class SkillShadowVerifier:
    """Evaluate a :class:`SkillVariant` against a suite of replay cases.

    The verifier delegates the actual "shadow" computation to the
    :class:`VerificationHarness`; the harness is the only component that
    needs to know about :mod:`sre_safety` ShadowRunner or any other
    concrete combiner plumbing.
    """

    def __init__(
        self,
        harness: VerificationHarness,
        config: Optional[VerifierConfig] = None,
    ) -> None:
        self._harness = harness
        self._cfg = config or VerifierConfig()
        self._derived_ids: set[str] = set()

    # -------------------------------------------------- public API

    def verify(
        self,
        variant: SkillVariant,
        suite: Sequence[ReplayCase],
        holdout: Optional[Sequence[ReplayCase]] = None,
    ) -> VerifyResult:
        case_results = self._run_suite(variant, suite)
        passed_count = sum(1 for r in case_results if r.passed)
        pass_fail = passed_count == len(suite)

        # holdout is evaluated independently; findings are NOT derived
        # from holdout failures (REQ-VRF-009).
        holdout_results = self._run_suite(variant, holdout or ())
        holdout_passed = sum(1 for r in holdout_results if r.passed)

        findings: List[VerifierFinding] = []
        new_tests: List[ReplayCase] = []
        for case, result in zip(suite, case_results):
            if result.passed:
                continue
            finding = self._build_finding(variant, case, result)
            if finding is not None:
                findings.append(finding)
            nt = self._derive_new_test(case, result)
            if nt is not None:
                new_tests.append(nt)

        diagnostics = {
            "train_pass_rate": passed_count / max(1, len(suite)),
            "holdout_pass_rate": holdout_passed / max(1, len(holdout or [])) if holdout else 1.0,
            "avg_divergence": float(
                np.mean([r.divergence for r in case_results]) if case_results else 0.0
            ),
            "max_divergence": float(
                max((r.divergence for r in case_results), default=0.0)
            ),
        }

        return VerifyResult(
            variant_id=variant.variant_id,
            pass_fail=pass_fail,
            findings=tuple(findings),
            new_tests=tuple(new_tests),
            diagnostics=diagnostics,
            case_results=tuple(case_results),
        )

    # -------------------------------------------------- internals

    def _run_suite(
        self, variant: SkillVariant, suite: Sequence[ReplayCase]
    ) -> List[CaseResult]:
        # v1 runs serial; shape is ready for a ThreadPoolExecutor once
        # we observe bottlenecks (see refined/PR-007 §4).
        return [self._run_one(variant, case) for case in suite]

    def _run_one(self, variant: SkillVariant, case: ReplayCase) -> CaseResult:
        try:
            return self._harness.evaluate(case, variant)
        except Exception as exc:  # pragma: no cover — defensive
            _LOGGER.exception("harness crashed on %s", case.case_id)
            # Synthesize a deterministic failing result so the pipeline
            # sees the failure rather than propagating the exception.
            action_shape = case.values[0].shape if case.values else (1,)
            return CaseResult(
                case_id=case.case_id,
                baseline_action=np.zeros(action_shape),
                active_action=np.zeros(action_shape),
                baseline_weights=np.zeros(len(case.signals)),
                active_weights=np.zeros(len(case.signals)),
                divergence=float("inf"),
                passed=False,
                context={"harness_error": repr(exc)},
            )

    def _build_finding(
        self,
        variant: SkillVariant,
        case: ReplayCase,
        result: CaseResult,
    ) -> Optional[VerifierFinding]:
        """Return a :class:`VerifierFinding` describing the failure."""
        # Try counterfactuals first.
        offending: List[str] = []
        direction: dict[str, int] = {}

        cf = None
        try:
            cf = self._harness.counterfactuals(case, variant)
        except Exception as exc:  # pragma: no cover
            _LOGGER.debug("counterfactuals failed for %s: %s", case.case_id, exc)

        if cf is not None:
            # A signal "explains" the failure when removing it moves the
            # active action substantially closer to the baseline.
            baseline = result.baseline_action
            active = result.active_action
            base_div = _l2(active - baseline) + 1e-9
            for signal_index, alt_action in cf:
                if signal_index < 0 or signal_index >= len(case.signals):
                    continue
                alt_div = _l2(alt_action - baseline)
                if alt_div < 0.5 * base_div:
                    offending.append(case.signals[signal_index])

        if not offending:
            # Fallback: blame every signal that the variant touches.
            offending = [t.signal_name for t in variant.targets]

        # Direction sign: for each offending signal, if the variant raises
        # a BIAS/FLOOR, we suggest lowering it; same for the ceiling.
        targets_by_signal = {t.signal_name: t for t in variant.targets}
        for name in offending:
            t = targets_by_signal.get(name)
            if t is None:
                direction[name] = 0
                continue
            direction[name] = -1 if t.delta > 0 else 1

        severity = float(
            min(1.0, result.divergence / max(self._cfg.divergence_saturation, 1e-9))
        )
        if severity < self._cfg.min_severity:
            return None

        finding_id = compute_patch_id(
            variant.targets,
            {"case": case.case_id, "severity": severity},
        )
        return VerifierFinding(
            finding_id=finding_id,
            offending_signals=tuple(dict.fromkeys(offending)),
            suggested_direction=direction,
            severity=severity,
            diagnostics={
                "divergence": result.divergence,
                "case_tolerance": float(case.tolerance),
            },
        )

    def _derive_new_test(
        self, case: ReplayCase, result: CaseResult
    ) -> Optional[ReplayCase]:
        """Create a new test that re-asserts the baseline behaviour."""
        nt_id = f"{case.case_id}::baseline"
        if nt_id in self._derived_ids:
            return None
        self._derived_ids.add(nt_id)

        baseline = np.asarray(result.baseline_action, dtype=float)

        def _accept_baseline(
            action: np.ndarray,
            baseline_action: np.ndarray,
            ctx: Mapping[str, Any],
            tol: float = case.tolerance,
            _captured_baseline: np.ndarray = baseline,
        ) -> bool:
            # Compare against the captured baseline (not the runtime one);
            # the test is "whoever takes over must stay close to what the
            # original baseline would have done".
            return float(np.linalg.norm(action - _captured_baseline)) < tol

        return ReplayCase(
            case_id=nt_id,
            signals=case.signals,
            query=case.query.copy(),
            values=tuple(v.copy() for v in case.values),
            context=dict(case.context),
            expected_pass=_accept_baseline,
            tolerance=case.tolerance,
        )


# ---------------------------------------------------------------------------
# Convenience harness using WeightedConvexCombiner
# ---------------------------------------------------------------------------


class CombinerHarness:
    """Adapter that uses a real :class:`WeightedConvexCombiner` for the
    baseline + a patched clone for the active run.

    Usage::

        baseline = WeightedConvexCombiner([...signals...], query_dim=3)
        harness  = CombinerHarness(baseline)
        verifier = SkillShadowVerifier(harness)

    The harness takes the baseline's signal specs and applies the
    variant's :class:`PatchTarget`s on top to produce the active combiner.
    """

    def __init__(
        self,
        baseline: WeightedConvexCombiner,
        tolerance: float = 0.1,
    ) -> None:
        self._baseline = baseline
        self._tolerance = tolerance

    # -------------------------------------------------- harness API

    def evaluate(
        self,
        case: ReplayCase,
        variant: SkillVariant,
    ) -> CaseResult:
        if len(case.values) != len(self._baseline.signals):
            raise ValueError(
                f"case values length {len(case.values)} mismatches combiner "
                f"signals length {len(self._baseline.signals)}"
            )

        base_action, base_weights = self._baseline.combine(
            case.query, list(case.values)
        )
        active = self._build_active(variant)
        active_action, active_weights = active.combine(
            case.query, list(case.values)
        )
        divergence = float(_l2(active_action - base_action))
        passed = (
            case.expected_pass(active_action, base_action, case.context)
            if case.expected_pass is not None
            else divergence <= case.tolerance
        )
        return CaseResult(
            case_id=case.case_id,
            baseline_action=base_action,
            active_action=active_action,
            baseline_weights=base_weights,
            active_weights=active_weights,
            divergence=divergence,
            passed=bool(passed),
            context=dict(case.context),
        )

    def counterfactuals(
        self,
        case: ReplayCase,
        variant: SkillVariant,
    ) -> Optional[Sequence[Tuple[int, np.ndarray]]]:
        active = self._build_active(variant)
        explainer = CounterfactualExplainer(active)
        try:
            factual_action, _ = active.combine(case.query, list(case.values))
            results = explainer.explain(
                query=case.query,
                values=list(case.values),
                factual_action=factual_action,
            )
        except Exception:  # pragma: no cover - defensive
            return None
        return [(r.signal_index, r.alternate_action) for r in results]

    # -------------------------------------------------- build active

    def _build_active(self, variant: SkillVariant) -> WeightedConvexCombiner:
        """Build a clone of the baseline combiner with variant targets applied."""
        base_specs = {s.name: s for s in self._baseline.signals}
        tweaks: dict[str, dict[str, float]] = {}
        for t in variant.targets:
            slot = tweaks.setdefault(t.signal_name, {})
            slot[t.field.value] = slot.get(t.field.value, 0.0) + t.delta

        new_signals: List[SignalSpec] = []
        for spec in self._baseline.signals:
            adjust = tweaks.get(spec.name, {})
            floor = max(0.0, min(1.0, spec.floor + adjust.get("floor", 0.0)))
            ceiling = max(floor, min(1.0, spec.ceiling + adjust.get("ceiling", 0.0)))
            bias = spec.bias + adjust.get("bias", 0.0)
            new_signals.append(
                SignalSpec(
                    name=spec.name,
                    floor=floor,
                    ceiling=ceiling,
                    bias=bias,
                )
            )

        # Apply a single "temperature" tweak at the combiner level if
        # the variant asked for one; any signal-scoped temperature delta
        # is summed into a single scaling.
        t_delta = sum(
            t.delta
            for t in variant.targets
            if t.field is PatchField.TEMPERATURE
        )
        temperature = max(1e-6, self._baseline.temperature + t_delta)

        combiner = WeightedConvexCombiner(
            new_signals,
            query_dim=self._baseline.query_dim,
            temperature=temperature,
            rng_seed=None,
        )
        # Copy the W_K so active and baseline see the same "learned"
        # query-to-key projection.
        combiner.W_K = self._baseline.W_K.copy()
        return combiner


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _l2(x: np.ndarray) -> float:
    return float(np.linalg.norm(x))


__all__ = [
    "CaseResult",
    "CombinerHarness",
    "PassCheck",
    "ReplayCase",
    "SkillShadowVerifier",
    "VerificationHarness",
    "VerifierConfig",
    "VerifyResult",
]
