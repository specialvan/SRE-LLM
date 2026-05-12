"""Self-learning SafetyEnvelope — audit trail feeds back into the envelope.

This closes the outermost loop in the stack. Previous rounds gave us:

    1. sre_control     — Σa=1 凸组合 (hard invariant)
    2. sre_adaptive    — Hedge learner tilts the *bias* (soft preference)
    3. sre_safety      — operator-configured envelope (hard limits)
    4. sre_math        — per-equation math primitives + observers

The missing piece: the envelope in (3) was *static*. Operators had to
guess ``low / high / max_delta`` up-front. If they chose too loose, the
envelope didn't protect; too tight, the controller got starved.

This module learns the envelope from the audit trail under a strict
**conservative ratchet** discipline:

    * auto-tighten from SAFE / UNSAFE observations (bounded by hard limits)
    * never auto-loosen — operators must call :meth:`relax`
    * quorum + hysteresis to avoid thrashing on noise
    * optional contraction-aware shrinking of ``max_delta`` when the
      plant's observed gain signals a positive-feedback regime

The closure mirrors §5.2 of the Attention Residuals paper:
*"audit + learning = determinism"*.

Public API
----------
    OutcomeLabel                  enum: SAFE / UNSAFE / UNKNOWN
    OutcomeEvidence               soft label with confidence / evidence mass
    ActionOutcome                 dataclass used by EnvelopeLearner
    LearnedSafetyEnvelope         the ratchet itself
    ContractionAwareEnvelope      wraps learned env, modulates max_delta by |gain|
    EnvelopeLearner               orchestrator: reads AuditTrail + labeler, fits periodically
    CreditAwareLabeler            downgrades UNSAFE via TemporalCreditAssigner
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

from .sre_math import TemporalCreditAssigner


# ---------------------------------------------------------------------------
# Outcome labelling
# ---------------------------------------------------------------------------

class OutcomeLabel(str, Enum):
    """Post-hoc judgement on whether an action was safe in retrospect."""
    SAFE = "safe"
    UNSAFE = "unsafe"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class OutcomeEvidence:
    """Soft post-hoc evidence for one action outcome.

    ``safety_score`` is a continuous SAFE likelihood in ``[0, 1]``:

    * ``1.0`` means fully SAFE evidence.
    * ``0.0`` means fully UNSAFE evidence.
    * ``0.5`` with ``confidence=0`` means UNKNOWN / no usable evidence.

    ``confidence`` is the evidence mass. The envelope uses
    ``safety_score * confidence`` as SAFE evidence and
    ``(1 - safety_score) * confidence`` as UNSAFE evidence. Hard labels
    are just the special cases with confidence 1.
    """

    safety_score: float
    confidence: float = 1.0
    reason: str = ""

    def __post_init__(self) -> None:
        if not (0.0 <= self.safety_score <= 1.0):
            raise ValueError("safety_score must be in [0, 1]")
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError("confidence must be in [0, 1]")

    @classmethod
    def from_label(cls, label: OutcomeLabel, *, reason: str = "") -> "OutcomeEvidence":
        if label is OutcomeLabel.SAFE:
            return cls(1.0, 1.0, reason=reason)
        if label is OutcomeLabel.UNSAFE:
            return cls(0.0, 1.0, reason=reason)
        return cls(0.5, 0.0, reason=reason)

    @classmethod
    def from_weights(
        cls,
        safe_weight: float,
        unsafe_weight: float,
        *,
        reason: str = "",
    ) -> "OutcomeEvidence":
        if safe_weight < 0 or unsafe_weight < 0:
            raise ValueError("evidence weights must be non-negative")
        total = float(safe_weight + unsafe_weight)
        if total <= 0.0:
            return cls(0.5, 0.0, reason=reason)
        confidence = min(1.0, total)
        return cls(float(safe_weight) / total, confidence, reason=reason)

    @property
    def safe_weight(self) -> float:
        return float(self.safety_score * self.confidence)

    @property
    def unsafe_weight(self) -> float:
        return float((1.0 - self.safety_score) * self.confidence)

    def hard_label(self) -> OutcomeLabel:
        if self.confidence <= 0.0:
            return OutcomeLabel.UNKNOWN
        if self.safe_weight > self.unsafe_weight:
            return OutcomeLabel.SAFE
        if self.unsafe_weight > self.safe_weight:
            return OutcomeLabel.UNSAFE
        return OutcomeLabel.UNKNOWN

    def as_dict(self) -> dict:
        return {
            "outcome": self.hard_label().value,
            "safety_score": float(self.safety_score),
            "confidence": float(self.confidence),
            "safe_weight": self.safe_weight,
            "unsafe_weight": self.unsafe_weight,
            "reason": self.reason,
        }


OutcomeLike = Union[OutcomeLabel, OutcomeEvidence, float, str]


@dataclass
class ActionOutcome:
    """One labelled observation fed into the envelope."""
    step: int
    action: np.ndarray
    outcome: OutcomeLike
    delta: Optional[np.ndarray] = None          # ``action - previous action``
    context: Dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict:
        evidence = _coerce_evidence(self.outcome)
        return {
            "step": int(self.step),
            "action": [float(a) for a in self.action],
            "outcome": evidence.hard_label().value,
            "evidence": evidence.as_dict(),
            "delta": None if self.delta is None else [float(d) for d in self.delta],
            "context": dict(self.context),
        }


# ---------------------------------------------------------------------------
# Self-learning envelope
# ---------------------------------------------------------------------------

class LearnedSafetyEnvelope:
    """Envelope whose bounds tighten themselves from labelled observations.

    The envelope carries three running states per action dimension::

        current_low[d]  ≥  hard_low[d]
        current_high[d] ≤  hard_high[d]
        current_max_delta[d] ≤ hard_max_delta[d], ≥ min_max_delta[d]

    On each :meth:`fit` call (typically triggered every N observations):

      1. If fewer than ``min_safe_samples`` SAFE records or
         ``min_safe_evidence`` weighted SAFE evidence exist, do nothing.
      2. If fewer than ``unsafe_quorum`` UNSAFE records have been seen
         *since the last fit*, do nothing.
      3. Otherwise, compute the quantile bounds of recent SAFE actions
         with a ``hysteresis`` padding, and **ratchet-tighten** the
         current bounds (never loosen).

    Loosening requires an explicit :meth:`relax` call — that's the
    single biggest safety invariant in this module.

    Selection-bias caveat
    ---------------------
    This envelope only sees actions that made it past the previous
    envelope. If the controller is never allowed to test a larger
    action, we never accumulate evidence for or against it. Hard bounds
    are therefore **set by humans** — operators choose how much
    exploration head-room exists. Within those bounds, the envelope
    narrows around the empirically-safe region.

    Parameters
    ----------
    action_dim : int
        Dimensionality of the action vector.
    hard_low, hard_high, hard_max_delta : np.ndarray
        Operator-set absolute outer bounds. The learned envelope is
        guaranteed to stay inside these.
    min_max_delta : np.ndarray, optional
        Per-dimension floor on ``max_delta`` — prevents pathological
        self-lockdown. Defaults to ``hard_max_delta / 20``.
    initial_low, initial_high, initial_max_delta : np.ndarray, optional
        Starting values. Default to the hard bounds (widest possible).
    safe_quantile : float
        Quantile of SAFE actions used to size the envelope. Typical 0.95.
    hysteresis : float
        Fractional padding added beyond the quantile. Typical 0.1 (10%).
    unsafe_quorum : int
        Minimum UNSAFE observations *since last fit* required to trigger
        tightening. Prevents single-fluke adjustments.
    min_safe_samples : int
        Minimum SAFE records in the buffer required to compute a
        trustworthy quantile.
    min_safe_evidence : float, optional
        Minimum weighted SAFE evidence required to compute a trustworthy
        quantile. Defaults to ``float(min_safe_samples)`` so hard-label
        behaviour stays unchanged while soft labels can tune record count
        and evidence mass separately.
    buffer_size : int
        Rolling window of retained SAFE observations.
    """

    def __init__(
        self,
        action_dim: int,
        hard_low: np.ndarray,
        hard_high: np.ndarray,
        hard_max_delta: np.ndarray,
        *,
        min_max_delta: Optional[np.ndarray] = None,
        initial_low: Optional[np.ndarray] = None,
        initial_high: Optional[np.ndarray] = None,
        initial_max_delta: Optional[np.ndarray] = None,
        safe_quantile: float = 0.95,
        hysteresis: float = 0.1,
        unsafe_quorum: int = 5,
        min_safe_samples: int = 20,
        min_safe_evidence: Optional[float] = None,
        buffer_size: int = 500,
    ) -> None:
        if action_dim < 1:
            raise ValueError("action_dim must be ≥ 1")
        if not (0.5 < safe_quantile < 1.0):
            raise ValueError("safe_quantile must be in (0.5, 1.0)")
        if not (0.0 <= hysteresis <= 1.0):
            raise ValueError("hysteresis must be in [0, 1]")
        if unsafe_quorum < 1:
            raise ValueError("unsafe_quorum must be ≥ 1")
        if min_safe_samples < 1:
            raise ValueError("min_safe_samples must be ≥ 1")
        if min_safe_evidence is None:
            min_safe_evidence = float(min_safe_samples)
        if min_safe_evidence < 0:
            raise ValueError("min_safe_evidence must be >= 0")
        if buffer_size < min_safe_samples:
            raise ValueError("buffer_size must be ≥ min_safe_samples")

        self.action_dim = int(action_dim)
        self.hard_low = _as_1d(hard_low, action_dim, "hard_low")
        self.hard_high = _as_1d(hard_high, action_dim, "hard_high")
        self.hard_max_delta = _as_1d(hard_max_delta, action_dim, "hard_max_delta")

        if np.any(self.hard_low > self.hard_high):
            raise ValueError("hard_low must be ≤ hard_high elementwise")
        if np.any(self.hard_max_delta <= 0):
            raise ValueError("hard_max_delta must be > 0 everywhere")

        # Minimum floor on max_delta — by default 1/20th of hard limit.
        if min_max_delta is None:
            self.min_max_delta = self.hard_max_delta / 20.0
        else:
            self.min_max_delta = _as_1d(min_max_delta, action_dim, "min_max_delta")
        if np.any(self.min_max_delta <= 0):
            raise ValueError("min_max_delta must be > 0 everywhere")
        if np.any(self.min_max_delta > self.hard_max_delta):
            raise ValueError("min_max_delta must be ≤ hard_max_delta everywhere")

        # Initial (current) bounds: default to hardest-loosest envelope.
        init_low = self.hard_low.copy() if initial_low is None else _as_1d(
            initial_low, action_dim, "initial_low",
        )
        init_high = self.hard_high.copy() if initial_high is None else _as_1d(
            initial_high, action_dim, "initial_high",
        )
        init_max_delta = self.hard_max_delta.copy() if initial_max_delta is None else _as_1d(
            initial_max_delta, action_dim, "initial_max_delta",
        )
        # Coerce initial into feasible zone.
        self.current_low = np.maximum(init_low, self.hard_low).copy()
        self.current_high = np.minimum(init_high, self.hard_high).copy()
        self.current_max_delta = np.clip(
            init_max_delta, self.min_max_delta, self.hard_max_delta,
        ).copy()

        self.safe_quantile = float(safe_quantile)
        self.hysteresis = float(hysteresis)
        self.unsafe_quorum = int(unsafe_quorum)
        self.min_safe_samples = int(min_safe_samples)
        self.min_safe_evidence = float(min_safe_evidence)
        self.buffer_size = int(buffer_size)

        # Rolling state.
        self._safe_actions: List[np.ndarray] = []
        self._safe_weights: List[float] = []
        self._safe_deltas: List[np.ndarray] = []
        self._safe_delta_weights: List[float] = []
        self._unsafe_since_fit = 0.0
        self._last_action: Optional[np.ndarray] = None
        self._violation_count = 0
        self._fit_history: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------ apply
    def apply(self, action: np.ndarray) -> Tuple[np.ndarray, Dict[str, Any]]:
        """Clip ``action`` to the current learned envelope.

        Same signature as :class:`sre_safety.SafetyEnvelope.apply` so
        this class is drop-in compatible.
        """
        action = _as_1d(action, self.action_dim, "action")
        original = action.copy()
        clipped = np.clip(original, self.current_low, self.current_high)
        rate_limited = False
        if self._last_action is not None:
            lo = self._last_action - self.current_max_delta
            hi = self._last_action + self.current_max_delta
            prev_clip = clipped.copy()
            clipped = np.clip(clipped, lo, hi)
            rate_limited = not np.allclose(prev_clip, clipped)
        changed = not np.allclose(original, clipped)
        if changed:
            self._violation_count += 1
        self._last_action = clipped.copy()
        return clipped, {
            "original": original,
            "clipped": changed,
            "rate_limited": rate_limited,
            "violation_count": self._violation_count,
            "current_low": self.current_low.copy(),
            "current_high": self.current_high.copy(),
            "current_max_delta": self.current_max_delta.copy(),
        }

    # ------------------------------------------------------------------ observe
    def observe(
        self,
        action: np.ndarray,
        outcome: OutcomeLike,
        *,
        delta: Optional[np.ndarray] = None,
        step: Optional[int] = None,      # kept for API symmetry; not used internally
    ) -> None:
        """Record one (action, outcome) pair.

        ``delta`` — if provided, is used to learn ``max_delta``. Callers
        that don't have a previous action (e.g. the very first tick)
        can simply leave it as ``None``.

        Dual accounting
        ----------------
        Soft labels can contribute to both sides of the learning gate.
        For example, ``OutcomeEvidence(safety_score=0.3, confidence=1.0)``
        adds ``0.3`` SAFE weight to the quantile buffer and ``0.7`` UNSAFE
        weight to the quorum counter. ``UNKNOWN`` evidence uses
        ``confidence=0`` and is therefore a no-op.
        """
        del step
        action = _as_1d(action, self.action_dim, "action")
        evidence = _coerce_evidence(outcome)
        safe_weight = evidence.safe_weight
        unsafe_weight = evidence.unsafe_weight
        if safe_weight > 0.0:
            self._safe_actions.append(action.copy())
            self._safe_weights.append(safe_weight)
            if delta is not None:
                self._safe_deltas.append(
                    np.abs(_as_1d(delta, self.action_dim, "delta")).copy()
                )
                self._safe_delta_weights.append(safe_weight)
            # Drop oldest when over budget.
            while len(self._safe_actions) > self.buffer_size:
                self._safe_actions.pop(0)
                self._safe_weights.pop(0)
            while len(self._safe_deltas) > self.buffer_size:
                self._safe_deltas.pop(0)
                self._safe_delta_weights.pop(0)
        if unsafe_weight > 0.0:
            self._unsafe_since_fit += unsafe_weight
        # UNKNOWN → intentional no-op: we refuse to take a stand without evidence.

    # ------------------------------------------------------------------ fit
    def fit(self) -> Dict[str, Any]:
        """Run one ratchet-tightening step.

        Returns a summary dictionary describing what happened. Always
        appended to :meth:`fit_history`.
        """
        safe_evidence = float(sum(self._safe_weights))
        summary: Dict[str, Any] = {
            "n_safe_records": len(self._safe_actions),
            "n_safe": len(self._safe_actions),
            "safe_evidence": safe_evidence,
            "min_safe_samples": self.min_safe_samples,
            "min_safe_evidence": self.min_safe_evidence,
            "n_unsafe_since_fit": self._unsafe_since_fit,
            "unsafe_evidence_since_fit": float(self._unsafe_since_fit),
            "tightened_high": False,
            "tightened_low": False,
            "tightened_max_delta": False,
        }
        reasons: List[str] = []
        if len(self._safe_actions) < self.min_safe_samples:
            reasons.append("insufficient_safe_samples")
        if safe_evidence + 1e-12 < self.min_safe_evidence:
            reasons.append("insufficient_safe_evidence")
        if self._unsafe_since_fit + 1e-12 < self.unsafe_quorum:
            reasons.append("no_unsafe_quorum")
        if reasons:
            summary["reason"] = "+".join(reasons)
            summary["reasons"] = reasons
            self._fit_history.append(summary)
            return summary

        arr = np.stack(self._safe_actions, axis=0)       # shape (N, D)
        safe_weights = np.asarray(self._safe_weights, dtype=float)
        q_hi = _weighted_quantile(arr, safe_weights, self.safe_quantile)
        q_lo = _weighted_quantile(arr, safe_weights, 1.0 - self.safe_quantile)
        # Hysteresis padding: proportional to the per-dim safe-range.
        width = np.maximum(q_hi - q_lo, 1e-9)
        pad = width * (self.hysteresis / 2.0)
        proposed_hi = q_hi + pad
        proposed_lo = q_lo - pad
        # Ratchet: only tighten; never below hard or invert interval.
        new_high = np.minimum(self.current_high, proposed_hi)
        new_high = np.maximum(new_high, self.hard_low)       # never below hard_low
        new_high = np.minimum(new_high, self.hard_high)
        new_low = np.maximum(self.current_low, proposed_lo)
        new_low = np.minimum(new_low, self.hard_high)
        new_low = np.maximum(new_low, self.hard_low)
        # Keep the interval non-degenerate: high ≥ low.
        new_high = np.maximum(new_high, new_low + 1e-9)

        if np.any(new_high < self.current_high - 1e-12):
            summary["tightened_high"] = True
        if np.any(new_low > self.current_low + 1e-12):
            summary["tightened_low"] = True
        self.current_high = new_high
        self.current_low = new_low

        # max_delta: same ratchet rule on safe-delta quantiles.
        if self._safe_deltas:
            d_arr = np.stack(self._safe_deltas, axis=0)
            d_weights = np.asarray(self._safe_delta_weights, dtype=float)
            q_md = _weighted_quantile(d_arr, d_weights, self.safe_quantile) * (
                1.0 + self.hysteresis
            )
            new_md = np.minimum(self.current_max_delta, q_md)
            new_md = np.clip(new_md, self.min_max_delta, self.hard_max_delta)
            if np.any(new_md < self.current_max_delta - 1e-12):
                summary["tightened_max_delta"] = True
            self.current_max_delta = new_md

        summary["current_low"] = self.current_low.copy()
        summary["current_high"] = self.current_high.copy()
        summary["current_max_delta"] = self.current_max_delta.copy()
        # Reset quorum counter — we've acted on it.
        self._unsafe_since_fit = 0.0
        self._fit_history.append(summary)
        return summary

    # ------------------------------------------------------------------ relax
    def relax(
        self,
        *,
        factor: float = 1.5,
        to_hard: bool = False,
        dim: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Operator-invoked widening of the envelope.

        Parameters
        ----------
        factor : float
            Multiplicative widening applied to the current half-interval
            and to ``max_delta``. Ignored if ``to_hard=True``.
        to_hard : bool
            If ``True``, jump straight to the hard bounds regardless of
            ``factor``.
        dim : int, optional
            Restrict the relaxation to one action dimension. Default:
            all dimensions.
        """
        if factor < 1.0:
            raise ValueError("factor must be ≥ 1.0 (relax widens)")
        sel: Sequence[int] = (
            range(self.action_dim) if dim is None else (dim,)
        )
        if dim is not None and not (0 <= dim < self.action_dim):
            raise ValueError("dim out of range")
        before = {
            "low": self.current_low.copy(),
            "high": self.current_high.copy(),
            "max_delta": self.current_max_delta.copy(),
        }
        for d in sel:
            if to_hard:
                self.current_low[d] = self.hard_low[d]
                self.current_high[d] = self.hard_high[d]
                self.current_max_delta[d] = self.hard_max_delta[d]
                continue
            centre = 0.5 * (self.current_low[d] + self.current_high[d])
            half = 0.5 * (self.current_high[d] - self.current_low[d]) * factor
            self.current_low[d] = max(self.hard_low[d], centre - half)
            self.current_high[d] = min(self.hard_high[d], centre + half)
            self.current_max_delta[d] = min(
                self.hard_max_delta[d],
                self.current_max_delta[d] * factor,
            )
        # Relax also resets the quorum counter — safe to start learning again.
        self._unsafe_since_fit = 0.0
        return {
            "before": before,
            "after": {
                "low": self.current_low.copy(),
                "high": self.current_high.copy(),
                "max_delta": self.current_max_delta.copy(),
            },
            "to_hard": to_hard,
            "factor": factor,
            "dim": dim,
        }

    # ------------------------------------------------------------------ inspection
    def current_bounds(self) -> Dict[str, np.ndarray]:
        return {
            "low": self.current_low.copy(),
            "high": self.current_high.copy(),
            "max_delta": self.current_max_delta.copy(),
        }

    def fit_history(self) -> List[Dict[str, Any]]:
        return list(self._fit_history)

    @property
    def violation_count(self) -> int:
        return self._violation_count


