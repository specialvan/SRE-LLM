"""Multi-head vertical self-attention — §6 开放讨论（第 1 问）.

Formula
-------
    head^{(h)}_{l,k} = softmax_k ( (q^{(h)}_l · K^{(h)}_k) / sqrt(d_h) )
    AttnRes^{(h)}_l  = Σ_k head^{(h)}_{l,k} · (x_k W_V^{(h)})
    AttnRes_l        = concat_h( AttnRes^{(h)}_l ) · W_O

This is a strict generalisation of :class:`AttentionResidual` — with
``num_heads = 1`` and identity ``W_V`` / ``W_O`` the two modules are
numerically equivalent.
"""

from __future__ import annotations

import math
from typing import List, Optional, Sequence

import torch
from torch import nn, Tensor
import torch.nn.functional as F

from .types import AttnResConfig


class MultiHeadAttentionResidual(nn.Module):
    """Multi-head version of :class:`AttentionResidual`.

    Parameters
    ----------
    cfg : AttnResConfig
        ``cfg.d_model`` is split into ``cfg.num_heads`` heads of dim d_h.
        ``cfg.d_model`` must be divisible by ``cfg.num_heads``.
    """

    def __init__(self, cfg: AttnResConfig) -> None:
        super().__init__()
        if cfg.d_model % cfg.num_heads != 0:
            raise ValueError("d_model must be divisible by num_heads")
        self.cfg = cfg
        self.d_head = cfg.d_model // cfg.num_heads

        self.w_q = nn.Linear(cfg.d_model, cfg.d_model, bias=False)
        self.w_k = nn.Linear(cfg.d_model, cfg.d_model, bias=False)
        self.w_v = nn.Linear(cfg.d_model, cfg.d_model, bias=False)
        self.w_o = nn.Linear(cfg.d_model, cfg.d_model, bias=False)

        self._last_weights: Optional[Tensor] = None

    # ------------------------------------------------------------------ split
    def _split_heads(self, t: Tensor) -> Tensor:
        """[..., D] -> [..., H, d_h]."""
        *lead, _ = t.shape
        return t.view(*lead, self.cfg.num_heads, self.d_head)

    def _merge_heads(self, t: Tensor) -> Tensor:
        """[..., H, d_h] -> [..., D]."""
        *lead, h, dh = t.shape
        return t.reshape(*lead, h * dh)

    # ------------------------------------------------------------------ forward
    def forward(self, history: Sequence[Tensor], x_current: Tensor) -> Tensor:
        cfg = self.cfg
        pool: List[Tensor] = list(history)
        if cfg.include_self:
            pool.append(x_current)
        if not pool:
            return x_current

        x_stack = torch.stack(pool, dim=0)             # [K, B, T, D]

        # Per-head projections.
        q = self._split_heads(self.w_q(x_current))     # [B, T, H, d_h]
        K = self._split_heads(self.w_k(x_stack))       # [K, B, T, H, d_h]
        V = self._split_heads(self.w_v(x_stack))       # [K, B, T, H, d_h]

        scale = cfg.temperature if cfg.temperature else math.sqrt(self.d_head)
        # logits: [K, B, T, H] = sum over d_h of q * K_k
        logits = (K * q.unsqueeze(0)).sum(dim=-1) / scale
        # Softmax along the layer axis k.
        a = F.softmax(logits, dim=0)                   # [K, B, T, H]
        self._last_weights = a.detach()

        # Weighted sum over history:
        # V: [K, B, T, H, d_h], a: [K, B, T, H] -> broadcast over d_h
        out = (V * a.unsqueeze(-1)).sum(dim=0)         # [B, T, H, d_h]
        out = self._merge_heads(out)                   # [B, T, D]
        return self.w_o(out)

    def last_weights(self) -> Optional[Tensor]:
        return self._last_weights
