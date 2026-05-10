"""Block Attention Residuals — §5 分段机制.

Total depth L is split into G = ``num_blocks`` groups of B = ``layers_per_block``
layers. Inside a block we use plain classic residuals; between blocks we use
the explicit vertical self-attention.

Vertical attention is computed **only over block outputs**, which bounds the
per-layer cost and keeps the stack tractable past L = 100:

    |history_b| = b  (≤ num_blocks)   →    overall complexity  O((L/B)^2 + L)

Default `inner_residual = False` implements the "2 选 1" advice from the
last paragraph of §5: remove the per-layer classic residual inside a block
if Attn Residual is already in use.
"""

from __future__ import annotations

from typing import Callable, List, Optional, Sequence

import torch
from torch import nn, Tensor

from dataclasses import replace

from .attn_residual import AttentionResidual
from .classic_residual import ClassicResidual
from .types import AttnResConfig, BlockConfig


SublayerFactory = Callable[[int], nn.Module]
"""Callable returning a fresh sublayer F_l for layer index l."""


class BlockAttnResStack(nn.Module):
    """Stack L = num_blocks * layers_per_block layers with Block Attn Residuals.

    Parameters
    ----------
    sublayer_factory : Callable[[int], nn.Module]
        Produces one sublayer ``F_l`` per layer index. The output shape must
        match the input shape.
    attn_cfg : AttnResConfig
        Configuration for the vertical attention module.
    block_cfg : BlockConfig
        Sectioning configuration.
    """

    def __init__(
        self,
        sublayer_factory: SublayerFactory,
        attn_cfg: AttnResConfig = AttnResConfig(),
        block_cfg: BlockConfig = BlockConfig(),
    ) -> None:
        super().__init__()
        self.attn_cfg = attn_cfg
        self.block_cfg = block_cfg

        total = block_cfg.total_layers
        # One inner residual wrapper per layer; shape-preserving.
        self.layers = nn.ModuleList(
            ClassicResidual(sublayer_factory(i)) for i in range(total)
        )
        # One vertical attention module per block boundary.
        # block b (b >= 1) attends to outputs of blocks 0..b-1.
        # Between-block attention runs over prior block outputs only; the
        # current input (i.e. the trailing output of block b-1) is already
        # included in ``history`` below, so we disable ``include_self``.
        between_cfg = replace(attn_cfg, include_self=False)
        self.block_attn = nn.ModuleList(
            AttentionResidual(between_cfg) for _ in range(block_cfg.num_blocks - 1)
        )
        # Record per-block attention weights for auditability.
        self._block_weights: List[Tensor] = []

    # ----------------------------------------------------------------- helpers
    def _block_slice(self, b: int) -> slice:
        per = self.block_cfg.layers_per_block
        return slice(b * per, (b + 1) * per)

    # ----------------------------------------------------------------- forward
    def forward(self, x: Tensor) -> Tensor:
        self._block_weights = []
        cfg = self.block_cfg
        history: List[Tensor] = []          # outputs of completed blocks
        current = x
        for b in range(cfg.num_blocks):
            # Between-block Attn Residual (skip for the very first block).
            if b > 0:
                ar = self.block_attn[b - 1](history, current)
                if cfg.inner_residual:
                    # "Both at the same time" — the article calls this
                    # redundant but shows it still converges.
                    current = current + ar
                else:
                    current = ar
                w = self.block_attn[b - 1].last_weights()
                if w is not None:
                    self._block_weights.append(w)
            # In-block: B classic residual layers.
            for layer in self.layers[self._block_slice(b)]:
                current = layer(current)
            history.append(current)
        return current

    # ----------------------------------------------------------------- trace
    def trace(self) -> List[Tensor]:
        """Return the block-level attention weights collected during the last
        forward pass. Useful for visualizing information pathways (§5.2)."""
        return list(self._block_weights)