def _as_1d(x: np.ndarray, n: int, name: str) -> np.ndarray:
    """Coerce ``x`` to a 1D float ndarray of length ``n`` or raise."""
    arr = np.asarray(x, dtype=float)
    if arr.ndim == 0:
        arr = np.full(n, float(arr))
    if arr.shape != (n,):
        raise ValueError(f"{name} must have shape ({n},), got {arr.shape}")
    return arr


def _coerce_evidence(outcome: OutcomeLike) -> OutcomeEvidence:
    """Convert hard labels, strings, or scalar soft labels to evidence."""
    if isinstance(outcome, OutcomeEvidence):
        return outcome
    if isinstance(outcome, OutcomeLabel):
        return OutcomeEvidence.from_label(outcome)
    if isinstance(outcome, str):
        return OutcomeEvidence.from_label(OutcomeLabel(outcome))
    if isinstance(outcome, (int, float, np.integer, np.floating)):
        return OutcomeEvidence(float(outcome), 1.0)
    raise TypeError(f"unsupported outcome type: {type(outcome)!r}")


def _weighted_quantile(values: np.ndarray, weights: np.ndarray, q: float) -> np.ndarray:
    """Return per-column weighted quantiles.

    ``values`` is ``(n, d)`` and ``weights`` is ``(n,)``. The interpolation
    uses weighted CDF midpoints, which keeps low-confidence outliers from
    dominating the learned envelope while preserving the hard-label
    behaviour when all weights are 1.
    """
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    if values.ndim != 2:
        raise ValueError("values must have shape (n, d)")
    if values.shape[0] == 0:
        raise ValueError("values must contain at least one row")
    if weights.shape != (values.shape[0],):
        raise ValueError("weights length must match values")
    if np.any(weights < 0):
        raise ValueError("weights must be non-negative")
    total = weights.sum()
    if total <= 0:
        raise ValueError("weights must sum to > 0")

    out = np.empty(values.shape[1], dtype=float)
    for d in range(values.shape[1]):
        order = np.argsort(values[:, d])
        xs = values[order, d]
        ws = weights[order]
        cdf = (np.cumsum(ws) - 0.5 * ws) / total
        out[d] = np.interp(q, cdf, xs, left=xs[0], right=xs[-1])
    return out


