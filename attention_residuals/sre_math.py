"""Deep-math primitives distilled from individual Attention-Residuals equations.

Previous rounds extracted *structural* primitives (softmax + floor/ceiling,
hierarchical blocks, gates). This module digs into specific scalar
operations inside those equations and turns each of them into a
standalone SRE primitive:

    §05  q·K_k / √d              →  :class:`ScaleInvariantNormalizer`
    §05  softmax(·/τ)             →  :class:`TemperatureScheduler`
    §08  concat_h · W_O           →  :class:`ViewSpec`, :class:`MultiViewCombiner`
    §17  w ← w·exp(-η·loss)       →  :class:`FTRLLearner` (Hedge as a special case)
    §02  I + ∂F/∂x stability      →  :class:`JacobianContractionMonitor`
    §02  ∂L/∂x_l gradient flow    →  :class:`TemporalCreditAssigner`
    §18  drift on probability     →  :class:`WassersteinDriftDetector`

Every primitive is pure numpy; imports are kept minimal so this module
can be dropped into a control-plane service without a PyTorch dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .sre_control import (
    SignalSpec,
    WeightedConvexCombiner,
)


# ---------------------------------------------------------------------------
# §05  Scale invariance :  q·K / √d  →  ScaleInvariantNormalizer
# ---------------------------------------------------------------------------
#
# In scaled dot-product attention, dividing by √d isn't cosmetic. q·K is
# a sum of d random products with bounded variance; its variance grows
# linearly with d. Without the 1/√d scaling, softmax becomes either too
# peaky (at large d) or too flat (at small d). The √d factor keeps the
# *distribution of logits* invariant to dimensionality.
#
# The SRE analog: signals live on wildly different scales (latency in
# milliseconds, RPS in thousands, error-rate in [0,1]). Without an
# analogous scale-normalisation, the signal with the largest native
# range will dominate the softmax, regardless of its true importance.
# The cure is Welford-style online z-scoring — standard in streaming
# analytics, but *belongs* here because it's the same mathematical
# invariance the paper exploits.
# ---------------------------------------------------------------------------


class ScaleInvariantNormalizer:
    """Online z-score normaliser with EWMA tracking (scalar per signal).

    Parameters
    ----------
    n_signals : int
        Number of parallel signal streams.
    alpha : float
        EWMA update rate for mean and variance (``0 < α ≤ 1``). Smaller
        ``α`` means slower tracking; ``α=1`` reduces to "use only the
        latest sample" (degenerate, but valid).
    warmup : int
        Number of samples before the normaliser starts returning
        z-scores. During warmup :meth:`transform` returns the raw input
        and :attr:`ready` is ``False``.
    eps : float
        Floor on the standard deviation to avoid division by zero on
        constant streams.
    """

    def __init__(
        self,
        n_signals: int,
        alpha: float = 0.05,
        warmup: int = 16,
        eps: float = 1e-6,
    ) -> None:
        if n_signals < 1:
            raise ValueError("n_signals must be ≥ 1")
        if not (0.0 < alpha <= 1.0):
            raise ValueError("alpha must be in (0, 1]")
        if warmup < 1:
            raise ValueError("warmup must be ≥ 1")
        if eps <= 0:
            raise ValueError("eps must be > 0")
        self.n_signals = int(n_signals)
        self.alpha = float(alpha)
        self.warmup = int(warmup)
        self.eps = float(eps)
        self._mean = np.zeros(n_signals, dtype=float)
        self._var = np.ones(n_signals, dtype=float)  # start at 1 to avoid /0
        self._count = 0

    # -------------------------------------------------- updates
    def observe(self, x: np.ndarray) -> None:
        if x.shape != (self.n_signals,):
            raise ValueError(f"x shape {x.shape} != ({self.n_signals},)")
        if self._count == 0:
            # Seed with the first sample so the EWMA has a sensible
            # starting point rather than 0 / 1.
            self._mean = x.astype(float).copy()
            self._var = np.ones_like(self._mean)
        else:
            diff = x - self._mean
            self._mean = self._mean + self.alpha * diff
            # EWMA of squared deviation — the "variance" of a Welford
            # estimator in streaming form.
            self._var = (1 - self.alpha) * (self._var + self.alpha * diff * diff)
        self._count += 1

    # -------------------------------------------------- transform
    def transform(self, x: np.ndarray) -> np.ndarray:
        """Return z-scored ``x``. Identity during warmup."""
        if x.shape != (self.n_signals,):
            raise ValueError(f"x shape {x.shape} != ({self.n_signals},)")
        if not self.ready:
            return x.astype(float).copy()
        std = np.sqrt(np.maximum(self._var, self.eps))
        return (x - self._mean) / std

    def observe_and_transform(self, x: np.ndarray) -> np.ndarray:
        """Most common combined path: update state then return z-score."""
        self.observe(x)
        return self.transform(x)

    # -------------------------------------------------- inspection
    @property
    def ready(self) -> bool:
        return self._count >= self.warmup

    @property
    def mean(self) -> np.ndarray:
        return self._mean.copy()

    @property
    def std(self) -> np.ndarray:
        return np.sqrt(np.maximum(self._var, self.eps))


# ---------------------------------------------------------------------------
# §05  softmax(logits/τ)  →  TemperatureScheduler
# ---------------------------------------------------------------------------
#
# Softmax at temperature τ : a_k = exp(s_k/τ) / Σ_j exp(s_j/τ).
# Two limits:
#   τ → 0⁺ : a becomes one-hot (argmax).                Pure exploitation.
#   τ → ∞  : a becomes uniform.                         Pure exploration.
#
# A controller usually wants to start with some exploration (τ high) and
# anneal to exploitation as it collects evidence. The classic schedule
# τ_t = τ_0 / √(1+t) matches the Hedge regret proof's learning-rate
# schedule; linear schedules are also common in practice.
# ---------------------------------------------------------------------------


@dataclass
class TemperatureScheduler:
    """Closed-form temperature schedule for a softmax-based controller.

    Parameters
    ----------
    tau0 : float
        Initial temperature (at t=0).
    tau_min : float
        Floor — the schedule never drops below this.
    kind : str
        One of ``"sqrt"``, ``"linear"``, ``"exp"``, ``"constant"``.
    half_life : float
        For ``"exp"`` kind: ticks after which τ decays to τ0/2.
    total_ticks : int
        For ``"linear"`` kind: horizon at which τ reaches ``tau_min``.
    """
    tau0: float = 1.0
    tau_min: float = 1e-3
    kind: str = "sqrt"
    half_life: float = 100.0
    total_ticks: int = 1000

    def __post_init__(self) -> None:
        if self.tau0 <= 0 or self.tau_min <= 0:
            raise ValueError("temperatures must be > 0")
        if self.tau_min > self.tau0:
            raise ValueError("tau_min must be ≤ tau0")
        if self.kind not in {"sqrt", "linear", "exp", "constant"}:
            raise ValueError("kind must be one of sqrt/linear/exp/constant")

    def tau(self, t: int) -> float:
        if t < 0:
            raise ValueError("t must be ≥ 0")
        if self.kind == "constant":
            value = self.tau0
        elif self.kind == "sqrt":
            value = self.tau0 / np.sqrt(1.0 + t)
        elif self.kind == "linear":
            frac = min(1.0, t / max(self.total_ticks, 1))
            # Ensure exact floor at t == total_ticks without float fuzz.
            if frac >= 1.0:
                return float(self.tau_min)
            value = self.tau0 + (self.tau_min - self.tau0) * frac
        else:  # "exp"
            value = self.tau0 * (0.5 ** (t / max(self.half_life, 1.0)))
        return float(max(value, self.tau_min))


# ---------------------------------------------------------------------------
# §08  Multi-head :  y = concat_h(Σ_k a_{h,k}·V_h x_k) · W_O  →  MultiViewCombiner
# ---------------------------------------------------------------------------
#
# Multi-head attention decomposes the feature space into H orthogonal
# subspaces ("heads"), runs attention inside each, then mixes outputs
# with W_O. The structural meaning is *subspace decoupling*: each head
# gets to answer a different question about the same state.
#
# In SRE we often want the same thing — "latency view", "reliability
# view", "cost view" — each with its own fused recommendation. The
# critical property we preserve from the paper: Σa=1 holds *per head*,
# so every view respects its own budget-conservation invariant.
# ---------------------------------------------------------------------------


@dataclass
class ViewSpec:
    """Description of one view (≈ one attention head in §08)."""
    name: str
    signals: Sequence[SignalSpec]
    weight: float = 1.0          # merging weight (later normalised across views)


class MultiViewCombiner:
    """Run multiple independent combiners (one per view) and merge them.

    The merge step is itself a convex combination, so the outer layer
    still obeys ``Σ merge_weights = 1``. This makes the whole structure
    a nested simplex — exactly the "concat + W_O" pattern with guaranteed
    budget conservation.

    Parameters
    ----------
    views : sequence of ViewSpec
        One view per "head". Each view has its own signals; they may
        overlap or not.
    query_dim : int
        Dimensionality shared by all per-view combiners.
    """

    def __init__(
        self,
        views: Sequence[ViewSpec],
        query_dim: int,
        temperature: float = 1.0,
        rng_seed: Optional[int] = 0,
    ) -> None:
        if not views:
            raise ValueError("need at least one view")
        if any(v.weight <= 0 for v in views):
            raise ValueError("view weights must be > 0")
        self.views = list(views)
        self._combiners: List[WeightedConvexCombiner] = [
            WeightedConvexCombiner(
                list(v.signals),
                query_dim=query_dim,
                temperature=temperature,
                rng_seed=(None if rng_seed is None else rng_seed + i),
            )
            for i, v in enumerate(views)
        ]
        raw = np.array([v.weight for v in views], dtype=float)
        self._merge_weights = raw / raw.sum()
        self._last_view_weights: List[np.ndarray] = []

    # -------------------------------------------------- forward
    def combine(
        self,
        query_per_view: Sequence[np.ndarray],
        values_per_view: Sequence[Sequence[np.ndarray]],
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Run one step.

        Parameters
        ----------
        query_per_view :
            One query vector per view.
        values_per_view :
            For each view, a list of proposed action vectors (one per
            signal in that view).

        Returns
        -------
        action : np.ndarray
            The merged action.
        merge_weights : np.ndarray
            The outer merge weights (shape = ``(num_views,)``).
        """
        if len(query_per_view) != len(self.views):
            raise ValueError("query_per_view length mismatch")
        if len(values_per_view) != len(self.views):
            raise ValueError("values_per_view length mismatch")
        self._last_view_weights = []
        per_view_actions: List[np.ndarray] = []
        for c, q, vs in zip(self._combiners, query_per_view, values_per_view):
            action_h, w_h = c.combine(q, vs)
            per_view_actions.append(action_h)
            self._last_view_weights.append(w_h)
        # merge : convex combination with static merge weights
        stacked = np.stack(per_view_actions, axis=0)
        final = (self._merge_weights[:, None] * stacked).sum(axis=0)
        return final, self._merge_weights.copy()

    # -------------------------------------------------- inspection
    def last_view_weights(self) -> List[np.ndarray]:
        """Per-view softmax weights from the last :meth:`combine`."""
        return [w.copy() for w in self._last_view_weights]


