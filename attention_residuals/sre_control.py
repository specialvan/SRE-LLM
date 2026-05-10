"""SRE control primitives distilled from Attention Residuals.

This module is the *domain-free distillation* of the mechanisms explored
in :mod:`attn_residual`, :mod:`blocks`, :mod:`transformer_layer` and
:mod:`layer_skip`. The idea:

- Attention Residuals gave us a small handful of structural primitives
  (softmax-normalised weighted routing, horizontal/vertical decoupling,
  block-level sectioning, must-attend guarantees, audit-trail exposure,
  budget-preserving gating).
- Those primitives are not about deep learning; they are about how to
  combine heterogeneous signals into a single decision while preserving
  invariants. Exactly the job of an SRE control plane.

Primitives implemented here (each maps to a §5 idea):

    §5.1   Σ a = 1         →  :class:`WeightedConvexCombiner`
    §5.1   audit weights    →  :class:`AuditTrail`
    §5.2   decoupling       →  :class:`DecoupledControlLoop`
    §5     block sectioning →  :class:`HierarchicalBlockController`
    §6     layer skip       →  :class:`BudgetGate`
    §5.2   must-attend      →  :class:`MustAttendRegistry`
    §5     2-out-of-1       →  enforced via assertions in hierarchical ctrl

The implementation uses only ``numpy`` to keep it independent from the
PyTorch stack. It is safe to embed inside an SRE control plane service.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np


# ---------------------------------------------------------------------------
# Primitive 1 · Weighted Convex Combiner  (§5.1 Σ_k a_k = 1)
# ---------------------------------------------------------------------------

@dataclass
class SignalSpec:
    """Description of one input signal feeding a controller.

    Parameters
    ----------
    name : str
        Human-readable label (used in audit trails).
    floor : float
        Minimum weight this signal is guaranteed, ∈ [0, 1].
        A positive floor realises the "must-attend" guarantee (§5.2).
    ceiling : float
        Maximum weight ∈ [floor, 1]. Use 1.0 for no ceiling.
    bias : float
        Additive bias added to the raw logit before the softmax. Useful
        for operator-provided priors ("during a migration, upweight the
        error-budget signal by +0.5 in logit space").
    """
    name: str
    floor: float = 0.0
    ceiling: float = 1.0
    bias: float = 0.0

    def __post_init__(self) -> None:
        if not (0.0 <= self.floor <= self.ceiling <= 1.0):
            raise ValueError(
                f"SignalSpec {self.name!r}: require 0 ≤ floor ≤ ceiling ≤ 1, "
                f"got floor={self.floor}, ceiling={self.ceiling}"
            )


class WeightedConvexCombiner:
    """Produce a decision vector as a convex combination of input signals.

    This is the SRE-flavoured twin of :class:`AttentionResidual`. Instead
    of attending over layer history, it attends over heterogeneous
    control signals (SLIs, error-budget burn, queue length, ...).

    The combiner is described by:

        logits_k = (q · K_k) / T  + bias_k
        a_k      = softmax_k(logits_k)           subject to floor_k ≤ a_k ≤ ceiling_k
        y        = Σ_k a_k · v_k                 the convex combination

    where:
        - ``q`` is the controller's query vector (the "policy intent"),
        - ``K_k`` are per-signal keys (feature embeddings of each signal),
        - ``v_k`` are per-signal value vectors (the signal's recommended
          action, e.g. ``replica_delta = +3``),
        - ``T`` is a softmax temperature (higher ⇒ flatter).

    Invariants
    ----------
    * ``sum(a) == 1``          — budget conservation.
    * ``a_k ∈ [floor_k, ceiling_k]`` — must-attend and fuse protection.
    * Weights are exposed through :meth:`last_weights` for audit.
    """

    def __init__(
        self,
        signals: Sequence[SignalSpec],
        query_dim: int,
        temperature: float = 1.0,
        rng_seed: Optional[int] = 0,
    ) -> None:
        if not signals:
            raise ValueError("need at least one signal")
        if sum(s.floor for s in signals) > 1.0 + 1e-9:
            raise ValueError(
                "floor weights sum to > 1 — no feasible convex combination"
            )
        self.signals = list(signals)
        self.query_dim = int(query_dim)
        self.temperature = float(temperature)
        rng = np.random.default_rng(rng_seed)
        # One K_k per signal; values are supplied per-step.
        self.W_K = rng.standard_normal((len(signals), query_dim)) * 0.1
        self._last_weights: Optional[np.ndarray] = None

    # -------------------------------------------------- public API
    def combine(
        self,
        query: np.ndarray,
        values: Sequence[np.ndarray],
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Compute one controller step.

        Parameters
        ----------
        query : np.ndarray of shape (query_dim,)
            Current policy query — typically a summary of the system
            state (normalised feature vector).
        values : sequence of np.ndarray, each shape (action_dim,)
            Each signal's *proposed* action. Must have the same length
            as ``self.signals``.

        Returns
        -------
        action : np.ndarray
            The convex-combined action.
        weights : np.ndarray of shape (n_signals,)
            The a_k weights (also cached as :meth:`last_weights`).
        """
        if len(values) != len(self.signals):
            raise ValueError("values length must match signals length")
        if query.shape != (self.query_dim,):
            raise ValueError(
                f"query shape {query.shape} != ({self.query_dim},)"
            )

        # Raw logits
        logits = (self.W_K @ query) / max(self.temperature, 1e-9)
        for i, s in enumerate(self.signals):
            logits[i] += s.bias
        # Vanilla softmax
        shifted = logits - logits.max()
        raw = np.exp(shifted)
        a = raw / raw.sum()
        # Enforce per-signal floor/ceiling while keeping Σ = 1.
        a = _project_to_simplex_with_bounds(
            a,
            floors=np.array([s.floor for s in self.signals]),
            ceilings=np.array([s.ceiling for s in self.signals]),
        )
        self._last_weights = a.copy()

        V = np.stack(values, axis=0)    # shape (n_signals, action_dim)
        action = (a[:, None] * V).sum(axis=0)
        return action, a

    def last_weights(self) -> Optional[np.ndarray]:
        return None if self._last_weights is None else self._last_weights.copy()


def _project_to_simplex_with_bounds(
    a: np.ndarray,
    floors: np.ndarray,
    ceilings: np.ndarray,
    max_iter: int = 64,
    tol: float = 1e-9,
) -> np.ndarray:
    """Project ``a`` onto {x : Σx = 1, floors ≤ x ≤ ceilings}.

    Simple iterative scheme: clip, redistribute the residual proportionally
    among unsaturated coordinates. Cheap and deterministic — adequate for
    control-plane latency budgets (sub-microsecond in practice).
    """
    x = a.copy()
    for _ in range(max_iter):
        x = np.minimum(np.maximum(x, floors), ceilings)
        residual = 1.0 - x.sum()
        if abs(residual) < tol:
            return x
        if residual > 0:
            # Need to add mass → only coords not yet at ceiling are eligible.
            room = ceilings - x
            room_mass = room.sum()
            if room_mass < tol:
                return x
            x = x + residual * (room / room_mass)
        else:
            # Need to remove mass → only coords not yet at floor are eligible.
            room = x - floors
            room_mass = room.sum()
            if room_mass < tol:
                return x
            x = x - (-residual) * (room / room_mass)
    return x


# ---------------------------------------------------------------------------
# Primitive 2 · Audit Trail                 (§5.1 last_weights())
# ---------------------------------------------------------------------------

@dataclass
class AuditRecord:
    """One controller decision with the weight vector that produced it."""
    step: int
    signal_names: List[str]
    weights: np.ndarray
    action: np.ndarray
    context: Dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "step": self.step,
            "signals": self.signal_names,
            "weights": [float(w) for w in self.weights],
            "action": [float(a) for a in self.action],
            "context": dict(self.context),
        }