# ---------------------------------------------------------------------------
# Contraction-aware modulation of max_delta
# ---------------------------------------------------------------------------

class ContractionAwareEnvelope:
    """Shrinks ``max_delta`` on-the-fly when the plant is in a positive-feedback regime.

    Given an inner :class:`LearnedSafetyEnvelope` and a callable that
    returns the current empirical contraction gain (typically
    ``JacobianContractionMonitor.gain``), we scale ``max_delta`` by

        scale = clip(target_gain / max(|gain|, target_gain), min_scale, 1.0)

    If the gain is below ``target_gain`` (stable), ``scale = 1`` and the
    inner envelope's ``max_delta`` is used as-is. If the gain climbs
    above ``target_gain``, we temporarily shrink ``max_delta`` by the
    scale factor — a conservative "slow down, plant is hot" response.
    The inner envelope's state is untouched; this wrapper only narrows
    during application.

    ``apply`` is serialized by default because it temporarily overrides
    ``inner.current_max_delta`` while delegating to the inner envelope.
    Pass ``thread_safe=False`` only when calls are externally serialized.
    """

    def __init__(
        self,
        inner: LearnedSafetyEnvelope,
        gain_provider: Callable[[], Optional[float]],
        *,
        target_gain: float = 1.0,
        min_scale: float = 0.1,
        thread_safe: bool = True,
    ) -> None:
        if target_gain <= 0:
            raise ValueError("target_gain must be > 0")
        if not (0 < min_scale <= 1):
            raise ValueError("min_scale must be in (0, 1]")
        self.inner = inner
        self.gain_provider = gain_provider
        self.target_gain = float(target_gain)
        self.min_scale = float(min_scale)
        self._last_scale = 1.0
        # RLock chosen over Lock because a future labeler that re-enters apply()
        # via the observe() path would deadlock under a non-reentrant lock.
        # See docs/adr/0001-contraction-wrapper-uses-rlock.md.
        self._lock = threading.RLock() if thread_safe else None

    # ---------------------------------------------------- apply
    def apply(self, action: np.ndarray) -> Tuple[np.ndarray, Dict[str, Any]]:
        if self._lock is not None:
            with self._lock:
                return self._apply_unlocked(action)
        return self._apply_unlocked(action)

    def _apply_unlocked(self, action: np.ndarray) -> Tuple[np.ndarray, Dict[str, Any]]:
        scale = self._current_scale()
        self._last_scale = scale
        # Temporarily tighten max_delta inside the inner envelope.
        saved_md = self.inner.current_max_delta.copy()
        self.inner.current_max_delta = np.maximum(
            saved_md * scale, self.inner.min_max_delta,
        )
        try:
            clipped, info = self.inner.apply(action)
        finally:
            self.inner.current_max_delta = saved_md
        info["contraction_scale"] = scale
        info["contraction_gain"] = self.gain_provider()
        return clipped, info

    def _current_scale(self) -> float:
        g = self.gain_provider()
        if g is None:
            return 1.0
        mag = float(abs(g))
        if mag <= self.target_gain:
            return 1.0
        return max(self.min_scale, self.target_gain / mag)

    # ---------------------------------------------------- observe / fit pass-through
    def observe(self, *args, **kwargs) -> None:
        if self._lock is not None:
            with self._lock:
                self.inner.observe(*args, **kwargs)
                return
        self.inner.observe(*args, **kwargs)

    def fit(self) -> Dict[str, Any]:
        if self._lock is not None:
            with self._lock:
                return self.inner.fit()
        return self.inner.fit()

    def current_bounds(self) -> Dict[str, np.ndarray]:
        if self._lock is not None:
            with self._lock:
                return self._current_bounds_unlocked()
        return self._current_bounds_unlocked()

    def _current_bounds_unlocked(self) -> Dict[str, np.ndarray]:
        bounds = self.inner.current_bounds()
        bounds["effective_max_delta"] = bounds["max_delta"] * self._last_scale
        return bounds