# ---------------------------------------------------------------------------
# §17  FTRL with pluggable regularizer :  generalises Hedge
# ---------------------------------------------------------------------------
#
# Hedge is a special case of Follow-The-Regularized-Leader :
#
#   x_{t+1} = argmin_{x ∈ Δ}  Σ_{s ≤ t} ⟨g_s, x⟩  +  (1/η) Ψ(x)
#
# With Ψ = negative entropy we recover Hedge. With Ψ = (1/2) ‖x‖² we
# recover Online Gradient Descent (OGD) projected onto the simplex.
# Picking different Ψ lets the engineer dial in update geometry:
#   entropy  →  mass conservation; regret √(T log n); aggressive at corners.
#   l2       →  additive updates; regret √T; smoother near boundaries.
#
# Both live in one class. No neural-net dependency.
# ---------------------------------------------------------------------------


class FTRLLearner:
    """Follow-the-regularized-leader over the simplex.

    ``regularizer``:
        * ``"entropy"`` — softmax-of-negative-cum-loss = **Hedge**.
        * ``"l2"`` — projected gradient descent on the simplex =
          **OGD** restricted to a distribution.
    """

    def __init__(
        self,
        n_signals: int,
        eta: float = 0.1,
        regularizer: str = "entropy",
        init: Optional[np.ndarray] = None,
    ) -> None:
        if n_signals < 1:
            raise ValueError("n_signals must be ≥ 1")
        if eta <= 0:
            raise ValueError("eta must be > 0")
        if regularizer not in {"entropy", "l2"}:
            raise ValueError("regularizer must be 'entropy' or 'l2'")
        self.n_signals = int(n_signals)
        self.eta = float(eta)
        self.regularizer = regularizer
        self._g_sum = np.zeros(n_signals, dtype=float)
        if init is not None:
            if init.shape != (n_signals,):
                raise ValueError("init shape mismatch")
            if init.min() <= 0:
                raise ValueError("init must have strictly positive entries")
            # Translate the init distribution into an equivalent cumulative
            # gradient, so the first weights() call returns exactly `init`.
            if regularizer == "entropy":
                self._g_sum = -np.log(init / init.sum()) / self.eta
            else:
                self._g_sum = -init.astype(float) / self.eta

    # -------------------------------------------------- update
    def update(self, losses: np.ndarray) -> None:
        if losses.shape != (self.n_signals,):
            raise ValueError("losses shape mismatch")
        self._g_sum += losses

    # -------------------------------------------------- inference
    def weights(self) -> np.ndarray:
        if self.regularizer == "entropy":
            logits = -self.eta * self._g_sum
            logits -= logits.max()         # numerical stability
            w = np.exp(logits)
            return w / w.sum()
        # l2 : projected gradient, start from -η·g_sum
        raw = -self.eta * self._g_sum
        return _euclidean_simplex_projection(raw)

    def logits(self) -> np.ndarray:
        return -self.eta * self._g_sum.copy()


