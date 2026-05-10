"""Industrial-grade safety layer on top of the controller primitives.

Four capabilities, each mapping to a well-known SRE concern:

1. :class:`SafetyEnvelope` — clamp *actions* to an operational envelope
   (e.g. ``replica_delta ∈ [-2, +3]`` per tick, rate of change bounded).
   This is the action-space analogue of the weight-space floor/ceiling.

2. :class:`ShadowRunner` — run the new controller in *shadow mode*
   alongside a baseline. Actions are logged but not applied; the user
   compares realised cost between shadow and baseline to decide when to
   cut over.

3. :class:`CounterfactualExplainer` — given a decision record, compute
   "what would the action be if we zeroed out signal k?". This is the
   SRE analogue of attention-residual ablation and the basis for
   post-incident "why did the controller do X?" explanations.

4. :class:`WeightDriftDetector` — EWMA-based drift monitor on the
   weight vector a_{t}. If today's distribution of weights differs
   from last week's by more than a threshold (KL divergence), emit an
   alert — the controller's *preferences* are shifting and humans
   should know.

All four are domain-free and rely only on :mod:`sre_control`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .sre_control import WeightedConvexCombiner


# ---------------------------------------------------------------------------
# 1. Action-space safety envelope
# ---------------------------------------------------------------------------

@dataclass
class SafetyEnvelope:
    """Hard bounds and rate-limits on the action vector.

    Parameters
    ----------
    low, high : np.ndarray
        Per-dimension lower and upper bounds on the absolute action.
    max_delta : np.ndarray, optional
        Per-dimension cap on how much ``action`` can change between
        consecutive ticks. Use ``np.inf`` entries to disable a specific
        dim.
    """
    low: np.ndarray
    high: np.ndarray
    max_delta: Optional[np.ndarray] = None

    def __post_init__(self) -> None:
        if self.low.shape != self.high.shape:
            raise ValueError("low / high shapes must match")
        if np.any(self.low > self.high):
            raise ValueError("every low must be ≤ its corresponding high")
        if self.max_delta is not None and self.max_delta.shape != self.low.shape:
            raise ValueError("max_delta shape must match low/high")
        self._last_action: Optional[np.ndarray] = None
        self._violation_count = 0

    # -------------------------------------------------- enforcement
    def apply(self, action: np.ndarray) -> Tuple[np.ndarray, Dict[str, Any]]:
        """Clip ``action`` to the envelope; report what was adjusted."""
        if action.shape != self.low.shape:
            raise ValueError(
                f"action shape {action.shape} != envelope shape {self.low.shape}"
            )
        original = action.copy()
        clipped = np.clip(original, self.low, self.high)
        if self.max_delta is not None and self._last_action is not None:
            lo = self._last_action - self.max_delta
            hi = self._last_action + self.max_delta
            clipped = np.clip(clipped, lo, hi)
        changed = not np.allclose(original, clipped)
        if changed:
            self._violation_count += 1
        self._last_action = clipped.copy()
        return clipped, {
            "original": original,
            "clipped": changed,
            "violation_count": self._violation_count,
        }

    @property
    def violation_count(self) -> int:
        return self._violation_count


# ---------------------------------------------------------------------------
# 2. Shadow-mode runner
# ---------------------------------------------------------------------------

@dataclass
class ShadowRecord:
    step: int
    baseline: np.ndarray
    shadow: np.ndarray
    divergence: float
    context: Dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "step": self.step,
            "baseline": [float(x) for x in self.baseline],
            "shadow": [float(x) for x in self.shadow],
            "divergence": float(self.divergence),
            "context": dict(self.context),
        }


class ShadowRunner:
    """Run a shadow controller in parallel with the active one.

    The ``baseline_fn`` is the currently-deployed controller (may be a
    hand-written if/else, a PID loop, or a previous version of our own
    combiner). ``shadow_fn`` is the new candidate. The runner calls both
    on every tick, records the pair, and reports their divergence —
    ``L2`` by default — over time.

    Cutover decision belongs to the operator, who looks at the divergence
    distribution, the baseline's realised cost, and the shadow's
    counterfactual cost.
    """

    def __init__(
        self,
        baseline_fn,                       # Callable[..., np.ndarray]
        shadow_fn,                         # Callable[..., np.ndarray]
        divergence: str = "l2",
    ) -> None:
        if divergence not in ("l2", "l1", "max"):
            raise ValueError("divergence must be one of: l2 / l1 / max")
        self.baseline_fn = baseline_fn
        self.shadow_fn = shadow_fn
        self.divergence = divergence
        self._records: List[ShadowRecord] = []

    # -------------------------------------------------- step
    def tick(
        self,
        *args,
        context: Optional[Dict[str, float]] = None,
        **kwargs,
    ) -> Tuple[np.ndarray, ShadowRecord]:
        baseline_action = np.asarray(self.baseline_fn(*args, **kwargs),
                                     dtype=float)
        shadow_action = np.asarray(self.shadow_fn(*args, **kwargs),
                                   dtype=float)
        if baseline_action.shape != shadow_action.shape:
            raise RuntimeError(
                f"baseline / shadow action shapes disagree: "
                f"{baseline_action.shape} vs {shadow_action.shape}"
            )
        div = _divergence(baseline_action, shadow_action, self.divergence)
        rec = ShadowRecord(
            step=len(self._records),
            baseline=baseline_action,
            shadow=shadow_action,
            divergence=div,
            context=dict(context or {}),
        )
        self._records.append(rec)
        # The returned action is the *baseline* — shadow is observed only.
        return baseline_action, rec

    # -------------------------------------------------- stats
    def summary(self) -> Dict[str, float]:
        if not self._records:
            return {"n": 0}
        divs = np.array([r.divergence for r in self._records])
        return {
            "n": len(self._records),
            "divergence_mean": float(divs.mean()),
            "divergence_p95": float(np.quantile(divs, 0.95)),
            "divergence_max": float(divs.max()),
        }


def _divergence(a: np.ndarray, b: np.ndarray, kind: str) -> float:
    d = a - b
    if kind == "l2":
        return float(np.linalg.norm(d))
    if kind == "l1":
        return float(np.abs(d).sum())
    return float(np.abs(d).max())


# ---------------------------------------------------------------------------
# 3. Counterfactual explainer
# ---------------------------------------------------------------------------

@dataclass
class CounterfactualResult:
    """One counterfactual: zeroing out signal k gives this alternate action."""
    signal_index: int
    signal_name: str
    alternate_action: np.ndarray
    delta_norm: float                 # ||alternate - factual||_2
    weight_shift: np.ndarray          # new_weights - old_weights

    def as_dict(self) -> dict:
        return {
            "signal_index": self.signal_index,
            "signal_name": self.signal_name,
            "alternate_action": [float(x) for x in self.alternate_action],
            "delta_norm": float(self.delta_norm),
            "weight_shift": [float(x) for x in self.weight_shift],
        }


class CounterfactualExplainer:
    """Compute "what if signal k was absent?" explanations for any combiner.

    The mechanism is exact, not approximate: we re-run the combiner with
    signal k masked out via a very negative bias so its softmax weight
    collapses toward zero, then compare actions. Because the combiner
    preserves ``Σ a = 1`` by design, masking one signal redistributes its
    weight *proportionally* to the surviving ones — which is exactly the
    desired "marginal importance" definition.
    """

    def __init__(self, combiner: WeightedConvexCombiner, mask_bias: float = -1e3) -> None:
        self.combiner = combiner
        self.mask_bias = float(mask_bias)

    def explain(
        self,
        query: np.ndarray,
        values: List[np.ndarray],
        factual_action: np.ndarray,
    ) -> List[CounterfactualResult]:
        """Return one CounterfactualResult per input signal."""
        # Snapshot the factual weights first (combiner may have been called
        # elsewhere; we don't rely on its internal last_weights).
        _, factual_weights = self.combiner.combine(query, values)
        out: List[CounterfactualResult] = []
        for k, spec in enumerate(self.combiner.signals):
            original_bias = spec.bias
            try:
                spec.bias = original_bias + self.mask_bias     # strong negative
                alt_action, alt_weights = self.combiner.combine(query, values)
                out.append(CounterfactualResult(
                    signal_index=k,
                    signal_name=spec.name,
                    alternate_action=alt_action,
                    delta_norm=float(np.linalg.norm(alt_action - factual_action)),
                    weight_shift=alt_weights - factual_weights,
                ))
            finally:
                spec.bias = original_bias
        # Restore the factual weights by running combine once more.
        self.combiner.combine(query, values)
        return out


# ---------------------------------------------------------------------------
# 4. Weight-drift detector
# ---------------------------------------------------------------------------

class WeightDriftDetector:
    """EWMA-based KL-divergence monitor over weight vectors.

    Maintains two distributions: a fast EWMA (short window) and a slow
    EWMA (long window). Whenever their KL divergence exceeds a threshold
    we flag drift. The detector never mutates the controller — it simply
    emits events that ops / ML systems can respond to.
    """

    def __init__(
        self,
        n_signals: int,
        fast_alpha: float = 0.3,
        slow_alpha: float = 0.03,
        kl_threshold: float = 0.25,
    ) -> None:
        if not (0 < fast_alpha <= 1):
            raise ValueError("fast_alpha must be in (0, 1]")
        if not (0 < slow_alpha <= fast_alpha):
            raise ValueError("slow_alpha must be in (0, fast_alpha]")
        if kl_threshold <= 0:
            raise ValueError("kl_threshold must be > 0")
        self.n_signals = int(n_signals)
        self.fast_alpha = float(fast_alpha)
        self.slow_alpha = float(slow_alpha)
        self.kl_threshold = float(kl_threshold)
        # Initialise both EWMAs to the uniform distribution so the first
        # few ticks don't fire spurious alerts.
        init = np.full(n_signals, 1.0 / n_signals)
        self.fast = init.copy()
        self.slow = init.copy()
        self._alerts: List[Dict[str, Any]] = []

    # -------------------------------------------------- update
    def observe(self, weights: np.ndarray, step: int) -> Optional[Dict[str, Any]]:
        """Feed one weight vector to the detector.

        Returns an alert dict if drift crosses the threshold *this* tick,
        else ``None``.
        """
        if weights.shape != (self.n_signals,):
            raise ValueError("weights shape mismatch")
        w = np.clip(weights, 1e-12, 1.0)
        w = w / w.sum()
        self.fast = (1 - self.fast_alpha) * self.fast + self.fast_alpha * w
        self.slow = (1 - self.slow_alpha) * self.slow + self.slow_alpha * w
        kl = _kl(self.fast, self.slow)
        if kl > self.kl_threshold:
            alert = {
                "step": int(step),
                "kl": float(kl),
                "fast": self.fast.copy(),
                "slow": self.slow.copy(),
            }
            self._alerts.append(alert)
            return alert
        return None

    def alerts(self) -> List[Dict[str, Any]]:
        return list(self._alerts)


def _kl(p: np.ndarray, q: np.ndarray, eps: float = 1e-12) -> float:
    p = np.clip(p, eps, 1.0)
    q = np.clip(q, eps, 1.0)
    return float((p * (np.log(p) - np.log(q))).sum())


__all__ = [
    "SafetyEnvelope",
    "ShadowRecord", "ShadowRunner",
    "CounterfactualResult", "CounterfactualExplainer",
    "WeightDriftDetector",
]
