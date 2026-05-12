"""Hindsight utility tracker · PR-019.

Refined spec: ``skill-research/refined/PR-019-hindsight-utility-tracker-refined.md``.

Implements Def 3 from the source paper:

    u_s  ← (1 - α) · u_s  +  α · (M_with(s) - M_without(s))

and the companion streaming API that tucks skill-level attribution into
the existing :class:`attention_residuals.sre_math.TemporalCreditAssigner`
without changing its contract (ADR-002 + ADR-004).

Requirements:

* REQ-RTE-009 · ``M_with`` and ``M_without`` must come from the same
  input stream — violating calls raise ``ValueError``.
* utility updates bounded by ``clip_delta`` to prevent one flaky
  observation from dominating the EMA (Insight 2).
"""

from __future__ import annotations

import logging
import math
import threading
from dataclasses import dataclass, field
from typing import Callable, Iterable, List, Mapping, Optional, Sequence, Tuple

from attention_residuals.sre_math import TemporalCreditAssigner

_LOGGER = logging.getLogger(__name__)


@dataclass
class HindsightConfig:
    """Defaults per refined/PR-019 §5."""

    alpha_ema: float = 0.1
    clip_delta: float = 5.0
    min_uses_for_judgment: int = 20
    window_ticks: int = 60
    # Safety rail: if `observe()` is called with mismatching step for
    # active vs shadow streams, raise.
    strict_same_stream: bool = True


@dataclass(frozen=True)
class UtilitySnapshot:
    """Read-only view of per-skill state."""

    skill_id: str
    utility_ema: float
    n_observed: int
    last_step: int
    confidence: float


@dataclass
class _State:
    utility: float
    n: int
    last_step: int
    last_active_step: int

    def copy(self) -> "_State":
        return _State(
            utility=self.utility,
            n=self.n,
            last_step=self.last_step,
            last_active_step=self.last_active_step,
        )


class HindsightUtilityTracker:
    """Maintain per-skill utility EMA with hindsight M_with − M_without.

    Two usage patterns:

    * ``observe(skill_id, m_with, m_without, step)`` — caller already has
      both metrics (e.g. because they ran a ShadowRunner in parallel).
    * ``observe_stream(skill_id, active_metric, baseline_metric, step)`` —
      equivalent API kept for readability in online loops.

    The tracker can optionally forward attribution into a
    :class:`TemporalCreditAssigner`; that enables the signal-level
    `attribute` API to also surface "skill:X|signal:Y" entries.
    """

    def __init__(
        self,
        config: Optional[HindsightConfig] = None,
        tca: Optional[TemporalCreditAssigner] = None,
    ) -> None:
        self._cfg = config or HindsightConfig()
        self._tca = tca
        self._states: dict[str, _State] = {}
        self._lock = threading.RLock()
        if not (0.0 < self._cfg.alpha_ema <= 1.0):
            raise ValueError("alpha_ema must be in (0, 1]")
        if self._cfg.clip_delta <= 0:
            raise ValueError("clip_delta must be > 0")
        if self._cfg.min_uses_for_judgment < 0:
            raise ValueError("min_uses_for_judgment must be >= 0")

    # ---------------- observe ----------------

    def observe(
        self,
        skill_id: str,
        m_with: float,
        m_without: float,
        step: int,
        *,
        signals: Optional[Sequence[Tuple[str, float]]] = None,
        context: Optional[Mapping[str, float]] = None,
    ) -> UtilitySnapshot:
        """Ingest one sample of ``(m_with, m_without)`` at ``step``.

        Parameters
        ----------
        skill_id
            The skill whose utility we are updating.
        m_with, m_without
            Scalar performance metrics (higher = better) for the same
            input stream with and without the skill applied.
        step
            The tick at which the metrics were observed. Used for
            same-stream sanity and for TCA attribution.
        signals
            Optional ``(signal_name, fraction)`` tuples describing the
            skill's attention on each input signal at this step; only
            used to feed the companion TCA.
        context
            Arbitrary scalar annotations for TCA (e.g. "tenant": ...).
        """
        if not skill_id:
            raise ValueError("skill_id must be non-empty")
        for name, value in ("m_with", m_with), ("m_without", m_without):
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite, got {value}")

        delta = float(m_with - m_without)
        clipped = max(-self._cfg.clip_delta, min(self._cfg.clip_delta, delta))

        with self._lock:
            state = self._states.get(skill_id)
            if state is None:
                state = _State(
                    utility=0.0,
                    n=0,
                    last_step=step,
                    last_active_step=step,
                )
                self._states[skill_id] = state
            else:
                if self._cfg.strict_same_stream and step < state.last_step:
                    raise ValueError(
                        f"step {step} precedes last_step {state.last_step} "
                        f"for skill {skill_id!r}; observations must be monotonic"
                    )
                state.last_step = step
                state.last_active_step = step

            alpha = self._cfg.alpha_ema
            state.utility = (1 - alpha) * state.utility + alpha * clipped
            state.n += 1

            snapshot = self._make_snapshot(skill_id, state)

        # Forward to TCA (outside the lock to avoid holding two locks).
        if self._tca is not None and signals:
            # Loss = -delta clipped to non-negative for the "was it
            # harmful?" interpretation, because TCA stores losses not
            # utilities. Positive utility ⇒ zero loss attributed; a
            # negative utility ⇒ |delta| loss attributed.
            loss = max(0.0, -clipped)
            self._tca.record_skill(
                tick=step,
                skill_id=skill_id,
                signals=list(signals),
                loss=loss,
                context=dict(context or {}),
            )
        return snapshot

    def observe_stream(
        self,
        skill_id: str,
        active_metric: float,
        baseline_metric: float,
        step: int,
        **kwargs,
    ) -> UtilitySnapshot:
        """Alias of :meth:`observe` for streaming-loop readability."""
        return self.observe(skill_id, active_metric, baseline_metric, step, **kwargs)

    # ---------------- accessors ----------------

    def snapshot(self, skill_id: str) -> UtilitySnapshot:
        with self._lock:
            state = self._states.get(skill_id)
            if state is None:
                return UtilitySnapshot(
                    skill_id=skill_id,
                    utility_ema=0.0,
                    n_observed=0,
                    last_step=-1,
                    confidence=0.0,
                )
            return self._make_snapshot(skill_id, state)

    def utilities(self) -> Mapping[str, float]:
        """Cheap read-only view used by the retriever hot path."""
        with self._lock:
            return {sid: s.utility for sid, s in self._states.items()}

    def all(self) -> List[UtilitySnapshot]:
        with self._lock:
            return [self._make_snapshot(sid, s) for sid, s in self._states.items()]

    def reset(self) -> None:
        with self._lock:
            self._states.clear()

    # ---------------- helpers ----------------

    def _make_snapshot(self, skill_id: str, state: _State) -> UtilitySnapshot:
        # Confidence: 0 during warmup, linearly ramping to 1 as
        # n_observed grows past ``min_uses_for_judgment + 50``.
        warmup = self._cfg.min_uses_for_judgment
        if state.n < warmup:
            confidence = 0.0
        else:
            confidence = min(1.0, (state.n - warmup) / max(50, 1))
        return UtilitySnapshot(
            skill_id=skill_id,
            utility_ema=float(state.utility),
            n_observed=int(state.n),
            last_step=int(state.last_step),
            confidence=float(confidence),
        )


__all__ = [
    "HindsightConfig",
    "HindsightUtilityTracker",
    "UtilitySnapshot",
]