def _euclidean_simplex_projection(y: np.ndarray) -> np.ndarray:
    """Euclidean projection onto the probability simplex.

    Implements the O(n log n) sort-based algorithm from
    Wang & Carreira-Perpinán 2013. Used by FTRL(l2). Kept separate from
    :func:`_project_to_simplex_with_bounds` because the bounded version
    does sum-preserving redistribution, while this one performs
    ``argmin_{x ∈ Δ} ‖x − y‖²`` — two distinct operations.
    """
    n = y.shape[0]
    u = np.sort(y)[::-1]                     # descending
    cssv = np.cumsum(u)
    # Find the largest rho such that u[rho] - (cssv[rho] - 1) / (rho + 1) > 0.
    rho_candidates = np.nonzero(u - (cssv - 1.0) / np.arange(1, n + 1) > 0)[0]
    if rho_candidates.size == 0:
        # y is already far below the simplex — fall back to uniform.
        return np.full(n, 1.0 / n)
    rho = int(rho_candidates[-1])
    theta = (cssv[rho] - 1.0) / (rho + 1)
    return np.maximum(y - theta, 0.0)


# ---------------------------------------------------------------------------
# §02  residual Jacobian  I + ∂F/∂x   →  JacobianContractionMonitor
# ---------------------------------------------------------------------------
#
# A residual recursion x_{t+1} = x_t + F(x_t, u_t) is stable iff its
# Jacobian I + ∂F/∂x has spectral radius ≤ 1. For a black-box controller
# we can estimate the *effective gain* empirically by regressing the
# observed state change Δx_t against the action u_t via a rolling OLS:
#
#       Δx_t  ≈  g · u_t  +  ε_t
#
# If |g| drifts above 1, the loop is self-amplifying — e.g. adding
# replicas makes next-tick load higher rather than lower. Catching this
# early is the SRE analog of preventing gradient explosion.
# ---------------------------------------------------------------------------