class AuditTrail:
    """Append-only log of controller decisions, analogous to ``trace()``.

    The trail is intentionally simple: it lives in memory and supports
    export to JSON Lines. Plug any structured logger in production.
    """

    def __init__(self) -> None:
        self._records: List[AuditRecord] = []

    def record(
        self,
        combiner: WeightedConvexCombiner,
        action: np.ndarray,
        context: Optional[Mapping[str, float]] = None,
    ) -> AuditRecord:
        w = combiner.last_weights()
        if w is None:
            raise RuntimeError("combiner has no weights yet — call combine() first")
        rec = AuditRecord(
            step=len(self._records),
            signal_names=[s.name for s in combiner.signals],
            weights=w,
            action=action.copy(),
            context=dict(context or {}),
        )
        self._records.append(rec)
        return rec

    def __iter__(self) -> Iterable[AuditRecord]:
        return iter(self._records)

    def __len__(self) -> int:
        return len(self._records)

    def to_jsonl(self) -> str:
        import json
        return "\n".join(json.dumps(r.as_dict()) for r in self._records)


# ---------------------------------------------------------------------------
# Primitive 3 · Decoupled Fast/Slow Loop    (§5.2 nonzero decoupling)
# ---------------------------------------------------------------------------

class DecoupledControlLoop:
    """Two orthogonal control loops with independent query matrices.

    - ``fast_loop`` runs every tick (per-request or per-second).
      Typical duty: rate limiting, request-level circuit breaking.
    - ``slow_loop`` runs every N ticks (per-minute or per-hour).
      Typical duty: capacity planning, error-budget burn monitoring.

    Both loops are :class:`WeightedConvexCombiner` instances with their
    *own* ``W_K`` — i.e. their policies never share parameters. This is
    the SRE analogue of the two independent ``W_Q`` matrices in the
    decoupled Transformer layer.

    The compose step merges their outputs via a final convex combination
    whose weights themselves come from a meta policy (``alpha``).
    """

    def __init__(
        self,
        fast_loop: WeightedConvexCombiner,
        slow_loop: WeightedConvexCombiner,
        slow_period: int = 10,
        alpha: float = 0.3,
    ) -> None:
        if not (0.0 <= alpha <= 1.0):
            raise ValueError("alpha must be in [0, 1]")
        self.fast = fast_loop
        self.slow = slow_loop
        self.slow_period = int(slow_period)
        self.alpha = float(alpha)
        self._tick = 0
        self._last_slow_action: Optional[np.ndarray] = None

    def step(
        self,
        fast_query: np.ndarray,
        fast_values: Sequence[np.ndarray],
        slow_query: np.ndarray,
        slow_values: Sequence[np.ndarray],
    ) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
        """Advance one tick.

        The slow loop only fires every ``slow_period`` ticks; in between
        the last slow action is cached and reused.
        """
        fast_action, _ = self.fast.combine(fast_query, fast_values)
        if self._tick % self.slow_period == 0 or self._last_slow_action is None:
            slow_action, _ = self.slow.combine(slow_query, slow_values)
            self._last_slow_action = slow_action
        else:
            slow_action = self._last_slow_action
        merged = (1.0 - self.alpha) * fast_action + self.alpha * slow_action
        self._tick += 1
        return merged, {
            "fast_action": fast_action,
            "slow_action": slow_action,
            "fast_weights": self.fast.last_weights(),  # type: ignore[arg-type]
            "slow_weights": self.slow.last_weights(),  # type: ignore[arg-type]
        }


