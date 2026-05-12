"""Trace → skill miner · PR-001.

Refined spec: ``skill-research/refined/PR-001-trace2skill-miner-refined.md``.

Five-step pipeline:

1. **Filter high-cost records** (quantile).
2. **Cluster by trigger features** (here: a lightweight k-means).
3. **Propose targets per cluster** using pluggable ``PatchRule`` objects.
4. **Hash & dedupe** by content; guaranteed idempotent ``patch_id``.
5. **Cap** at ``max_candidates`` preserving must-attend-touching targets.

The miner is **offline** — it takes a list of :class:`AuditRecord`
already produced by a combiner (we read them from
:class:`attention_residuals.sre_control.AuditTrail` or directly).

Requirements:

* REQ-EVD-004 · produce candidate when support ≥ min
* REQ-EVD-005 · deterministic patch_id
* REQ-EVD-006 · reject floor violations
* REQ-EVD-009 · bound candidate count
* REQ-EVD-010 · attach registry_hash
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import (
    Callable,
    List,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    Tuple,
)

import numpy as np

from attention_residuals.sre_control import AuditRecord
from attention_residuals.skill.trajectory.merger import MustAttendSnapshot
from attention_residuals.skill.types import (
    PatchField,
    PatchTarget,
    SkillPatchCandidate,
    compute_patch_id,
)

_LOGGER = logging.getLogger(__name__)

LossFn = Callable[[AuditRecord], float]


class PatchRule(Protocol):
    """One rule that looks at a cluster and proposes 0..N ``PatchTarget``."""

    name: str

    def propose(
        self,
        cluster: Sequence[AuditRecord],
        snapshot: "MustAttendSnapshot",
    ) -> Sequence[PatchTarget]: ...


@dataclass
class MinerConfig:
    support_min: int = 10
    cost_quantile: float = 0.8
    max_candidates: int = 50
    cluster_k_max: int = 4
    trigger_features: Tuple[str, ...] = ()
    score_cap: float = 1e6
    rng_seed: int = 42


# -----------------------------------------------------------------------------
# Default PatchRule set (spec §2.3 of refined/PR-001)
# -----------------------------------------------------------------------------


@dataclass
class FloorUpRule:
    """Rule A: signal under-attended inside a high-cost cluster → floor↑."""

    name: str = "floor_up"
    low_threshold: float = 0.05
    delta_cap: float = 0.05

    def propose(
        self,
        cluster: Sequence[AuditRecord],
        snapshot: MustAttendSnapshot,
    ) -> Sequence[PatchTarget]:
        if not cluster:
            return []
        weights = np.stack([r.weights for r in cluster])
        signals = cluster[0].signal_names
        result: list[PatchTarget] = []
        for i, name in enumerate(signals):
            w_mean = float(weights[:, i].mean())
            current = snapshot.current_floor(name)
            gap = current - w_mean
            if gap > self.low_threshold:
                delta = min(self.delta_cap, gap)
                # Floor must stay in [0,1]: current + delta ≤ 1
                delta = max(0.0, min(delta, 1.0 - current))
                if delta <= 0:
                    continue
                result.append(
                    PatchTarget(
                        signal_name=name,
                        field=PatchField.FLOOR,
                        delta=float(delta),
                        rationale=(
                            f"cluster mean weight {w_mean:.3f} under floor "
                            f"{current:.3f} by {gap:.3f}"
                        )[:200],
                    )
                )
        return result


@dataclass
class CeilingDownRule:
    """Rule C: one signal dominates while loss stays high → ceiling↓."""

    name: str = "ceiling_down"
    dominance: float = 0.6
    delta_cap: float = 0.1

    def propose(
        self,
        cluster: Sequence[AuditRecord],
        snapshot: MustAttendSnapshot,
    ) -> Sequence[PatchTarget]:
        if not cluster:
            return []
        weights = np.stack([r.weights for r in cluster])
        signals = cluster[0].signal_names
        result: list[PatchTarget] = []
        for i, name in enumerate(signals):
            w_mean = float(weights[:, i].mean())
            if w_mean >= self.dominance:
                current_ceiling = snapshot.current_ceiling(name)
                delta = -min(self.delta_cap, current_ceiling - 0.1)
                if delta >= 0:
                    continue
                result.append(
                    PatchTarget(
                        signal_name=name,
                        field=PatchField.CEILING,
                        delta=float(delta),
                        rationale=(
                            f"signal {name} dominates (w̄={w_mean:.3f}); cap ceiling"
                        )[:200],
                    )
                )
        return result


# -----------------------------------------------------------------------------
# Miner
# -----------------------------------------------------------------------------


class Trace2SkillMiner:
    """Offline miner producing :class:`SkillPatchCandidate` from audit logs.

    Parameters
    ----------
    loss_fn : callable
        Per-record cost function. Defaults to summing the first numeric
        ``loss``-like context key if present, else 0. Inject a function
        that queries :class:`TemporalCreditAssigner` for realistic use.
    rules : sequence of PatchRule
        Plug-in rules. If omitted, the default pair (FloorUpRule,
        CeilingDownRule) is used.
    config : MinerConfig
    """

    _DEFAULT_LOSS_KEYS: Tuple[str, ...] = (
        "slo_breach",
        "loss",
        "cost",
        "controller_error",
    )

    def __init__(
        self,
        loss_fn: Optional[LossFn] = None,
        rules: Optional[Sequence[PatchRule]] = None,
        config: Optional[MinerConfig] = None,
    ) -> None:
        # Ergonomic fallback: callers who do ``Trace2SkillMiner(MinerConfig(...))``
        # — a natural mistake given the spec naming — still get what they want.
        if isinstance(loss_fn, MinerConfig) and config is None:
            config = loss_fn
            loss_fn = None
        self._cfg = config or MinerConfig()
        self._rules = list(rules) if rules else [FloorUpRule(), CeilingDownRule()]
        self._loss_fn: LossFn = loss_fn or self._default_loss
        self._rng = np.random.default_rng(self._cfg.rng_seed)

    # -------------------------------------------------- public API

    def mine(
        self,
        records: Sequence[AuditRecord],
        snapshot: MustAttendSnapshot,
    ) -> List[SkillPatchCandidate]:
        """Run the 5-step pipeline; returns a sorted list of candidates."""
        if not records:
            return []

        losses = np.array([self._loss_fn(r) for r in records], dtype=float)
        if len(losses) == 0 or float(losses.max()) <= 0.0:
            return []

        high_cost_records = self._filter_high_cost(records, losses)
        if len(high_cost_records) < self._cfg.support_min:
            # Not enough signal to mine candidates.
            return []

        clusters = self._cluster_by_trigger(high_cost_records)
        all_candidates: list[SkillPatchCandidate] = []
        for cluster_records in clusters.values():
            if len(cluster_records) < self._cfg.support_min:
                continue
            cluster_losses = np.array([self._loss_fn(r) for r in cluster_records])
            avg_cost = float(cluster_losses.mean()) if cluster_losses.size else 0.0
            proposed: list[PatchTarget] = []
            for rule in self._rules:
                proposed.extend(rule.propose(cluster_records, snapshot))
            targets = self._dedupe(proposed)
            if not targets:
                continue
            # REQ-EVD-006: reject if the whole candidate would violate Σfloor ≤ 1.
            if not self._is_floor_feasible(targets, snapshot):
                _LOGGER.debug("dropping candidate that would exceed Σfloor")
                continue

            trigger = self._cluster_trigger(cluster_records)
            support = len(cluster_records)
            evidence_steps = tuple(int(r.step) for r in cluster_records)

            pid = compute_patch_id(tuple(targets), trigger)
            score = float(
                min(self._cfg.score_cap, support * avg_cost)
            )
            candidate = SkillPatchCandidate(
                patch_id=pid,
                trigger=trigger,
                targets=tuple(targets),
                evidence_steps=evidence_steps,
                support=support,
                avg_cost_before=avg_cost,
                score=score,
                registry_hash=snapshot.registry_hash,
            )
            all_candidates.append(candidate)

        return self._cap(all_candidates, snapshot)

    # -------------------------------------------------- stage helpers

    def _filter_high_cost(
        self, records: Sequence[AuditRecord], losses: np.ndarray
    ) -> List[AuditRecord]:
        if self._cfg.cost_quantile <= 0:
            return list(records)
        threshold = float(np.quantile(losses, self._cfg.cost_quantile))
        return [r for r, l in zip(records, losses) if l >= threshold]

    def _cluster_by_trigger(
        self, records: Sequence[AuditRecord]
    ) -> Mapping[int, List[AuditRecord]]:
        features = self._cfg.trigger_features
        if not features:
            return {0: list(records)}

        x = np.array(
            [
                [float(r.context.get(k, 0.0)) for k in features]
                for r in records
            ],
            dtype=float,
        )
        # Standardise so k-means doesn't get dominated by a single axis.
        std = x.std(axis=0)
        std = np.where(std < 1e-9, 1.0, std)
        x_norm = (x - x.mean(axis=0)) / std

        k = self._choose_k(x_norm)
        labels = self._kmeans(x_norm, k, max_iter=30)
        out: dict[int, List[AuditRecord]] = {i: [] for i in range(k)}
        for label, r in zip(labels, records):
            out[int(label)].append(r)
        return out

    def _choose_k(self, x: np.ndarray) -> int:
        k = min(self._cfg.cluster_k_max, max(1, x.shape[0] // max(1, self._cfg.support_min)))
        return max(1, k)

    def _kmeans(self, x: np.ndarray, k: int, max_iter: int = 30) -> np.ndarray:
        n = x.shape[0]
        if k <= 1 or n <= 1:
            return np.zeros(n, dtype=int)
        idx = self._rng.choice(n, size=k, replace=False)
        centers = x[idx].copy()
        labels = np.zeros(n, dtype=int)
        for _ in range(max_iter):
            # assign
            dists = ((x[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
            new_labels = dists.argmin(axis=1)
            if np.array_equal(new_labels, labels) and _ > 0:
                break
            labels = new_labels
            # update
            for j in range(k):
                mask = labels == j
                if mask.any():
                    centers[j] = x[mask].mean(axis=0)
        return labels

    def _cluster_trigger(self, cluster: Sequence[AuditRecord]) -> Mapping[str, float]:
        if not self._cfg.trigger_features:
            return {}
        return {
            k: float(np.mean([r.context.get(k, 0.0) for r in cluster]))
            for k in self._cfg.trigger_features
        }

    def _dedupe(self, targets: Sequence[PatchTarget]) -> List[PatchTarget]:
        by_key: dict[Tuple[str, PatchField], PatchTarget] = {}
        for t in targets:
            k = (t.signal_name, t.field)
            keep = by_key.get(k)
            if keep is None or abs(t.delta) > abs(keep.delta):
                by_key[k] = t
        return list(by_key.values())

    @staticmethod
    def _is_floor_feasible(
        targets: Sequence[PatchTarget], snapshot: MustAttendSnapshot
    ) -> bool:
        delta_total = sum(t.delta for t in targets if t.field is PatchField.FLOOR)
        return snapshot.total_floor() + delta_total <= 1.0 + 1e-9

    def _cap(
        self,
        candidates: Sequence[SkillPatchCandidate],
        snapshot: MustAttendSnapshot,
    ) -> List[SkillPatchCandidate]:
        # Stable sort: (touches_must_attend, score) descending.
        must_attend = set(snapshot.floors.keys())

        def sort_key(c: SkillPatchCandidate) -> tuple[int, float, str]:
            touches = int(any(t.signal_name in must_attend for t in c.targets))
            return (touches, c.score, c.patch_id)

        ordered = sorted(candidates, key=sort_key, reverse=True)
        return ordered[: self._cfg.max_candidates]

    # -------------------------------------------------- defaults

    @classmethod
    def _default_loss(cls, record: AuditRecord) -> float:
        for key in cls._DEFAULT_LOSS_KEYS:
            if key in record.context:
                try:
                    return max(0.0, float(record.context[key]))
                except (TypeError, ValueError):
                    continue
        return 0.0


__all__ = [
    "CeilingDownRule",
    "FloorUpRule",
    "LossFn",
    "MinerConfig",
    "PatchRule",
    "Trace2SkillMiner",
]