class JacobianContractionMonitor:
    """Rolling OLS gain estimator with an amplification alert.

    Parameters
    ----------
    window : int
        Number of recent samples used for the regression.
    min_samples : int
        Minimum samples before :meth:`gain` returns a non-NaN value.
    threshold : float
        |gain| above this fires an amplification alert.
    """

    def __init__(
        self,
        window: int = 64,
        min_samples: int = 16,
        threshold: float = 1.0,
    ) -> None:
        if window < 2 or min_samples < 2 or min_samples > window:
            raise ValueError("require 2 ≤ min_samples ≤ window")
        if threshold <= 0:
            raise ValueError("threshold must be > 0")
        self.window = int(window)
        self.min_samples = int(min_samples)
        self.threshold = float(threshold)
        self._u: List[float] = []
        self._dx: List[float] = []
        self._alerts: List[Dict[str, float]] = []

    # -------------------------------------------------- observe
    def observe(self, action: float, state_delta: float, step: Optional[int] = None) -> None:
        self._u.append(float(action))
        self._dx.append(float(state_delta))
        if len(self._u) > self.window:
            self._u.pop(0)
            self._dx.pop(0)
        # Fire alert once we have enough samples and gain is too big.
        if len(self._u) >= self.min_samples:
            g = self._gain()
            if g is not None and abs(g) > self.threshold:
                self._alerts.append({
                    "step": float(step) if step is not None else float(len(self._alerts)),
                    "gain": float(g),
                    "samples": float(len(self._u)),
                })

    # -------------------------------------------------- regression
    def _gain(self) -> Optional[float]:
        u = np.asarray(self._u, dtype=float)
        dx = np.asarray(self._dx, dtype=float)
        uu = (u * u).sum()
        if uu < 1e-12:
            return None
        return float((u * dx).sum() / uu)

    def gain(self) -> Optional[float]:
        return None if len(self._u) < self.min_samples else self._gain()

    # -------------------------------------------------- inspection
    def alerts(self) -> List[Dict[str, float]]:
        return list(self._alerts)