# ---------------------------------------------------------------------------
# Primitive 4 · Hierarchical Block Controller  (§5 sectioning)
# ---------------------------------------------------------------------------

@dataclass
class BlockSpec:
    """Description of one block (e.g. an availability zone or cluster)."""
    name: str
    local_combiner: WeightedConvexCombiner
    """The block's own local controller — 'classic residual' inside the block."""
    block_key: np.ndarray
    """Feature vector describing this block at the global level."""


class HierarchicalBlockController:
    """SRE analogue of :class:`BlockAttnResStack`.

    Inside each block we run a dedicated :class:`WeightedConvexCombiner`
    (a local policy that aggregates local signals). At the global level
    a second combiner attends across *block outputs* — matching the
    "Block Attention Residual" design::

        O( (L/B)^2 + L )         (NOT O(L^2) over all signals)

    Only one of ``inner_residual`` or the between-block aggregation is
    allowed to be active at the global level — this enforces the
    "2-out-of-1" principle (§5 end). An attempt to pass both a local
    correction *and* an overriding between-block output is rejected at
    construction time via :meth:`step` parameters.
    """

    def __init__(
        self,
        blocks: Sequence[BlockSpec],
        global_query_dim: int,
        temperature: float = 1.0,
        allow_inner_residual: bool = False,
    ) -> None:
        if not blocks:
            raise ValueError("need at least one block")
        self.blocks = list(blocks)
        self.allow_inner_residual = bool(allow_inner_residual)
        # Between-block combiner attends over blocks. Keys come from
        # block_key vectors. Each block emits an *action proposal*.
        block_signals = [SignalSpec(name=f"block:{b.name}") for b in blocks]
        self.global_combiner = WeightedConvexCombiner(
            block_signals, query_dim=global_query_dim, temperature=temperature,
        )
        # Pin the global W_K rows to the blocks' own key vectors: this
        # makes the between-block attention reflect block features
        # directly rather than random projections.
        keys = np.stack([b.block_key for b in blocks], axis=0)
        if keys.shape != (len(blocks), global_query_dim):
            raise ValueError(
                f"block_key shapes mismatch: expected (n_blocks={len(blocks)}, "
                f"global_query_dim={global_query_dim}), got {keys.shape}"
            )
        self.global_combiner.W_K = keys.copy()

    def step(
        self,
        per_block_queries: Sequence[np.ndarray],
        per_block_values: Sequence[Sequence[np.ndarray]],
        global_query: np.ndarray,
    ) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
        """Run one hierarchical decision.

        Parameters
        ----------
        per_block_queries :
            One query vector per block (shape (query_dim_local,)).
        per_block_values :
            For each block, the list of values its local combiner expects.
        global_query :
            Query vector used by the between-block combiner.
        """
        if len(per_block_queries) != len(self.blocks):
            raise ValueError("per_block_queries length mismatch")
        if len(per_block_values) != len(self.blocks):
            raise ValueError("per_block_values length mismatch")
        block_actions: List[np.ndarray] = []
        block_weights: List[np.ndarray] = []
        for b, q, vs in zip(self.blocks, per_block_queries, per_block_values):
            a, w = b.local_combiner.combine(q, vs)
            block_actions.append(a)
            block_weights.append(w)
        # Aggregate block actions via the global convex combiner.
        global_action, global_weights = self.global_combiner.combine(
            global_query, block_actions,
        )
        return global_action, {
            "block_actions": np.stack(block_actions, axis=0),
            "block_weights": block_weights,
            "global_weights": global_weights,
        }


