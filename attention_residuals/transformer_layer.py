"""Decoupled horizontal + vertical Transformer layer — §5.2.

Horizontal self-attention (standard MHA) handles context along the token
axis; vertical self-attention (:class:`AttentionResidual`) handles the layer
axis. The two Query matrices are strictly independent — a key property the
article calls "纵横解耦".

Per-layer compute::

    h = LN(x)
    a = x + MHA(h, h, h)                   # horizontal path
    f = FFN(LN(a))                         # feed-forward sublayer
    y = AttnRes_l(history, a) + f          # vertical residual replaces + x
"""

from __future__ import annotations

from typing import List, Optional, Sequence

import torch
from torch import nn, Tensor

from .attn_residual import AttentionResidual
from .types import AttnResConfig


class _FFN(nn.Module):
    """Two-layer feed-forward network F_l."""

    def __init__(self, d_model: int, d_ff: int) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(d_model, d_ff),
            nn.GELU(),
            nn.Linear(d_ff, d_model),
        )

    def forward(self, x: Tensor) -> Tensor:
        return self.net(x)


class DecoupledTransformerLayer(nn.Module):
    """One Transformer layer with horizontal + vertical attention decoupled.

    Parameters
    ----------
    d_model : int
        Feature dimension.
    num_heads : int
        Number of horizontal-MHA heads. The vertical path stays single-head
        by default (§5.3 纯粹配置) and can be swapped for the multi-head
        version at the stack level.
    d_ff : int
        Hidden dim of the feed-forward sublayer.
    attn_cfg : Optional[AttnResConfig]
        Config for the vertical attention module. If None, a default
        (single-head, shared key) config is used.
    """

    def __init__(
        self,
        d_model: int = 64,
        num_heads: int = 4,
        d_ff: Optional[int] = None,
        attn_cfg: Optional[AttnResConfig] = None,
    ) -> None:
        super().__init__()
        d_ff = d_ff or 4 * d_model
        self.d_model = d_model

        # Horizontal (token-axis) MHA — standard Pre-Norm wiring.
        self.ln_mha = nn.LayerNorm(d_model)
        self.mha = nn.MultiheadAttention(d_model, num_heads, batch_first=True)

        # Feed-forward sublayer F_l.
        self.ln_ffn = nn.LayerNorm(d_model)
        self.ffn = _FFN(d_model, d_ff)

        # Vertical (layer-axis) attention residual — §5.1.
        cfg = attn_cfg or AttnResConfig(d_model=d_model)
        # Guarantee d_model alignment in case caller passed a mismatched cfg.
        if cfg.d_model != d_model:
            cfg = AttnResConfig(
                d_model=d_model,
                num_heads=cfg.num_heads,
                temperature=cfg.temperature,
                share_key=cfg.share_key,
                include_self=cfg.include_self,
            )
        self.attn_res = AttentionResidual(cfg)

    # ------------------------------------------------------------------ forward
    def forward(self, history: Sequence[Tensor], x: Tensor) -> Tensor:
        # Horizontal path (self-attention + residual).
        h = self.ln_mha(x)
        a, _ = self.mha(h, h, h, need_weights=False)
        a = x + a

        # Feed-forward sublayer on the horizontal output.
        f = self.ffn(self.ln_ffn(a))

        # Vertical residual: AttnRes over prior layer outputs replaces the
        # classic "+ x" term.
        return self.attn_res(history, a) + f

    # ------------------------------------------------------------------ trace
    def vertical_weights(self) -> Optional[Tensor]:
        """Return ``a_{l,k}`` weights from the last forward pass."""
        return self.attn_res.last_weights()