# ---------------------------------------------------------------------------
# §02  gradient flow ∂L/∂x_l = ∂L/∂x_{l+1}·(I + ∂F/∂x_l)  →  TemporalCreditAssigner
# ---------------------------------------------------------------------------
#
# The identity in the Jacobian is what makes gradients flow across many
# layers. Transplanted to time, it means an outcome observed at tick T
# can be decomposed into contributions from decisions at every past
# tick, each weighted by the product of identity-plus-local-jacobian
# terms. With linear F (as in our convex combiner) the weights simplify
# to the decision weights themselves, modulated by a decay.
#
# A full decomposition requires replay; for fast SRE post-mortems we use
# a linear surrogate:
#
#   blame(signal=k, tick=t | incident at T)  ≈  a_{t,k} · loss_{t,k} · γ^(T-t)
#
# That is the SRE equivalent of backpropagation through time, running
# in O(window · n_signals) forward-only.
# ---------------------------------------------------------------------------


@dataclass
class CreditEntry:
    tick: int
    signal_name: str
    score: float
    weight: float
    loss: float
    context: Dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "tick": self.tick,
            "signal_name": self.signal_name,
            "score": float(self.score),
            "weight": float(self.weight),
            "loss": float(self.loss),
            "context": dict(self.context),
        }


class TemporalCreditAssigner:
    """Retrospective blame distribution across past decisions and signals.

    Typical use::

        tca = TemporalCreditAssigner(decay=0.9)
        for t in ticks:
            ...
            tca.record(t, weights=w, losses=L, context={"qps": qps})

        # after the incident at tick T
        top_blamed = tca.attribute(incident_tick=T, window=50, top_k=10)
    """

    def __init__(self, decay: float = 0.9) -> None:
        if not (0.0 < decay <= 1.0):
            raise ValueError("decay must be in (0, 1]")
        self.decay = float(decay)
        self._history: List[dict] = []

    # -------------------------------------------------- record
    def record(
        self,
        tick: int,
        weights: np.ndarray,
        losses: np.ndarray,
        signal_names: Optional[Sequence[str]] = None,
        context: Optional[Dict[str, float]] = None,
    ) -> None:
        if weights.shape != losses.shape:
            raise ValueError("weights and losses must share shape")
        names = list(signal_names) if signal_names is not None else [
            f"signal_{i}" for i in range(weights.shape[0])
        ]
        if len(names) != weights.shape[0]:
            raise ValueError("signal_names length mismatch")
        self._history.append({
            "tick": int(tick),
            "weights": weights.copy(),
            "losses": losses.copy(),
            "names": names,
            "context": dict(context or {}),
        })

    # -------------------------------------------------- attribute
    def attribute(
        self,
        incident_tick: int,
        window: int = 50,
        top_k: Optional[int] = None,
    ) -> List[CreditEntry]:
        """Return blame entries sorted by score descending.

        The score is ``weight · loss · decay^age`` where age = incident
        tick − decision tick. Only records with ``tick ≤ incident_tick``
        and ``age < window`` are considered.
        """
        entries: List[CreditEntry] = []
        for rec in self._history:
            age = incident_tick - rec["tick"]
            if age < 0 or age >= window:
                continue
            factor = self.decay ** age
            for name, w, l in zip(rec["names"], rec["weights"], rec["losses"]):
                entries.append(CreditEntry(
                    tick=rec["tick"],
                    signal_name=name,
                    score=float(w * l * factor),
                    weight=float(w),
                    loss=float(l),
                    context=dict(rec["context"]),
                ))
        entries.sort(key=lambda e: -e.score)
        return entries if top_k is None else entries[:top_k]