# ---------------------------------------------------------------------------
# Orchestrator: EnvelopeLearner
# ---------------------------------------------------------------------------

Labeler = Callable[[Dict[str, Any]], OutcomeLike]


@dataclass
class LearnerStats:
    ingested: int = 0
    safe: int = 0
    unsafe: int = 0
    unknown: int = 0
    soft: int = 0
    safe_evidence: float = 0.0
    unsafe_evidence: float = 0.0
    fits: int = 0

    def as_dict(self) -> dict:
        return self.__dict__.copy()


class EnvelopeLearner:
    """Pull (action, context) records from an AuditTrail, label them, fit.

    The orchestrator is intentionally lightweight — it does not own the
    audit trail or the envelope; it just wires them up. A production
    deployment will typically call :meth:`ingest` on each new batch of
    audit records, then :meth:`maybe_fit` every N records (or on a
    timer).

    Parameters
    ----------
    envelope : LearnedSafetyEnvelope or ContractionAwareEnvelope
        The envelope to teach.
    labeler : Callable[[record dict], OutcomeLabel]
        Pure function from an audit record context dict to a label.
        Domain-specific — e.g. an autoscaler labeler might return
        ``SAFE`` iff post-action P99 stayed under SLO and error budget
        did not burn.
    fit_every : int
        Fit cadence (every N ingested records).
    """

    def __init__(
        self,
        envelope,                               # LearnedSafetyEnvelope | ContractionAwareEnvelope
        labeler: Labeler,
        *,
        fit_every: int = 50,
    ) -> None:
        if fit_every < 1:
            raise ValueError("fit_every must be ≥ 1")
        self.envelope = envelope
        self.labeler = labeler
        self.fit_every = int(fit_every)
        self.stats = LearnerStats()

    def ingest(
        self,
        action: np.ndarray,
        context: Dict[str, Any],
        *,
        delta: Optional[np.ndarray] = None,
        step: Optional[int] = None,
    ) -> OutcomeEvidence:
        label = self.labeler(context)
        evidence = _coerce_evidence(label)
        self.envelope.observe(action, evidence, delta=delta, step=step)
        self.stats.ingested += 1
        hard = evidence.hard_label()
        if hard is OutcomeLabel.SAFE:
            self.stats.safe += 1
        elif hard is OutcomeLabel.UNSAFE:
            self.stats.unsafe += 1
        else:
            self.stats.unknown += 1
        if 0.0 < evidence.confidence < 1.0 or 0.0 < evidence.safety_score < 1.0:
            self.stats.soft += 1
        self.stats.safe_evidence += evidence.safe_weight
        self.stats.unsafe_evidence += evidence.unsafe_weight
        if self.stats.ingested % self.fit_every == 0:
            self.envelope.fit()
            self.stats.fits += 1
        return evidence


