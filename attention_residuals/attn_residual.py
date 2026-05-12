"""Explicit vertical self-attention over layer history (section 5.1).

Formulas
--------
    a_{l,k} = softmax_k((q_l · K_k) / sqrt(d))
    AttnRes_l(x_0, ..., x_l) = sum_{k=0..l} a_{l,k} · x_k
    sum_k a_{l,k} = 1
    x_{l+1} = AttnRes_l + F_l(x_l)

Shapes
------
    Each history tensor x_k has shape ``[B, T, D]`` (batch x tokens x features).
    The vertical attention operates along the layer axis, so each (b, t)
    position attends only across its own layer history.

The only mandatory new parameter is W_Q. W_K can either be shared across all
history slots (``share_key=True``) or allocated per slot
(``share_key=False``). The latter is created lazily so the ablation works for
arbitrary history lengths.
"""

from __future__ import annotations

import math
from typing import List, Optional, Sequence

import torch
from torch import Tensor, nn
import torch.nn.functional as F

from .types import AttnResConfig


class AttentionResidual(nn.Module):
    """Compute AttnRes_l = sum_k a_{l,k} * x_k with softmax-normalized weights.

    When ``cfg.share_key=False``, W_K projections are created lazily per
    history slot. This is memory-efficient for single-device training but
    incompatible with DDP/FSDP's snapshot-at-wrap semantics; see
    ``docs/ARCHITECTURE.md §5.1`` for the distributed-training caveat and
    workarounds.
    """

    def __init__(self, cfg: AttnResConfig = AttnResConfig()) -> None:
        super().__init__()
        self.cfg = cfg
        self.w_q = nn.Linear(cfg.d_model, cfg.d_model, bias=False)
        self.w_k = nn.Linear(cfg.d_model, cfg.d_model, bias=False) if cfg.share_key else None
        self.w_k_layers = nn.ModuleList()
        self._last_weights: Optional[Tensor] = None

    # ------------------------------------------------------------------ helpers
    def _compute_weights(self, q: Tensor, keys: Tensor) -> Tensor:
        """Compute softmax-normalized attention weights along the layer axis."""
        d = q.size(-1)
        scale = self.cfg.temperature if self.cfg.temperature else math.sqrt(d)
        logits = (keys * q.unsqueeze(0)).sum(dim=-1) / scale
        return F.softmax(logits, dim=0)

    def _ensure_key_layers(self, count: int) -> None:
        """Grow the per-slot key bank to cover ``count`` history items."""
        if self.cfg.share_key:
            return
        while len(self.w_k_layers) < count:
            self.w_k_layers.append(nn.Linear(self.cfg.d_model, self.cfg.d_model, bias=False))

    # ------------------------------------------------------------------ forward
    def forward(self, history: Sequence[Tensor], x_current: Tensor) -> Tensor:
        """Run one step of vertical attention."""
        cfg = self.cfg
        pool: List[Tensor] = list(history)
        if cfg.include_self:
            pool.append(x_current)
        if not pool:
            return x_current

        x_stack = torch.stack(pool, dim=0)  # [K, B, T, D]
        q = self.w_q(x_current)  # [B, T, D]

        if cfg.share_key:
            assert self.w_k is not None
            keys = self.w_k(x_stack)  # [K, B, T, D]
        else:
            self._ensure_key_layers(len(pool))
            keys = torch.stack([proj(x_k) for proj, x_k in zip(self.w_k_layers, pool)], dim=0)

        a = self._compute_weights(q, keys)  # [K, B, T]
        self._last_weights = a.detach()
        out = (x_stack * a.unsqueeze(-1)).sum(dim=0)
        return out

    # ------------------------------------------------------------------ API
    def last_weights(self) -> Optional[Tensor]:
        """Return the attention weights from the last forward pass (or None)."""
        return self._last_weights


class AttentionResidualConnector(nn.Module):
    """Combine AttnRes_l with a sublayer F_l to form the residual rule.

    x_{l+1} = AttnRes_l(x_0, ..., x_l) + F_l(x_l)
    """

    def __init__(self, sublayer: nn.Module, attn_res: AttentionResidual) -> None:
        super().__init__()
        self.sublayer = sublayer
        self.attn_res = attn_res

    def forward(self, history: Sequence[Tensor], x: Tensor) -> Tensor:
        ar = self.attn_res(history, x)
        return ar + self.sublayer(x)