# ---------------------------------------------------------------------------
# §18  Wasserstein drift  —  alternative to KL for weight drift
# ---------------------------------------------------------------------------
#
# KL(p ‖ q) diverges when q has zero mass anywhere p has positive mass —
# a real risk when signal priorities shift abruptly. The 1-Wasserstein
# distance over the "signal index" axis is bounded, symmetric, and
# handles support changes gracefully. For 1D distributions the Wasserstein
# distance equals the L1 distance of CDFs:
#
#   W_1(p, q) = Σ_i |cumsum(p)_i - cumsum(q)_i|
#
# We use it as a drop-in replacement for the KL-based detector when
# alerts on small corner shifts matter more than on global re-weighting.
# ---------------------------------------------------------------------------


class WassersteinDriftDetector:
    """Drift detector using the 1D Wasserstein distance on weight vectors.

    The signal axis is treated as an ordered line (indices 0..n-1). If
    that ordering isn't meaningful in your domain, pass ``ordering`` to
    permute the axis into priority-sorted order (e.g. error_budget first,
    cost last).
    """

    def __init__(
        self,
        n_signals: int,
        fast_alpha: float = 0.3,
        slow_alpha: float = 0.03,
        threshold: float = 0.1,
        ordering: Optional[Sequence[int]] = None,
    ) -> None:
        if not (0.0 < fast_alpha <= 1.0):
            raise ValueError("fast_alpha must be in (0, 1]")
        if not (0.0 < slow_alpha <= fast_alpha):
            raise ValueError("slow_alpha must be in (0, fast_alpha]")
        if threshold <= 0:
            raise ValueError("threshold must be > 0")
        if ordering is not None and sorted(ordering) != list(range(n_signals)):
            raise ValueError("ordering must be a permutation of range(n_signals)")
        self.n_signals = int(n_signals)
        self.fast_alpha = float(fast_alpha)
        self.slow_alpha = float(slow_alpha)
        self.threshold = float(threshold)
        self.ordering = (np.asarray(ordering, dtype=int)
                         if ordering is not None else np.arange(n_signals))
        uni = np.full(n_signals, 1.0 / n_signals)
        self.fast = uni.copy()
        self.slow = uni.copy()
        self._alerts: List[Dict[str, float]] = []
        self._seeded = False

    def observe(self, weights: np.ndarray, step: int) -> Optional[Dict[str, float]]:
        if weights.shape != (self.n_signals,):
            raise ValueError("weights shape mismatch")
        w = np.clip(weights, 0.0, 1.0)
        total = w.sum()
        if total <= 0:
            raise ValueError("weights must sum to > 0")
        w = w / total
        if not self._seeded:
            # Seed both EWMAs with the first observation so that
            # cold-start transients don't fire spurious alerts.
            self.fast = w.copy()
            self.slow = w.copy()
            self._seeded = True
            return None
        self.fast = (1 - self.fast_alpha) * self.fast + self.fast_alpha * w
        self.slow = (1 - self.slow_alpha) * self.slow + self.slow_alpha * w
        dist = self._w1(self.fast, self.slow)
        if dist > self.threshold:
            alert = {
                "step": float(step),
                "w1": float(dist),
                "fast_hash": float(self.fast.sum()),  # sanity
                "slow_hash": float(self.slow.sum()),
            }
            self._alerts.append(alert)
            return alert
        return None

    def _w1(self, p: np.ndarray, q: np.ndarray) -> float:
        p_sorted = p[self.ordering]
        q_sorted = q[self.ordering]
        return float(np.abs(np.cumsum(p_sorted) - np.cumsum(q_sorted)).sum())

    def alerts(self) -> List[Dict[str, float]]:
        return list(self._alerts)


__all__ = [
    # §05
    "ScaleInvariantNormalizer", "TemperatureScheduler",
    # §08
    "ViewSpec", "MultiViewCombiner",
    # §17
    "FTRLLearner",
    # §02
    "JacobianContractionMonitor",
    "CreditEntry", "TemporalCreditAssigner",
    # §18
    "WassersteinDriftDetector",
]