class CreditAwareLabeler:
    """Downgrade UNSAFE evidence when temporal credit points elsewhere.

    A post-hoc SLO breach is not always caused by the current control
    action. If :class:`TemporalCreditAssigner` says most blame belongs
    to exogenous signals (for example upstream traffic), this wrapper
    reduces the UNSAFE evidence before it reaches the envelope. The
    action still remains auditable; it simply does not cause the safety
    ratchet to overreact to the wrong root cause.
    """

    def __init__(
        self,
        base_labeler: Labeler,
        credit_assigner: TemporalCreditAssigner,
        controllable_signals: Sequence[str],
        *,
        incident_tick_key: str = "tick",
        window: int = 50,
        top_k: Optional[int] = None,
        min_total_score: float = 1e-12,
    ) -> None:
        if not controllable_signals:
            raise ValueError("controllable_signals must not be empty")
        if window < 1:
            raise ValueError("window must be >= 1")
        if top_k is not None and top_k < 1:
            raise ValueError("top_k must be >= 1 when provided")
        if min_total_score < 0:
            raise ValueError("min_total_score must be non-negative")
        self.base_labeler = base_labeler
        self.credit_assigner = credit_assigner
        self.controllable_signals = set(controllable_signals)
        self.incident_tick_key = incident_tick_key
        self.window = int(window)
        self.top_k = top_k
        self.min_total_score = float(min_total_score)
        self._last_adjustment: Dict[str, float] = {}

    def __call__(self, context: Dict[str, Any]) -> OutcomeEvidence:
        evidence = _coerce_evidence(self.base_labeler(context))
        self._last_adjustment = {
            "controllable_ratio": 1.0,
            "total_credit": 0.0,
            "unsafe_before": evidence.unsafe_weight,
            "unsafe_after": evidence.unsafe_weight,
        }
        if evidence.unsafe_weight <= 0.0:
            return evidence

        if self.incident_tick_key not in context:
            return evidence
        incident_tick = int(context[self.incident_tick_key])
        entries = self.credit_assigner.attribute(
            incident_tick=incident_tick,
            window=self.window,
            top_k=self.top_k,
        )
        total = float(sum(max(0.0, e.score) for e in entries))
        if total <= self.min_total_score:
            return evidence

        controllable = float(sum(
            max(0.0, e.score)
            for e in entries
            if e.signal_name in self.controllable_signals
        ))
        ratio = max(0.0, min(1.0, controllable / total))
        adjusted = OutcomeEvidence.from_weights(
            evidence.safe_weight,
            evidence.unsafe_weight * ratio,
            reason=f"credit_adjusted:{ratio:.3f}",
        )
        self._last_adjustment = {
            "controllable_ratio": ratio,
            "total_credit": total,
            "controllable_credit": controllable,
            "unsafe_before": evidence.unsafe_weight,
            "unsafe_after": adjusted.unsafe_weight,
        }
        return adjusted

    def last_adjustment(self) -> Dict[str, float]:
        return dict(self._last_adjustment)


__all__ = [
    "OutcomeLabel",
    "OutcomeEvidence",
    "OutcomeLike",
    "ActionOutcome",
    "LearnedSafetyEnvelope",
    "ContractionAwareEnvelope",
    "Labeler",
    "LearnerStats",
    "EnvelopeLearner",
    "CreditAwareLabeler",
]
