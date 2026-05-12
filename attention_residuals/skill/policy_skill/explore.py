"""Exploration bias scheduler · PR-022.

Refined spec: ``skill-research/04-route-policy-skill-couple/PR-022-*``.

Invariant (REQ-RTE-010/011):

* Per-skill ``effective_beta`` starts at ``beta0`` and decays as
  ``beta0 / sqrt(max(1, n - min_protection_uses + 1))`` once the
  protection window closes.
* Aggregate budget ``Σ effective_beta ≤ cfg.global_budget`` — if the
  raw sum exceeds the budget, every skill is scaled proportionally.

The scheduler is lock-free hot path: :meth:`notify_used` just increments
a counter; :meth:`effective_beta` runs a pure function over the counter.
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from typing import Iterable, Mapping, Optional


@dataclass
class ExploreConfig:
    beta0: float = 0.1
    min_protection_uses: int = 20
    global_budget: float = 1.0


class ExplorationBiasScheduler:
    def __init__(self, config: Optional[ExploreConfig] = None) -> None:
        self._cfg = config or ExploreConfig()
        if self._cfg.beta0 < 0:
            raise ValueError("beta0 must be >= 0")
        if self._cfg.min_protection_uses < 0:
            raise ValueError("min_protection_uses must be >= 0")
        if self._cfg.global_budget <= 0:
            raise ValueError("global_budget must be > 0")
        self._uses: dict[str, int] = {}
        self._lock = threading.RLock()

    # ---------------- mutate ----------------

    def notify_used(self, skill_id: str) -> None:
        if not skill_id:
            raise ValueError("skill_id must be non-empty")
        with self._lock:
            self._uses[skill_id] = self._uses.get(skill_id, 0) + 1

    def forget(self, skill_id: str) -> None:
        with self._lock:
            self._uses.pop(skill_id, None)

    # ---------------- query ----------------

    def raw_beta(self, skill_id: str) -> float:
        """Pre-budget effective β for a single skill."""
        with self._lock:
            n = self._uses.get(skill_id, 0)
        return self._raw_from_n(n)

    def _raw_from_n(self, n: int) -> float:
        cfg = self._cfg
        if cfg.beta0 == 0:
            return 0.0
        if n <= cfg.min_protection_uses:
            return cfg.beta0
        # After protection: decay as 1 / sqrt(1 + n - min_protection_uses).
        decay = math.sqrt(max(1, n - cfg.min_protection_uses))
        return cfg.beta0 / decay

    def effective_beta(self, skill_id: str) -> float:
        """Budget-adjusted β for one skill."""
        with self._lock:
            snapshot = self._budget_adjusted_snapshot()
        return float(snapshot.get(skill_id, 0.0))

    def snapshot(self) -> Mapping[str, float]:
        with self._lock:
            return self._budget_adjusted_snapshot()

    def _budget_adjusted_snapshot(self) -> dict[str, float]:
        raws = {sid: self._raw_from_n(n) for sid, n in self._uses.items()}
        total = sum(raws.values())
        if total <= self._cfg.global_budget or total == 0.0:
            return raws
        scale = self._cfg.global_budget / total
        return {sid: beta * scale for sid, beta in raws.items()}

    # Convenience for cold skills (not yet observed): returns beta0.
    def default_beta(self) -> float:
        return float(self._cfg.beta0)

    def __len__(self) -> int:
        with self._lock:
            return len(self._uses)


__all__ = [
    "ExplorationBiasScheduler",
    "ExploreConfig",
]
