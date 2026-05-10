"""Explicit vertical self-attention over layer history — §5.1 (core module).

Formulas
--------
    a_{l,k} = softmax_k ( (q_l · K_k) / sqrt(d) )
    AttnRes_l(x_0, ..., x_l) = Σ_{k=0..l} a_{l,k} · x_k
    Σ_{k=0..l} a_{l,k} = 1
    x_{l+1} = AttnRes_l + F_l(x_l)        (see AttentionResidualConnector)

Shapes
------
    Each history tensor x_k has shape ``[B, T, D]`` (batch × tokens × features).
    The vertical attention operates **along the layer axis**, i.e. each
    (b, t) position attends to its own history across layers.

Keeping the Query matrix as the only mandatory new parameter preserves the
"Less is More" design from §5.3.
"""

from __future__ import annotations

import math
from typing import List, Optional, Sequence

import torch
from torch import nn, Tensor
import torch.nn.functional as F

from .types import AttnResConfig


class AttentionResidual(nn.Module):
    """Compute AttnRes_l = Σ_k a_{l,k} · x_k with softmax-normalized weights.

    Notes
    -----
    * ``Σ_k a_{l,k} = 1`` is guaranteed by softmax along the layer axis.
    * ``W_Q`` is the only *mandatory* new parameter; ``W_K`` can be shared
      across history layers (``share_key=True``, the paper's default) or
      unique per layer (``share_key=False``).
    * Values are taken as the raw history tensors x_k (no W_V); this keeps
      the "vertical residual = weighted sum of past hidden states" meaning.
      A learnable W_V lives in :mod:`multi_head_vertical`.
    """

    def __init__(self, cfg: AttnResConfig = AttnResConfig()) -> None:
        super().__init__()
        self.cfg = cfg
        self.w_q = nn.Linear(cfg.d_model, cfg.d_model, bias=False)
        self.w_k = nn.Linear(cfg.d_model, cfg.d_model, bias=False)
        # buffer for last computed attention (for auditability, §5.2)
        self._last_weights: Optional[Tensor] = None

    # ------------------------------------------------------------------ helpers
    def _compute_weights(self, q: Tensor, keys: Tensor) -> Tensor:
        """Compute softmax-normalized attention weights along the layer axis.

        Parameters
        ----------
        q : Tensor, shape ``[B, T, D]``
            Query built from the current layer input.
        keys : Tensor, shape ``[K, B, T, D]``
            Keys stacked along the layer axis (K = number of history layers).

        Returns
        -------
        Tensor, shape ``[K, B, T]``
            Attention weights with ``sum_k a = 1``.
        """
        d = q.size(-1)
        scale = self.cfg.temperature if self.cfg.temperature else math.sqrt(d)
        # logits_k = (q · K_k) / sqrt(d)    -> [K, B, T]
        logits = (keys * q.unsqueeze(0)).sum(dim=-1) / scale
        # softmax along layer axis k
        return F.softmax(logits, dim=0)

    # ------------------------------------------------------------------ forward
    def forward(self, history: Sequence[Tensor], x_current: Tensor) -> Tensor:
        """Run one step of vertical attention.

        Parameters
        ----------
        history : Sequence[Tensor]
            List of prior layer outputs ``[x_0, x_1, ..., x_{l-1}]``.
            Each tensor has shape ``[B, T, D]``.
        x_current : Tensor
            The current layer input ``x_l`` (shape ``[B, T, D]``).

        Returns
        -------
        Tensor
            ``AttnRes_l`` with shape ``[B, T, D]``.
        """
        cfg = self.cfg
        # §5.3: include x_l itself in the pool when include_self=True.
        pool: List[Tensor] = list(history)
        if cfg.include_self:
            pool.append(x_current)
        if not pool:
            # No history yet (e.g. at layer 0 with include_self=False).
            # Fall back to the current input so the network degenerates
            # gracefully to a classic residual.
            return x_current

        # Stack along a new "layer" axis -> [K, B, T, D]
        x_stack = torch.stack(pool, dim=0)
        # q = W_Q · x_l  -> [B, T, D]
        q = self.w_q(x_current)
        # K_k = W_K · x_k. share_key=True means W_K is shared across layers;
        # applying a single Linear to the stack achieves that.
        keys = self.w_k(x_stack)  # [K, B, T, D]
        # Weights along the layer axis
        a = self._compute_weights(q, keys)  # [K, B, T]
        self._last_weights = a.detach()
        # Weighted sum over history: Σ_k a_{l,k} · x_k
        #   x_stack: [K, B, T, D], a: [K, B, T] -> broadcast mul, sum over K
        out = (x_stack * a.unsqueeze(-1)).sum(dim=0)
        return out

    # ------------------------------------------------------------------ API
    def last_weights(self) -> Optional[Tensor]:
        """Return the attention weights from the last forward pass (or None)."""
        return self._last_weights


class AttentionResidualConnector(nn.Module):
    """Combine AttnRes_l with a sublayer F_l to form the new residual rule.

        x_{l+1} = AttnRes_l(x_0, ..., x_l) + F_l(x_l)

    This module is stateless with respect to history; callers are responsible
    for maintaining the list of previous layer outputs and feeding it in.
    """

    def __init__(self, sublayer: nn.Module, attn_res: AttentionResidual) -> None:
        super().__init__()
        self.sublayer = sublayer
        self.attn_res = attn_res

    def forward(self, history: Sequence[Tensor], x: Tensor) -> Tensor:
        ar = self.attn_res(history, x)
        return ar + self.sublayer(x)
