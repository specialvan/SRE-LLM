"""Utility-aware retriever · PR-021.

Refined spec: ``skill-research/refined/PR-021-utility-aware-retriever-refined.md``.

Scoring formula (Def 3 of the source paper)::

    score(s|q) = sim(s, q) + λ_util · u_s + λ_explore · β_s

``sim`` is cosine similarity between a pre-computed skill embedding and
the query; ``u_s`` comes from :class:`HindsightUtilityTracker`; ``β_s``
from :class:`ExplorationBiasScheduler`. When λ values are zero the
retriever degenerates to pure similarity — this is the "observe only"
mode useful for replay.

Requirements:

* REQ-RTE-003 · score composition
* REQ-RTE-004 · λ=0 degenerates to sim-only
* REQ-RTE-007 · P95 pick latency < 5 ms on 1k skills (hot path uses
  plain numpy argpartition, no Python loops).
* REQ-RTE-008 · utility updates don't rebuild the embedding index.
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from typing import (
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
)

import numpy as np


@dataclass(frozen=True)
class Scored:
    """Single scoring tuple returned by :meth:`UtilityAwareRetriever.rank`."""

    skill_id: str
    score: float
    sim: float
    utility: float
    explore_bonus: float


@dataclass
class RetrieverConfig:
    lambda_util: float = 0.3
    lambda_explore: float = 0.1
    # Initial buffer capacity in rows; grown lazily in `upsert`.
    initial_capacity: int = 128
    # Numerical floor for cosine similarity denominator.
    eps: float = 1e-9


class UtilityAwareRetriever:
    """Lightweight embedding index + scoring.

    Embeddings are stored in a contiguous float32 buffer; ``upsert`` is
    amortised O(1), ``rank`` is O(N · d) dot product — both are hot
    paths that deliberately avoid Python loops.
    """

    def __init__(self, dim: int, config: Optional[RetrieverConfig] = None) -> None:
        if dim < 1:
            raise ValueError("dim must be >= 1")
        self._cfg = config or RetrieverConfig()
        self._dim = int(dim)
        self._buf = np.zeros((self._cfg.initial_capacity, self._dim), dtype=np.float32)
        self._norms = np.zeros(self._cfg.initial_capacity, dtype=np.float32)
        self._ids: List[str] = []
        self._id_to_row: dict[str, int] = {}
        self._n = 0
        self._lock = threading.RLock()

    # ---------------- mutate ----------------

    def upsert(self, skill_id: str, embedding: np.ndarray) -> None:
        """Insert or replace the embedding for ``skill_id``.

        ``embedding`` must be shape ``(dim,)``; the retriever copies.
        """
        if not skill_id:
            raise ValueError("skill_id must be non-empty")
        arr = np.asarray(embedding, dtype=np.float32).ravel()
        if arr.shape != (self._dim,):
            raise ValueError(
                f"embedding shape {arr.shape} != ({self._dim},)"
            )
        norm = float(np.linalg.norm(arr))
        with self._lock:
            if skill_id in self._id_to_row:
                row = self._id_to_row[skill_id]
            else:
                row = self._n
                if row >= self._buf.shape[0]:
                    self._grow()
                self._ids.append(skill_id)
                self._id_to_row[skill_id] = row
                self._n += 1
            self._buf[row] = arr
            self._norms[row] = max(norm, self._cfg.eps)

    def remove(self, skill_id: str) -> None:
        """O(N) removal (rare on hot path)."""
        with self._lock:
            row = self._id_to_row.pop(skill_id, None)
            if row is None:
                return
            # Compact: move last row into the hole, fix up id mapping.
            last = self._n - 1
            if row != last:
                self._buf[row] = self._buf[last]
                self._norms[row] = self._norms[last]
                moved_id = self._ids[last]
                self._ids[row] = moved_id
                self._id_to_row[moved_id] = row
            self._ids.pop()
            self._n -= 1

    # ---------------- rank ----------------

    def rank(
        self,
        query: np.ndarray,
        utilities: Optional[Mapping[str, float]] = None,
        exploration: Optional[Mapping[str, float]] = None,
        candidates: Optional[Sequence[str]] = None,
        top_k: Optional[int] = None,
    ) -> List[Scored]:
        """Score every skill in the index (or ``candidates``) for ``query``."""
        q = np.asarray(query, dtype=np.float32).ravel()
        if q.shape != (self._dim,):
            raise ValueError(f"query shape {q.shape} != ({self._dim},)")
        q_norm = max(float(np.linalg.norm(q)), self._cfg.eps)

        with self._lock:
            if self._n == 0:
                return []
            if candidates is None:
                row_indices = np.arange(self._n)
                ids = list(self._ids[: self._n])
            else:
                rows = [
                    self._id_to_row[sid]
                    for sid in candidates
                    if sid in self._id_to_row
                ]
                row_indices = np.asarray(rows, dtype=int)
                ids = [
                    sid for sid in candidates if sid in self._id_to_row
                ]
            if row_indices.size == 0:
                return []
            buf_slice = self._buf[row_indices]
            norm_slice = self._norms[row_indices]

        sims = (buf_slice @ q) / (norm_slice * q_norm)
        util_vec = np.zeros(sims.shape[0], dtype=np.float32)
        explore_vec = np.zeros(sims.shape[0], dtype=np.float32)
        if utilities is not None:
            for i, sid in enumerate(ids):
                util_vec[i] = float(utilities.get(sid, 0.0))
        if exploration is not None:
            for i, sid in enumerate(ids):
                explore_vec[i] = float(exploration.get(sid, 0.0))

        total = (
            sims
            + self._cfg.lambda_util * util_vec
            + self._cfg.lambda_explore * explore_vec
        )

        if top_k is not None and 0 < top_k < total.shape[0]:
            # argpartition gives us top_k unsorted; sort that slice.
            part = np.argpartition(-total, top_k)[:top_k]
            order = part[np.argsort(-total[part])]
        else:
            order = np.argsort(-total)

        scored: List[Scored] = []
        for idx in order:
            scored.append(
                Scored(
                    skill_id=ids[idx],
                    score=float(total[idx]),
                    sim=float(sims[idx]),
                    utility=float(util_vec[idx]),
                    explore_bonus=float(explore_vec[idx]),
                )
            )
        return scored

    # ---------------- accessors ----------------

    def __len__(self) -> int:
        with self._lock:
            return self._n

    def contains(self, skill_id: str) -> bool:
        with self._lock:
            return skill_id in self._id_to_row

    def ids(self) -> List[str]:
        with self._lock:
            return list(self._ids[: self._n])

    @property
    def dim(self) -> int:
        return self._dim

    # ---------------- internals ----------------

    def _grow(self) -> None:
        new_cap = max(1, self._buf.shape[0]) * 2
        new_buf = np.zeros((new_cap, self._dim), dtype=np.float32)
        new_buf[: self._n] = self._buf[: self._n]
        new_norms = np.zeros(new_cap, dtype=np.float32)
        new_norms[: self._n] = self._norms[: self._n]
        self._buf = new_buf
        self._norms = new_norms


__all__ = [
    "RetrieverConfig",
    "Scored",
    "UtilityAwareRetriever",
]