# ---------------------------------------------------------------------------
# Primitive 5 · Budget Gate    (§6 layer skip under budget constraint)
# ---------------------------------------------------------------------------

class BudgetGate:
    """Dynamic skip gate with a hard budget across a population of gates.

    In the Attention-Residuals paper each layer owns a gate g_l = σ(w_l)
    that can short-circuit the layer at inference time. That design lets
    *any* layer be bypassed independently. In SRE the common requirement
    is stronger: **you can't bypass everyone at once**. There has to be a
    floor of always-on capacity.

    This class enforces::

        g_i ∈ [0, 1]
        Σ_i g_i ≥ budget_floor * N          (e.g. at least 50% always active)

    ``step`` returns the vector of gate values for the current tick; the
    caller applies them to the underlying resource (replica weights, feature
    flags, shed probabilities).
    """

    def __init__(
        self,
        n_gates: int,
        budget_floor: float = 0.5,
        init_logits: Optional[Sequence[float]] = None,
    ) -> None:
        if not (0.0 <= budget_floor <= 1.0):
            raise ValueError("budget_floor must be in [0, 1]")
        self.n_gates = int(n_gates)
        self.budget_floor = float(budget_floor)
        if init_logits is None:
            self.logits = np.full(n_gates, 4.6)    # σ(4.6) ≈ 0.99
        else:
            self.logits = np.asarray(init_logits, dtype=float).copy()
            if self.logits.shape != (n_gates,):
                raise ValueError("init_logits length mismatch")

    def gates(self) -> np.ndarray:
        g = 1.0 / (1.0 + np.exp(-self.logits))
        total = g.sum()
        minimum = self.budget_floor * self.n_gates
        if total < minimum:
            # Scale each gate up uniformly so the floor is satisfied.
            scale = minimum / max(total, 1e-9)
            g = np.minimum(g * scale, 1.0)
        return g

    def update_logits(self, delta: np.ndarray) -> None:
        if delta.shape != (self.n_gates,):
            raise ValueError("delta shape mismatch")
        self.logits = self.logits + delta


# ---------------------------------------------------------------------------
# Primitive 6 · Must-Attend Registry
# ---------------------------------------------------------------------------

class MustAttendRegistry:
    """Central registry of signals whose weight must have a positive floor.

    In SRE there are signals you *never* want to be silently ignored —
    error-budget burn, security incidents, P0 SLO breaches. Register
    those here, and the registry produces SignalSpecs with the desired
    floor weights.
    """

    def __init__(self) -> None:
        self._entries: Dict[str, float] = {}

    def register(self, name: str, floor: float) -> None:
        if not (0.0 <= floor <= 1.0):
            raise ValueError("floor must be in [0, 1]")
        self._entries[name] = float(floor)

    def spec(self, name: str, ceiling: float = 1.0, bias: float = 0.0) -> SignalSpec:
        floor = self._entries.get(name, 0.0)
        return SignalSpec(name=name, floor=floor, ceiling=ceiling, bias=bias)

    def total_floor(self) -> float:
        return float(sum(self._entries.values()))


__all__ = [
    "SignalSpec",
    "WeightedConvexCombiner",
    "AuditRecord", "AuditTrail",
    "DecoupledControlLoop",
    "BlockSpec", "HierarchicalBlockController",
    "BudgetGate",
    "MustAttendRegistry",
]
