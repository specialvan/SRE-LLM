"""Closed-loop adaptive layer on top of :mod:`sre_control`.

Motivation
----------
The primitives in :mod:`sre_control` are *open-loop*: given a query and a
bag of signals they produce a decision, but they never look at what
happened next. Real SRE control needs to close the loop — when a
decision made queue grow, the controller should down-weight the signal
that recommended that decision; when a decision saved latency, that
signal should earn more influence.

This module provides two building blocks:

1. :class:`HedgeRegretLearner` — a classical online-learning algorithm
   (a.k.a. *multiplicative weights update* or *Hedge*) that maintains a
   probability distribution over signals so that the cumulative loss is
   at most ``O(sqrt(T log n))`` worse than always picking the best
   signal in hindsight. See Freund & Schapire 1997.

2. :class:`AdaptiveCombiner` — a thin wrapper around
   :class:`WeightedConvexCombiner` that consumes observed regret and
   feeds it back as a learnable ``bias`` vector. The combiner's hard
   invariants (``Σ a = 1``, ``a_k ∈ [floor_k, ceiling_k]``) remain
   untouched — the learner only tilts the *prior* on signals, it cannot
   break the safety envelope.

Design choices
--------------
* The learner stores its state as a vector of log-weights; the
  ``bias`` presented to :class:`WeightedConvexCombiner` is just those
  log-weights. This keeps the math identical to the open-loop case
  when the learning rate ``eta`` is 0.
* Losses are bounded to ``[0, 1]`` on entry — out-of-range values are
  clipped with a warning-style counter, never silently rescaled.
* The learner is deterministic given its seed; every update is an
  ``O(n)`` elementwise op, safe to call inside a tight control loop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import numpy as np

from .sre_control import AuditTrail, SignalSpec, WeightedConvexCombiner


# ---------------------------------------------------------------------------
# Hedge / Multiplicative-weights-update learner
# ---------------------------------------------------------------------------

class HedgeRegretLearner:
    """Online learner that maintains log-weights over ``n`` signals.

    Update rule (Freund & Schapire 1997)::

        w_i      ← w_i * exp(-eta * loss_i)
        logits_i  = log(w_i)      (returned via :meth:`logits`)

    With per-step losses in ``[0, 1]`` and a horizon ``T``, picking
    ``eta = sqrt(ln n / T)`` guarantees

        Σ_t  E[loss_t]  −  min_i Σ_t loss_{t,i}   ≤   √(T · ln n)

    i.e. the *regret* grows sub-linearly. In SRE this means: the longer
    the controller runs, the less its per-step cost can possibly be from
    the best-in-hindsight static policy — without ever having known
    which signal was going to be best.
    """

    def __init__(
        self,
        n_signals: int,
        eta: Optional[float] = None,
        horizon: Optional[int] = None,
        clip_range: Tuple[float, float] = (0.0, 1.0),
    ) -> None:
        if n_signals < 1:
            raise ValueError("n_signals must be >= 1")
        if eta is None:
            # Default: pick eta from the standard Hedge bound. If no
            # horizon is provided, pick a conservative one so the
            # learner is stable from step 1.
            T = horizon if horizon is not None else max(n_signals * 10, 50)
            eta = float(np.sqrt(np.log(max(n_signals, 2)) / T))
        if eta <= 0:
            raise ValueError("eta must be > 0")
        lo, hi = clip_range
        if not (lo < hi):
            raise ValueError("clip_range must be increasing")
        self.n_signals = int(n_signals)
        self.eta = float(eta)
        self._clip_lo = float(lo)
        self._clip_hi = float(hi)
        self._log_w = np.zeros(n_signals, dtype=float)
        self._cum_loss = np.zeros(n_signals, dtype=float)
        self._steps = 0
        self._clipped = 0

    # -------------------------------------------------- accessors
    def weights(self) -> np.ndarray:
        """Return the probability distribution implied by current log-weights."""
        w = self._log_w - self._log_w.max()
        w = np.exp(w)
        return w / w.sum()

    def logits(self) -> np.ndarray:
        """Return the raw log-weights (usable as ``bias`` in a combiner)."""
        return self._log_w.copy()

    # -------------------------------------------------- update
    def update(self, losses: np.ndarray) -> None:
        """Consume the losses observed on the last step.

        Each ``losses[i]`` should reflect how bad it would have been if
        the controller had assigned all its mass to signal ``i`` on the
        previous step. Typical SRE losses:

        * ``1 - success_rate``
        * ``max(0, latency - target) / target``
        * ``1 - (remaining_error_budget / total_error_budget)``
        """
        if losses.shape != (self.n_signals,):
            raise ValueError(
                f"losses shape {losses.shape} != ({self.n_signals},)"
            )
        clipped = np.clip(losses, self._clip_lo, self._clip_hi)
        self._clipped += int(((losses != clipped).sum()))
        self._log_w -= self.eta * clipped
        self._cum_loss += clipped
        self._steps += 1

    # -------------------------------------------------- diagnostics
    @property
    def steps(self) -> int:
        return self._steps

    @property
    def clipped_count(self) -> int:
        """Number of scalar losses that had to be clipped into clip_range."""
        return self._clipped

    def regret_bound(self) -> float:
        """Return the theoretical regret bound √(T · ln n) at current T."""
        if self._steps == 0:
            return 0.0
        return float(np.sqrt(self._steps * np.log(max(self.n_signals, 2))))

    def best_signal_in_hindsight(self) -> int:
        """Index of the signal with the smallest cumulative loss so far."""
        return int(np.argmin(self._cum_loss))


# ---------------------------------------------------------------------------
# AdaptiveCombiner — closed-loop wrapper
# ---------------------------------------------------------------------------

@dataclass
class AdaptiveRecord:
    """One closed-loop tick: (action, observed loss, learner state)."""
    step: int
    weights_before: np.ndarray
    action: np.ndarray
    losses: np.ndarray
    weights_after: np.ndarray
    regret_bound: float

    def as_dict(self) -> dict:
        return {
            "step": self.step,
            "weights_before": [float(x) for x in self.weights_before],
            "action": [float(x) for x in self.action],
            "losses": [float(x) for x in self.losses],
            "weights_after": [float(x) for x in self.weights_after],
            "regret_bound": float(self.regret_bound),
        }


class AdaptiveCombiner:
    """A :class:`WeightedConvexCombiner` that learns its own bias online.

    The flow per tick is::

        (1) bias_k ← learner.logits()
        (2) a_k, action ← combiner.combine(query, values)
                          using bias_k on top of the per-spec bias
        (3) after acting, observe ``losses_k`` (one per signal)
        (4) learner.update(losses_k)

    The ``[floor, ceiling]`` safety envelope stays in force at step 2 —
    the learner can shift priorities but cannot overrule hard invariants.
    """

    def __init__(
        self,
        signals: Sequence[SignalSpec],
        query_dim: int,
        learner: Optional[HedgeRegretLearner] = None,
        temperature: float = 1.0,
        rng_seed: Optional[int] = 0,
    ) -> None:
        self.specs = [
            SignalSpec(
                name=s.name,
                floor=s.floor,
                ceiling=s.ceiling,
                bias=s.bias,  # static prior from the operator
            )
            for s in signals
        ]
        self._static_biases = [float(s.bias) for s in signals]
        # The combiner's *own* bias on each spec will be overwritten
        # per-tick with (static_bias + learner_logit).
        self.combiner = WeightedConvexCombiner(
            self.specs, query_dim=query_dim,
            temperature=temperature, rng_seed=rng_seed,
        )
        self.learner = learner or HedgeRegretLearner(n_signals=len(signals))
        if self.learner.n_signals != len(signals):
            raise ValueError("learner.n_signals must match len(signals)")
        self._records: List[AdaptiveRecord] = []

    # -------------------------------------------------- main loop
    def step(
        self,
        query: np.ndarray,
        values: Sequence[np.ndarray],
        observed_losses: Optional[np.ndarray] = None,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Run one closed-loop tick.

        Parameters
        ----------
        query, values :
            As for :meth:`WeightedConvexCombiner.combine`.
        observed_losses :
            Per-signal loss from the *previous* tick. ``None`` on the
            very first call (no history yet).

        Returns
        -------
        action, weights
        """
        if observed_losses is not None:
            self.learner.update(observed_losses)

        # Inject the learner's logits as additional bias — without
        # rewriting the combiner's core invariants.
        logits = self.learner.logits()
        for spec, base_bias, lg in zip(self.combiner.signals, self._static_biases, logits):
            # We respect the operator-provided static bias and stack the
            # learner bias on top.
            spec.bias = float(base_bias + lg)

        weights_before = self.learner.weights()
        action, a = self.combiner.combine(query, values)
        self._records.append(AdaptiveRecord(
            step=len(self._records),
            weights_before=weights_before,
            action=action,
            losses=observed_losses if observed_losses is not None else np.zeros_like(a),
            weights_after=self.learner.weights(),
            regret_bound=self.learner.regret_bound(),
        ))
        return action, a

    # -------------------------------------------------- diagnostics
    def records(self) -> List[AdaptiveRecord]:
        return list(self._records)


__all__ = [
    "HedgeRegretLearner",
    "AdaptiveCombiner",
    "AdaptiveRecord",
]
